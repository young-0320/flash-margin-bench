#!/usr/bin/env python3
"""UART 욕조 v2 스트림 수신 → bathtub2 CSV 파일화 (ps/src/bathtub_v2.c 의 PC측 반쪽, 수정안 #4 §2.5 · §2.6).

v1(sweep_uart_capture.py)과 따로 둔다 — 파일 이름부터 다르다(`bathtub2_*`). 메타 열 · 불변식(chip 은 UID 없이
만들지 않는다) · 무효 파일 이름 규칙은 v1 것을 그대로 가져다 쓴다.

  M,<v1 메인 열 9개>,<pass>   → bathtub2_<label>[_<uid16>]_<stamp>.csv
  R,<step>,<i>,<e>,<6 값>     → bathtub2_<label>[_<uid16>]_<stamp>_reads.csv  (pass 는 여기서 붙인다)

R 줄에는 pass 가 없다 — R 묶음 뒤에 그 (pass, phase_step) 의 M 줄이 오므로, R 행을 스풀 파일에 모았다가 M 을 받으면
그 pass 부호(s · c · w · r)를 붙여 옮긴다. 초심부는 한 스텝 R 행이 약 200만이라 메모리에 두지 않는다.

완주 검사 (§2.6):
  1. BEGIN 에 fmt=bathtub2 가 없으면 받지 않고 끊는다
  2. (pass, phase_step) 마다 R 행 수 = 그 M 의 n_reads, R 의 phase_step = M 의 것. 어긋나면(R 행이 빠짐) 그 메인 행
     flags 에 reads_gap — 런은 유효로 둔다. R 행이 다 왔는데 Σerr_count ≠ bit_errors 면 값이 깨진 것 → 무효 ⑤
  3. 받은 메인 행 수 ≠ END main_rows → 무효 ⑤
  4. 받은 R 행 총수 ≠ END reads_rows 인데 2 에 걸린 스텝이 없으면 → 무효 ⑤. 어느 M 에도 붙지 못한 R 행이 남아도 무효 ⑤
  5. scan · rescan 행이 phase_step 0 .. steps − 1 을 하나씩 갖지 않거나, (pass, phase_step) 가 파일 안에서 겹치면 → 무효 ⑤
END 의 mode · flags 와 reason 은 END 를 받은 뒤 전 행에 채운다 (v1 fill_reason 과 같은 원자적 갈아끼우기).

저장 위치: data/bathtub2/<label>/ (S-6 §5 「원본 다루기」 — 초심부 원본은 스윕당 약 1.7GB 라 따로 둔다).

라이브러리: capture_bathtub2(ser, label, uid, ...) — 래퍼(host/run/run_sweep_chip.py --mode bathtub2)가 부른다.
사용: bathtub2_capture.py (--uid <16hex> | --loopback) [--port] [--baud] ...
"""

import argparse
import queue
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_registry  # noqa: E402
import sweep_uart_capture as v1  # noqa: E402

DEFAULT_ROOT = v1.DEFAULT_OUTDIR / "bathtub2"
PASS_CODE = {"scan": "s", "ceil": "c", "wall": "w", "rescan": "r"}
MAIN_COLS = v1.MAIN_COLS + ",pass,base_sector"
READS_COLS = "phase_step,pass,read_idx,err_count,e_c0,e_c1,e_c2,e1_c0,e1_c1,e1_c2"
N_MAIN_FIELDS = 10       # M, 뒤의 열 수 (v1 9 + pass)
N_READS_FIELDS = 9       # R, 뒤의 열 수


class Result(NamedTuple):
    valid: bool
    n_main: int
    n_reads: int
    main_path: Path
    reads_path: Path
    begin: dict
    end: dict
    reason: str
    gap_rows: int            # reads_gap 이 붙은 메인 행 수


def bathtub2_base(outdir, label, uid, stamp):
    return Path(outdir) / (f"bathtub2_{label}_{stamp}" if label == "loopback"
                           else f"bathtub2_{label}_{uid}_{stamp}")


def kv(line):
    return dict(t.split("=", 1) for t in line.split() if "=" in t)


def finalize_main(path, mode, run_flags, gap, reason):
    """mode · flags · reason 열을 채운다. 스트리밍 중에는 END 의 값을 모르므로 다 받은 뒤 원자적으로 갈아끼운다.
    헤더 = v1 열 · pass · base_sector · mode · flags · 메타 · reason (수정안 #4 §2.5)."""
    tmp = path.with_name(path.name + ".tmp")
    k = MAIN_COLS.count(",") + 1                      # mode · flags 를 끼울 자리
    with open(path) as src, open(tmp, "w") as dst:
        h = src.readline().rstrip("\n").split(",")
        dst.write(",".join(h[:k] + ["mode", "flags"] + h[k:] + [v1.REASON_COL]) + "\n")
        for i, line in enumerate(src):
            f = line.rstrip("\n").split(",")
            fl = ";".join(x for x in (run_flags, "reads_gap" if i in gap else "") if x)
            dst.write(",".join(f[:k] + [mode, fl] + f[k:] + [reason]) + "\n")
    tmp.replace(path)


class _Pump:
    """시리얼 줄을 따로 도는 스레드가 계속 읽어 큐에 쌓는다 — readline 만 흉내 낸다.
    M 줄마다 스풀을 _reads 로 옮기는 동안(deep 벽 스텝 약 2백만 행 — 약 0.4초) 포트를 안 읽으면
    커널 · FTDI 버퍼(유실 위치로 역산하면 약 5KB)가 넘쳐 다음 스텝 R 행이 빠진다 (2026-11-17 리뷰 F1).
    포트(in_waiting 이 있는 것)는 쌓인 바이트를 한 번에 읽어 줄로 나눈다. pyserial readline 은 1바이트마다
    read(1) 을 불러 바이트당 비용이 크다 — 11/17 초심부 두 런이 2백만 행 M 직후 0.4초 안에서 벽 스텝마다
    R 65-225 행 · rescan 130 스텝을 잃고 무효였다(유실 주기로 역산한 옛 펌프 속도 약 53KB/s < 92KB/s).
    시험 대역(readline 만 있는 것)은 readline 으로 읽는다.
    덩어리 읽기는 개행으로 끝나지 않은 마지막 조각을 내보내지 않는다 — 펌웨어 줄은 모두 \\r\\n 으로 끝난다.
    포트 예외는 받는 쪽 readline 에서 다시 던진다."""

    def __init__(self, ser):
        self.port, self.baudrate = ser.port, ser.baudrate
        self._ser, self._q, self._stop, self._err = ser, queue.Queue(), threading.Event(), None
        self._th = threading.Thread(target=self._run, daemon=True)
        self._th.start()

    def _run(self):
        buf = b""
        try:
            chunked = hasattr(type(self._ser), "in_waiting")   # 클래스에서 본다 — 프로퍼티를 평가하면 죽은 포트의 예외가 여기서 난다
            while not self._stop.is_set():
                if not chunked:
                    ln = self._ser.readline()
                    if ln:
                        self._q.put(ln)
                    continue
                b = self._ser.read(max(1, self._ser.in_waiting))   # 포트 timeout 이 지나면 b"" — stop 을 본다
                if not b:
                    continue
                *lines, buf = (buf + b).split(b"\n")
                for ln in lines:
                    self._q.put(ln + b"\n")
        except BaseException as e:                  # noqa: BLE001 — 포트 예외 · 시험 대역의 Ctrl-C 를 받는 쪽에서 다시 던진다
            self._err = e

    def readline(self):
        try:
            return self._q.get(timeout=1.0)
        except queue.Empty:
            if self._err is not None:
                raise self._err
            return b""

    def stop(self):
        self._stop.set()

    def join(self):
        """스레드가 끝나야 다음 소비자(같은 포트의 다음 반복 · UID 대조)와 포트를 다투지 않는다 — 포트 timeout 이 있어야 깬다.
        덩어리 읽기는 END 뒤 바이트까지 가져갈 수 있지만, 펌웨어는 END 뒤 말이 없고 다음 반복은 reset_input_buffer 로 시작한다."""
        self._th.join(timeout=10)
        if self._th.is_alive():
            raise RuntimeError("시리얼 읽기 스레드가 10초 안에 안 끝났다 — 포트 timeout 이 없으면 readline 이 안 깬다")


def capture_bathtub2(ser, label, uid, outdir=None, *, reseat=0, repeat_idx=1, batch_id=None,
                     log=sys.stderr, expect_base_sector=None):
    """열린 시리얼 핸들에서 욕조 v2 스윕 1회를 받아 CSV 2개로 쓴다. Ctrl-C 는 파일을 _invalid 로 정리한 뒤 다시 던진다."""
    uid = v1.check_target(label, uid)
    outdir = Path(outdir) if outdir else DEFAULT_ROOT / label
    outdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = v1.utc_stamp(now)
    meta = (f"{label},{now.isoformat(timespec='seconds')},{v1.git_rev()},"
            f"{uid},{int(reseat)},{int(repeat_idx)},{batch_id or stamp}")

    base = bathtub2_base(outdir, label, uid, stamp)
    main_path, reads_path = Path(f"{base}.csv"), Path(f"{base}_reads.csv")
    spool_path = Path(f"{base}_reads.spool")

    began = False
    begin, end = {}, {}
    base_sector = ""
    n_main = n_reads = 0                 # 받은 행 (R 은 스풀에 들어간 것까지)
    orphans = 0                          # 어느 M 에도 붙지 못한 R 행
    gap = set()                          # reads_gap 메인 행 번호 (0부터)
    seen = Counter()                     # (pass, phase_step) → 받은 M 행 수
    bad_sum = 0                          # R 행이 다 왔는데 Σerr_count ≠ bit_errors 인 스텝
    sp_n = sp_sum = 0                    # 스풀의 R 행 수 · Σerr_count
    sp_steps = set()                     # 스풀 R 행의 phase_step
    malformed = 0
    interrupted = None
    t_begin = t_last = None

    def show_progress():
        nonlocal t_last
        if t_begin is None or time.monotonic() - t_last < v1.PROGRESS_S:
            return
        t_last = time.monotonic()
        el = t_last - t_begin
        print(f"  progress main {n_main} · reads {n_reads}  {n_reads / el if el > 0 else 0:.0f} reads/s  "
              f"elapsed {v1.fmt_mmss(el)}", file=log)

    ser = _Pump(ser)
    try:
        with open(main_path, "x") as fm, open(reads_path, "x") as fr, open(spool_path, "w+") as sp:
            fm.write(f"{MAIN_COLS},{v1.META_COLS}\n")
            fr.write(f"{READS_COLS}\n")
            print(f"listening on {ser.port} @{ser.baudrate} → {main_path}", file=log)

            def flush_spool(code):
                """스풀 R 행을 pass 부호를 붙여 _reads 로 옮긴다."""
                sp.seek(0)
                for r in sp:
                    s, rest = r.split(",", 1)
                    fr.write(f"{s},{code},{rest}")
                sp.seek(0)
                sp.truncate()

            while True:
                line = ser.readline().decode(errors="replace").strip()
                show_progress()
                if not line:
                    continue
                i = line.find("#G0")
                if i >= 0:
                    line = line[i:]
                    print(line, file=log)
                    if "SWEEP BEGIN" in line:
                        begin = kv(line)
                        if begin.get("fmt") != "bathtub2":
                            print(f"fmt={begin.get('fmt', '(없음)')} — 욕조 v2 스트림이 아니다. 받지 않고 중단", file=log)
                            break
                        base_sector = begin.get("base_sector", "")
                        if expect_base_sector is not None and base_sector != str(expect_base_sector):
                            print(f"기대 base_sector={expect_base_sector} 인데 ELF 는 {base_sector} — 받지 않고 중단",
                                  file=log)
                            break
                        began = True
                        t_begin = t_last = time.monotonic()
                    elif "ERROR" in line:
                        break
                    elif "SWEEP END" in line:
                        end = kv(line)
                        break
                elif began and line.startswith("M,"):
                    f = line[2:].split(",")
                    try:
                        if len(f) != N_MAIN_FIELDS:
                            raise ValueError
                        step, nr, bits = int(f[0]), int(f[2]), int(f[4])
                        code = PASS_CODE[f[9]]
                    except (ValueError, IndexError, KeyError):
                        malformed += 1                       # 받지 못한 줄로 센다 — 메인 행 수가 잡는다
                        continue
                    if sp_n != nr or sp_steps - {step}:
                        gap.add(n_main)
                        print(f"reads_gap: {f[9]} step {step} — R {sp_n}/{nr} 행, Σ {sp_sum}/{bits}", file=log)
                    elif sp_sum != bits:
                        bad_sum += 1
                        print(f"Σ 불일치: {f[9]} step {step} — R {sp_n} 행 다 왔는데 Σ {sp_sum} ≠ {bits}", file=log)
                    seen[(f[9], step)] += 1
                    flush_spool(code)
                    sp_n = sp_sum = 0
                    sp_steps.clear()
                    fm.write(f"{line[2:]},{base_sector},{meta}\n")
                    n_main += 1
                elif began and line.startswith("R,"):
                    f = line[2:].split(",")
                    try:
                        if len(f) != N_READS_FIELDS:
                            raise ValueError
                        v = [int(x) for x in f]
                    except ValueError:
                        malformed += 1
                        continue
                    sp.write(line[2:] + "\n")
                    sp_n += 1
                    sp_sum += v[2]
                    sp_steps.add(v[0])
                    n_reads += 1
            if sp_n:                                         # 어느 M 에도 붙지 못한 R 행 — 원본은 남긴다 (pass 빈칸)
                orphans = sp_n
                flush_spool("")
    except KeyboardInterrupt as e:
        print("interrupted — 무효 ⑤(미완주)", file=log)
        interrupted = e
    except Exception as e:                                   # 포트 소실 등 — 파일을 _invalid 로 정리한 뒤 다시 던진다
        print(f"예외 {e!r} — 무효 ⑤(미완주)", file=log)
        interrupted = e
    finally:
        ser.stop()                                           # join 은 정리가 끝난 뒤 — 기다리는 동안 온 Ctrl-C 가 정리를 건너뛰지 않게
    spool_path.unlink(missing_ok=True)

    complete = False
    if end:
        main_ok = n_main == int(end.get("main_rows", -1))
        reads_ok = n_reads == int(end.get("reads_rows", -1)) or bool(gap)
        steps = list(range(int(begin.get("steps", -1))))
        dup = sum(v - 1 for v in seen.values())
        sweeps_ok = all(sorted(s for q, s in seen if q == p) == steps for p in ("scan", "rescan"))
        complete = began and main_ok and reads_ok and not orphans and not dup and sweeps_ok and not bad_sum
        if end.get("valid") == "1" and not complete:
            print(f"행 결측 — 무효 ⑤: main {n_main}/{end.get('main_rows')}, reads {n_reads}/{end.get('reads_rows')}, "
                  f"reads_gap {len(gap)} 스텝, 붙지 못한 R {orphans} 행, 깨진 줄 {malformed}, (pass, step) 겹침 {dup}, "
                  f"scan · rescan 0..{len(steps) - 1} {'맞음' if sweeps_ok else '어긋남'}, Σ 불일치 {bad_sum} 스텝", file=log)
    valid = end.get("valid") == "1" and complete

    if not end:
        reason = ("interrupted" if isinstance(interrupted, KeyboardInterrupt) else "port_error") if interrupted else "no_end"
    elif end.get("valid") == "1" and not complete:
        reason = "row_mismatch"                              # ⑤ — v1 과 같은 이름
    else:
        reason = end.get("reason") or "unknown"

    if not valid:
        main_path = main_path.rename(Path(f"{base}_invalid.csv"))
        reads_path = reads_path.rename(Path(f"{base}_invalid_reads.csv"))
    finalize_main(main_path, end.get("mode", ""), end.get("flags", ""), gap, reason)
    print(f"{'VALID' if valid else 'INVALID'}: {n_main} rows, {n_reads} read rows, reads_gap {len(gap)}, "
          f"mode={end.get('mode', '')} flags={end.get('flags', '')} reason={reason}\n  {main_path}\n  {reads_path}",
          file=log)
    ser.join()
    if interrupted:
        raise interrupted
    return Result(valid, n_main, n_reads, main_path, reads_path, begin, end, reason, len(gap))


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--outdir", type=Path, help="기본 data/bathtub2/<label>/")
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--uid", help="#PREP UID / #G2 UID <16hex>. 라벨은 등록부 역조회")
    who.add_argument("--loopback", action="store_true", help="G0 루프백 (UID 없음)")
    ap.add_argument("--reseat", type=int, choices=(0, 1), default=0)
    ap.add_argument("--repeat-idx", type=int, default=1)
    ap.add_argument("--batch-id", help="배치 시작 stamp. 생략 시 이 스윕의 stamp")
    args = ap.parse_args()

    if args.loopback:
        label, uid = "loopback", None
    else:
        label = chip_registry.label_for(args.uid)
        if label is None:
            raise SystemExit(f"UID {args.uid.upper()} 는 등록부에 없다 — docs/chip_registry.md")
        uid = args.uid
    v1.check_target(label, uid)
    try:
        with v1.serial.Serial(args.port, args.baud, timeout=2) as ser:
            r = capture_bathtub2(ser, label, uid, args.outdir, reseat=args.reseat,
                                 repeat_idx=args.repeat_idx, batch_id=args.batch_id)
    except KeyboardInterrupt:
        sys.exit(1)
    sys.exit(0 if r.valid else 1)


if __name__ == "__main__":
    main()
