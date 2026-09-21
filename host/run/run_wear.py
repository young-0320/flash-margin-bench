#!/usr/bin/env python3
"""마모 엔진 호스트 실행기 — 실칩 인수 시험(S-4 §9)과 복구(S-1 §8.3)를 명령 한 줄로.

    run_wear.py accept  --i-approve-real-pe [--cycle 0] [--delta 100]   ELF 프로그래밍 → START → 캡처 → A1~A7·C 판정
    run_wear.py status | halt | tally | dump | uid                      읽기·정지 (halt 는 다음 사이클 경계)
    run_wear.py resume  --host-log-max N | --from-session <dir>          RESUME → decide_resume → BLANK → (REERASE) → 채택값 출력
    run_wear.py tally-erase --i-approve-tally-erase                      tally 두 벌 소거 — UID 를 직접 타이핑해야 하고, 장부에 먼저 적는다

    공통: --port /dev/ttyUSB1 --baud 921600 | --sim build/sim/flash_wear_sim (호스트 시뮬레이션, P/E 없음)
          --no-program (accept 에서 xsct 단계 생략 — 이미 떠 있는 엔진에 붙는다)

**P/E 는 비가역이다.** `accept` 는 `--i-approve-real-pe` 없이는 실칩에 START 를 보내지 않는다 (`--sim` 은 예외).
`resume` 은 START 를 자동으로 보내지 않는다 — 채택값을 출력하고 사람이
`accept --cycle <채택값> --delta <n>` 으로 잇는다. 마모 영역은 TB 전용 1,000~1,006 고정이다 (S-4 §9);
파일럿 마모 그룹(0~6)의 체크포인트 편성(prep → 스윕 → ELF 교체 → START)은 근접·원격 스윕이 막혀 있어
(로그 44 [U44-8]) 이 실행기에 없다.

세션 로그: build/logs/wear/<session>/ — raw.txt(원문 전부) · H/A/B/R/D.txt(행 분리) · commands.txt ·
verdict.txt · resume.txt. 문자열 생성·해석은 host/tests/host_side.py, 전송은 host/run/wear_link.py.
의존: run_sweep_chip.py 의 Session·run_xsct·Drained·require_tty, chip_pe.py, chip_registry.py, pyserial, xsct.
"""

import argparse
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "tests"))
sys.path.insert(0, str(REPO / "host" / "capture"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_pe                                              # noqa: E402
import chip_registry                                        # noqa: E402
import host_side as hs                                      # noqa: E402
import wear_link as wl                                      # noqa: E402
from run_sweep_chip import Abort, Drained, Session, require_tty, run_xsct   # noqa: E402

WEAR_ELF = REPO / "build" / "vitis_wear" / "flash_wear" / "build" / "flash_wear.elf"
PROGRAM_G2 = REPO / "ps" / "scripts" / "program_g2.tcl"
LOG_ROOT = REPO / "build" / "logs" / "wear"
TB_BASE, TB_N = 1000, 7                                     # S-4 §9 TB 전용 마모 영역 — 옵션이 아니다
TB_SECTORS = f"{TB_BASE}~{TB_BASE + TB_N - 1}"
PATTERN = 0x00                                              # 파일럿 고정값 (S-1 §1)
PILOT_CHIP = "chip01"                                       # 등록부 — 파일럿 칩
ERASE_WARN_US = 400_000                                     # S-1 §10·§13 A6
SEC_PER_CYCLE = 2.0                                         # typ 0.405s — 대기 상한 산정용
PROBE_TOTAL = TB_N * 4096 * 8                               # 7섹터 전 비트 = 229,376 — probe 의 정답 (pattern 0x00)


# ── 순수 함수 — pytest 가 잰다 ──────────────────────────────────────────────
def judge_accept(log, status, tally, dumps, uid, expected_uid, n=100, probe=None):
    """S-1 §13 A1~A7 + C + probe. [(항목, 통과, 설명)]. A6 는 실칩에서만 뜻이 있다 (mock·sim 은 시계가 가짜).

    probe 는 멈춘 뒤 BLANK 를 부른 결과다 — 마지막 동작이 소거였으니 0xFF 를 0x00 과 대조하면
    전량(PROBE_TOTAL)이 나와야 한다. 0 이면 세는 경로가 죽은 것이고, 그때는 B 행의 0 도 못 믿는다
    (harness.check_probe 와 같은 검사, 워크플로 12 §3.3). None 은 BLANK 자체가 거부된 것."""
    cycle, state, _, _ = status
    ta, tb, mismatch = tally
    b_cycle = log.b[-1]["cycle"] if log.b else None
    ids = {h["chip_id"] for h in log.h}
    erase = [a["t_erase_us"] for a in log.a]
    paths = {"카운터": cycle, "A행수÷7": len(log.a) / 7, "B의 cycle": b_cycle, "tally×100": ta}
    out = [
        ("A1", cycle == n, f"카운터 {cycle} (기대 {n})"),
        ("A2", len(log.a) == n * 7, f"A 행 {len(log.a)} (기대 {n * 7}), 깨진 행 {len(log.rejected)}"),
        ("A3", len(log.b) == n // 100, f"B 행 {len(log.b)} (기대 {n // 100})"),
        ("A4", all(d.count(0) == n // 100 for d in dumps),
         "tally 0x00 " + "/".join(str(d.count(0)) for d in dumps) + f" (기대 각 {n // 100})"),
        ("A5", not mismatch and all(v == n for v in paths.values()),
         f"{paths}" + (" tally 불일치" if mismatch else "")),
        ("A6", bool(erase) and max(erase) < ERASE_WARN_US,
         f"t_erase_us max {max(erase) if erase else '-'} median {sorted(erase)[len(erase) // 2] if erase else '-'}"
         " (실칩에서만 뜻이 있다)"),
        ("A7", ids == {expected_uid} and uid == expected_uid,
         f"로그 chip_id {sorted(ids)} · 경계 7 {uid} · 등록부 {expected_uid}"),
        ("C", state == "checkpoint_due", f"state={state}"),
        ("probe", probe is not None and probe.erase_residual_bits == 0 and probe.program_fail_bits == PROBE_TOTAL,
         "BLANK 거부 — 세는 경로를 확인 못 했다" if probe is None else
         f"program_fail_bits {probe.program_fail_bits} (기대 {PROBE_TOTAL}) 잔류 {probe.erase_residual_bits}"
         + ("" if probe.program_fail_bits else " — 세는 경로가 죽었다, B 행의 0 을 믿지 말 것")),
    ]
    return out


def split_rows(raw_lines):
    """원문 줄 목록 → {'H': [...], 'A': [...], ...} (체크섬 통과한 행만, 원문 그대로)."""
    out = {k: [] for k in hs.ROW_KINDS}
    for ln in raw_lines:
        i = ln.find(hs.PREFIX)
        if i < 0:
            continue
        row = hs.parse_row(ln[i + len(hs.PREFIX):])
        if row:
            out[row["type"]].append(ln[i:].rstrip())
    return out


def host_log_max_from(session_dir):
    """이전 세션 폴더의 A.txt 에서 A 로그 최대 cycle."""
    log = hs.WearLog()
    p = Path(session_dir) / "A.txt"
    if not p.exists():
        raise Abort(f"{p} 가 없다")
    log.feed(p.read_bytes())
    return log.max_cycle


def start_command(cycle, delta, session):
    """사람이 확인할 START 한 줄 — 보내는 것과 같은 문자열."""
    return hs.format_cmd("START", 1, base=TB_BASE, n_sectors=TB_N, pattern=PATTERN,
                         cycle=cycle, delta=delta, session=session)


# ── 세션 ──────────────────────────────────────────────────────────────────
class Run:
    def __init__(self, args):
        self.args = args
        self.session = args.session or int(time.time())
        self.dir = Path(args.logdir) / str(self.session)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ses = Session(str(self.session))
        self.ses.path = self.dir / "session.log"
        self.ser = self.link = None

    def open(self, program=False):
        a = self.args
        if a.sim:
            env = dict(os.environ)
            if a.sim_image:
                env["WEAR_FAKE_IMAGE"] = a.sim_image
            if a.sim_state:
                env["WEAR_FAKE_STATE"] = a.sim_state
            env["WEAR_FAKE_TRACE"] = str(self.dir / "fake_trace.txt")
            self.ses.log(f"sim: {a.sim}")
            transport = wl.PipeTransport([a.sim], env=env)
        else:
            import serial
            self.ser = serial.Serial(a.port, a.baud, timeout=0.5)
            reader = self.ser
            if program:
                if not WEAR_ELF.exists():
                    raise Abort(f"missing {WEAR_ELF} — vitis -s ps/scripts/build_flash_wear.py 먼저")
                self.ser.reset_input_buffer()
                pre = run_xsct([PROGRAM_G2, WEAR_ELF], self.ses, "엔진 프로그래밍 (g2_jedec + flash_wear)", ser=self.ser)
                reader = Drained(self.ser, pre)
            transport = wl.SerialTransport(self.ser, reader=reader)
        self.link = wl.WearLink(transport, timeout=a.timeout)
        return self.link

    def close(self):
        if self.link:
            self.link.close()
        if self.ser:
            self.ser.close()
        self.save()

    def save(self):
        if not self.link:
            return
        raw = [r.decode(errors="replace") for r in self.link.t.raw]
        (self.dir / "raw.txt").write_text("".join(raw))
        for kind, rows in split_rows(raw).items():
            if rows:
                (self.dir / f"{kind}.txt").write_text("\n".join(rows) + "\n")
        (self.dir / "commands.txt").write_text("\n".join(self.link.responses) + "\n")

    def expected_uid(self):
        uid = chip_registry.parse().get(self.args.chip)
        if not uid:
            raise Abort(f"등록부에 {self.args.chip} 의 UID 가 없다 (docs/chip_registry.md)")
        return uid

    def check_uid(self):
        """S-1 §8.3 1 · §4 1 — 등록부와 다르면 아무것도 하지 않는다."""
        want = self.expected_uid()
        got = self.link.uid_read()
        if got != want:
            raise Abort(f"UID 불일치 — 소켓 {got}, 등록부 {self.args.chip}={want}. P/E 를 내지 않는다")
        self.ses.log(f"UID OK: {got} = {self.args.chip}")
        return got

    def pe_row(self, sectors, delta, source, note=""):
        chip_pe.append_pe(datetime.now(timezone.utc).strftime("%Y-%m-%d"), self.args.chip,
                          self.expected_uid(), sectors, delta, source, note, path=self.args.chip_pe)
        self.ses.log(f"chip_pe: {self.args.chip} {sectors} {delta} — {source} {note}")


# ── 서브커맨드 ────────────────────────────────────────────────────────────
def cmd_accept(run):
    a = run.args
    if not a.sim and not a.i_approve_real_pe:
        raise Abort("실칩에 P/E 를 낸다 — --i-approve-real-pe 를 명시해야 START 를 보낸다 (--sim 은 예외)")
    link = run.open(program=not a.no_program)
    status = link.wear_status()
    run.ses.log(f"boot: {status}")
    if status[1] == "error":
        raise Abort("엔진이 error 로 부팅했다 (SPI/JEDEC/UID) — 배선·칩 확인. START 를 보내지 않는다")
    if status[1] == "running":
        raise Abort("엔진이 running 이다 — halt 로 세우거나 끝나기를 기다릴 것")
    uid = run.check_uid()
    cmd = start_command(a.cycle, a.delta, run.session)
    run.ses.log(f"START: {cmd}")
    print(f"START → {cmd}", file=sys.stderr)
    link.wear_start(TB_BASE, TB_N, PATTERN, a.cycle, a.delta, run.session)
    status = link.wait_stopped(timeout=a.delta * SEC_PER_CYCLE + 60)
    run.ses.log(f"stopped: {status}")
    done = status[0] - a.cycle
    if done > 0:
        run.pe_row(TB_SECTORS, f"+{done}", f"run_wear accept (session {run.session})",
                   f"cycle {a.cycle}→{status[0]}" + ("" if status[1] == "checkpoint_due" else f" · {status[1]}"))
    tally = link.tally_read()
    dumps = link.tally_dump()
    try:                                                     # 시험 버튼 — 읽기 전용, 판정은 judge_accept
        probe = link.blank_check(TB_BASE, TB_N)
    except hs.Reject as e:
        run.ses.log(f"probe BLANK 거부: {e}")
        probe = None
    n = a.cycle + a.delta
    verdict = judge_accept(link.log, status, tally, dumps, uid, run.expected_uid(), n=n, probe=probe)
    lines = [f"{'PASS' if ok else 'FAIL'}  {item:5s} {detail}" for item, ok, detail in verdict]
    if link.log.r:
        lines.append("R 행: " + " | ".join(f"{r['kind']}@{r['cycle']}" for r in link.log.r))
    (run.dir / "verdict.txt").write_text("\n".join(lines) + "\n")
    for ln in lines:
        run.ses.log(ln)
    print("\n".join(lines))
    print(f"세션 로그: {run.dir}")
    return 0 if all(ok for _, ok, _ in verdict) else 1


def cmd_resume(run):
    a = run.args
    if a.host_log_max is None and not a.from_session:
        raise Abort("--host-log-max N 또는 --from-session <이전 세션 폴더> 가 필요하다 (A 로그의 최대 cycle)")
    host_max = a.host_log_max if a.host_log_max is not None else host_log_max_from(a.from_session)
    link = run.open(program=not a.no_program)
    if link.wear_status()[1] == "running":
        raise Abort("엔진이 running 이다 — halt 로 세울 것")
    run.check_uid()                                                       # §8.3 1
    info = link.wear_resume()                                             # §8.3 2 — recovering
    verdict, restored = hs.decide_resume(info, host_max)                  # §8.3 3·4
    out = [f"tally_a={info.tally_a} tally_b={info.tally_b} mismatch={info.mismatch} "
           f"next_byte={info.next_byte} write_ok={info.write_ok} host_log_max={host_max}",
           f"판정 {verdict} 채택값 {restored}"]
    if restored is None:
        out.append("사람을 부른다 — START 를 보내지 않는다")
    else:
        bc = link.blank_check(TB_BASE, TB_N)                              # §8.3 5
        out.append(f"blank_check 잔류 {bc.erase_residual_bits} program_fail {bc.program_fail_bits} "
                   f"addr_count {bc.addr_count} worst_page {bc.worst_page_idx}/{bc.worst_page_bits}")
        if bc.erase_residual_bits:
            rr = link.reerase(TB_BASE, TB_N, timeout=a.timeout + 30)
            after = link.blank_check(TB_BASE, TB_N)
            sectors = sorted({r["sector"] for r in link.log.r if r["kind"] == "reerase"})
            out.append(f"reerase ok={rr.ok} t_erase_us={rr.t_erase_us} resid_after={rr.resid_after} "
                       f"섹터 {sectors} → 재확인 잔류 {after.erase_residual_bits}")
            for s in sectors:
                run.pe_row(str(s), "±1", f"run_wear resume (session {run.session})", "reerase · ±1")
            if not rr.ok or after.erase_residual_bits:
                out.append("재소거 뒤에도 잔류 — 사람을 부른다. START 를 보내지 않는다")
                restored = None
        if restored is not None:
            out.append(f"다음 명령 (사람이 친다): run_wear.py accept --cycle {restored} --delta <n> --i-approve-real-pe")
    (run.dir / "resume.txt").write_text("\n".join(out) + "\n")
    for ln in out:
        run.ses.log(ln)
    print("\n".join(out))
    return 0 if restored is not None else 2


def cmd_tally_erase(run):
    """tally 두 벌(512·1,536) 소거 — 같은 칩으로 0 부터 다시 시작할 때. 자물쇠 셋:
    ① --i-approve-tally-erase ② 사람이 그 칩의 UID 를 직접 타이핑 ③ 지우기 전 값을 chip_pe.md 에 먼저 적는다
    (장부 기입이 실패하면 소거를 보내지 않는다). 엔진 쪽 자물쇠(idle · UID 대조)는 flash_wear.c."""
    a = run.args
    if not a.sim and not a.i_approve_tally_erase:
        raise Abort("tally 를 지운다 — --i-approve-tally-erase 를 명시해야 한다 (--sim 은 예외)")
    link = run.open(program=not a.no_program)
    status = link.wear_status()
    run.ses.log(f"boot: {status}")
    if status[1] != "idle":
        raise Abort(f"엔진이 {status[1]} 이다 — TALLY_ERASE 는 idle(부팅 직후)에서만. 리셋 뒤 다시")
    uid = run.check_uid()
    ta, tb, m = link.tally_read()
    ledger = [ln for ln in Path(a.chip_pe).read_text(encoding="utf-8").splitlines() if f"| {a.chip} |" in ln]
    print(f"칩 {a.chip} uid={uid}")
    print(f"지울 tally: a={ta // 100} b={tb // 100} 바이트 (사이클 {ta}/{tb}){' · 두 벌 불일치' if m else ''}")
    print(f"chip_pe.md 의 {a.chip} 이력 (최근 5행):")
    print("\n".join(ledger[-5:]) or "(없음)")
    print("tally 두 벌(512·1,536)을 소거한다 — 칩이 스스로 기억하는 마모 눈금이 지워진다.")
    print("진행하려면 이 칩의 UID 를 그대로 입력 (다르면 지우지 않는다):")
    try:
        typed = input("UID> ").strip().upper()
    except EOFError:
        typed = ""
    if typed != uid:
        raise Abort(f"입력 {typed or '(빈 값)'} ≠ 소켓 {uid} — 지우지 않는다")
    for s in (512, 1536):                                            # ③ 장부가 먼저 — 칩의 기억을 옮긴다
        run.pe_row(str(s), "+1", f"run_wear tally-erase (session {run.session})",
                   f"tally erase · 지운 값 a={ta // 100} b={tb // 100}")
    r = link.tally_erase(uid)
    line = (f"tally 소거: 지운 값 a={r.count_a // 100} b={r.count_b // 100} t_erase_us={r.t_erase_us} "
            f"clean={int(r.clean)}" + ("" if r.clean else " — 소거 뒤에도 0xFF 가 아니다, 엔진은 error 로 앉았다"))
    run.ses.log(line)
    print(line)
    return 0 if r.clean else 1


def cmd_simple(run):
    a = run.args
    link = run.open()
    if a.cmd == "status":
        c, s, d, lr = link.wear_status()
        print(f"cycle={c} state={s} defect_seen={int(d)} last_reject={lr}")
    elif a.cmd == "halt":
        link.halt()                                                       # OK 는 다음 사이클 경계에서 온다
        c, s, _, _ = link.wait_stopped(timeout=60)
        print(f"halted: cycle={c} state={s}  → 이어 가려면 accept --cycle {c} --delta <n>")
    elif a.cmd == "tally":
        ta, tb, m = link.tally_read()
        print(f"tally_a={ta // 100} tally_b={tb // 100} (바이트) mismatch={int(m)} → 사이클 {ta}/{tb}")
    elif a.cmd == "dump":
        for i, d in enumerate(link.tally_dump()):
            p = run.dir / f"tally_{i}.hex"
            p.write_text(d.hex())
            odd = {b for b in d if b not in (0x00, 0xFF)}
            print(f"copy {i}: 0x00 {d.count(0)}개, 0x00/0xFF 외 값 {sorted(odd)} → {p}")
    elif a.cmd == "uid":
        uid = link.uid_read()
        print(f"uid={uid} 등록부={chip_registry.label_for(uid) or '(없음)'}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("cmd", choices=("accept", "status", "halt", "resume", "tally", "dump", "uid", "tally-erase"))
    link = ap.add_argument_group("링크")
    link.add_argument("--port", default="/dev/ttyUSB1", help="Windows 는 COM<N>")
    link.add_argument("--baud", type=int, default=921600)
    link.add_argument("--sim", metavar="BIN", help="호스트 시뮬레이션 바이너리 (build/sim/flash_wear_sim) — 실칩 대신")
    link.add_argument("--sim-image", help="fake NOR 초기 이미지 (테스트용)")
    link.add_argument("--sim-state", help="fake NOR 상태 파일 (테스트용)")
    link.add_argument("--timeout", type=float, default=wl.CMD_TIMEOUT_S, help="명령 응답 대기 초")
    ap.add_argument("--no-program", action="store_true", help="accept/resume 에서 xsct 프로그래밍 생략")
    ap.add_argument("--chip", default=PILOT_CHIP, help="등록부 라벨 — UID 대조 (기본 파일럿 chip01)")
    ap.add_argument("--session", type=int, help="세션 id (UTC epoch 초). 생략하면 지금")
    ap.add_argument("--logdir", default=str(LOG_ROOT))
    ap.add_argument("--chip-pe", default=str(chip_pe.CHIP_PE), help="증분 기입 파일 (기본 docs/chip_pe.md)")
    acc = ap.add_argument_group("accept")
    acc.add_argument("--cycle", type=int, default=0, help="누적 현재값 — 신규 0, 복구 뒤 채택값")
    acc.add_argument("--delta", type=int, default=100, help="이번 구간에 추가로 돌릴 횟수")
    acc.add_argument("--i-approve-real-pe", action="store_true",
                     help="실칩에 P/E 를 내는 것을 승인한다 — 없으면 START 를 보내지 않는다")
    te = ap.add_argument_group("tally-erase")
    te.add_argument("--i-approve-tally-erase", action="store_true",
                    help="tally 두 벌 소거를 승인한다 — 그래도 UID 를 직접 타이핑해야 지운다")
    res = ap.add_argument_group("resume")
    res.add_argument("--host-log-max", type=int, help="호스트 A 로그의 최대 cycle")
    res.add_argument("--from-session", help="이전 세션 폴더 — A.txt 에서 최대 cycle 을 읽는다")
    args = ap.parse_args(argv)
    if args.cmd == "accept" and args.delta < 0:
        ap.error("--delta 는 0 이상")
    if args.cmd in ("accept", "tally-erase") and not args.sim and not args.no_program:
        require_tty(f"실칩 {args.cmd} 는 사람이 보는 자리에서")
    run = Run(args)
    try:
        rc = {"accept": cmd_accept, "resume": cmd_resume, "tally-erase": cmd_tally_erase}.get(args.cmd, cmd_simple)(run)
    except (Abort, hs.Reject, TimeoutError, ConnectionError) as e:
        run.ses.log(str(e))
        print(f"중단: {e}", file=sys.stderr)
        rc = 3
    finally:
        run.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
