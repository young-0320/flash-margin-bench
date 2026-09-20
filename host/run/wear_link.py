#!/usr/bin/env python3
"""UART 어댑터 — 경계 9개(`docs/interface/pe_engine.md` §2)와 같은 메서드 이름으로 실엔진을 부른다.

    link = WearLink(SerialTransport(ser))          # 실칩 — pyserial
    link = WearLink(PipeTransport([sim_bin]))      # 호스트 시뮬레이션 — ps/sim/ 파이프
    link.wear_start(1000, 7, 0x00, cycle=0, delta=100, session=n)
    link.wait_stopped()                            # running 이 아닐 때까지 행을 받아 log 에 넣는다

문자열의 생성·해석은 **`host/tests/host_side.py` 의 함수만** 쓴다 — 문법의 정본이 거기 하나다.
`REJECT` 는 `host_side.Reject(code)` 로 올리고, `#WEAR` 행은 전부 `WearLog` 에 들어간다.
반환 모양은 mock(`host/tests/mock_engine.py`)과 같아서 같은 채점표(`harness.py`)로 채점된다.

재시도는 **전송에만 3회** (`[D41-18]`) — 응답이 시간 안에 안 오면 같은 `req` 로 다시 보낸다.
그 재전송에 `E_DUP` 이 오면 첫 명령은 처리됐고 응답만 잃은 것이다 (`LostResponse`). 호스트는
그때 `wear_status()` 로 확인한다 (S-4 §4). 플래시 동작은 재시도하지 않는다.
"""

import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import host_side as hs                                      # noqa: E402

TALLY_STRIDE = 100
DUMP_ROWS = 64
CMD_TIMEOUT_S = 5.0       # 명령 → 응답. running 중엔 사이클 경계(≈0.5s)까지 기다린다
XFER_RETRY = 3


class LostResponse(hs.Reject):
    """재전송이 `E_DUP` 으로 돌아왔다 — 첫 명령은 처리됐고 응답만 잃었다. `wear_status()` 로 확인할 것."""


# ── 전송층 — 줄 단위 수신 스레드 + 큐. 시리얼과 파이프가 같은 모양 ────────
class _LineReader:
    def __init__(self):
        self.q = queue.Queue()
        self._th = threading.Thread(target=self._loop, daemon=True)
        self.raw = []                     # 받은 원문 전부 (세션 로그용)
        self._th.start()

    def _read_one(self):
        raise NotImplementedError

    def _loop(self):
        try:
            while True:
                line = self._read_one()
                if line is None:
                    break
                if line:
                    self.raw.append(line)
                    self.q.put(line)
        except Exception:
            pass
        self.q.put(None)

    def readline(self, timeout):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return b""


class PipeTransport(_LineReader):
    """호스트 시뮬레이션 — `build/sim/flash_wear_sim` 을 파이프로 띄운다."""

    def __init__(self, cmd, env=None):
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env)
        super().__init__()

    def _read_one(self):
        line = self.proc.stdout.readline()
        return None if not line else line

    def write(self, data: bytes):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.wait(timeout=10)


class SerialTransport(_LineReader):
    """실칩 — 열린 pyserial 핸들. `readline` 은 포트 timeout 마다 깨어난다.
    `reader` 를 주면 읽기만 그쪽으로 (xsct 구간 선수신을 앞에 흘리는 `Drained`)."""

    def __init__(self, ser, reader=None):
        self.ser, self.reader = ser, reader or ser
        super().__init__()

    def _read_one(self):
        return self.reader.readline()       # timeout 이면 b"" — 루프가 계속 돈다

    def write(self, data: bytes):
        self.ser.write(data)
        self.ser.flush()

    def close(self):
        pass


# ── 어댑터 ─────────────────────────────────────────────────────────────────
class WearLink:
    def __init__(self, transport, log=None, timeout=CMD_TIMEOUT_S):
        self.t, self.log, self.timeout = transport, log or hs.WearLog(), timeout
        self.req = 0
        self.responses = []               # (보낸 명령, 응답 원문) — 세션 로그용

    # 전송
    def _feed(self, raw: bytes):
        """`#WEAR` 행이면 log 에 넣고 True. 아니면 False (응답이거나 쓰레기)."""
        if hs.PREFIX.encode() in raw:
            self.log.feed_line(raw)
            return True
        return False

    def _wait_response(self, req, timeout):
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            raw = self.t.readline(left)
            if raw is None:
                raise ConnectionError("링크가 닫혔다")
            if not raw or self._feed(raw):
                continue
            r = hs.parse_response(raw.decode(errors="replace"))
            if r is not None and r.req == req:
                self.responses.append(raw.decode(errors="replace").rstrip())
                return r

    def _send(self, verb, timeout=None, **args):
        self.req += 1
        line = hs.format_cmd(verb, self.req, **args)
        self.responses.append(line)
        for attempt in range(XFER_RETRY):
            self.t.write((line + "\n").encode())
            r = self._wait_response(self.req, timeout or self.timeout)
            if r is None:
                continue
            if r.kind == "REJECT":
                code = r.fields["code"]
                if attempt and code == "E_DUP":
                    raise LostResponse(code)
                raise hs.Reject(code)
            return r
        raise TimeoutError(f"{verb}: 응답 없음 ({XFER_RETRY}회)")

    def pump(self, seconds):
        """행만 받는다 — 명령 없이. 받은 행 수를 돌려준다."""
        n, deadline = 0, time.monotonic() + seconds
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                return n
            raw = self.t.readline(left)
            if raw is None:
                raise ConnectionError("링크가 닫혔다")
            if raw and self._feed(raw):
                n += 1

    def wait_stopped(self, timeout=600.0, poll=0.5):
        """`running` 이 아닐 때까지 — 행을 받으면서 STATUS 로 확인한다. 마지막 status 를 돌려준다."""
        deadline = time.monotonic() + timeout
        while True:
            self.pump(poll)
            st = self.wear_status()
            if st[1] != "running":
                self.pump(0.2)            # 경계 뒤에 남은 행
                return st
            if time.monotonic() > deadline:
                raise TimeoutError(f"{timeout}s 안에 멈추지 않았다 (state={st[1]} cycle={st[0]})")

    # 경계 1~9
    def wear_start(self, base_sector, n_sectors, pattern, cycle, delta, session):
        self._send("START", base=base_sector, n_sectors=n_sectors, pattern=pattern,
                   cycle=cycle, delta=delta, session=session)

    def wear_status(self):
        f = self._send("STATUS").fields
        return f["cycle"], f["state"], bool(f["defect_seen"]), f.get("last_reject", "")

    def wear_resume(self):
        f = self._send("RESUME").fields
        return hs.ResumeInfo(f["tally_a"] * TALLY_STRIDE, f["tally_b"] * TALLY_STRIDE,
                             bool(f["mismatch"]), f["next_byte"], bool(f["write_ok"]))

    def blank_check(self, base_sector, n_sectors):
        f = self._send("BLANK", base=base_sector, n_sectors=n_sectors).fields
        return hs.BlankCheck(f["erase_residual_bits"], f["program_fail_bits"], f["addrs"],
                             f["addr_count"], f["worst_page"], f["worst_bits"])

    def tally_read(self):
        f = self._send("TALLY").fields
        return f["count_a"] * TALLY_STRIDE, f["count_b"] * TALLY_STRIDE, bool(f["mismatch"])

    def tally_dump(self):
        before = len(self.log.d)
        self._send("DUMP")
        deadline = time.monotonic() + self.timeout
        while len(self.log.d) < before + DUMP_ROWS:
            if time.monotonic() > deadline:
                raise TimeoutError(f"DUMP 행 {len(self.log.d) - before}/{DUMP_ROWS}")
            self.pump(0.05)
        rows = self.log.d[before:]
        out = [bytearray(), bytearray()]
        for d in sorted(rows, key=lambda d: (d["copy"], d["off"])):
            out[d["copy"]] += bytes.fromhex(d["hex"])
        return bytes(out[0]), bytes(out[1])

    def uid_read(self):
        return self._send("UID").fields["uid"]

    def reerase(self, base_sector, n_sectors, timeout=None):
        f = self._send("REERASE", timeout=timeout, base=base_sector, n_sectors=n_sectors).fields
        return hs.Reerase(f["ok"], f["t_erase_us"], f["resid_after"])

    def halt(self):
        self._send("HALT")

    def close(self):
        self.t.close()
