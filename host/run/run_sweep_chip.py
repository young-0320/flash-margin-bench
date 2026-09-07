#!/usr/bin/env python3
"""실칩 스윕 래퍼 — 한 프로세스가 UART 를 쥔 채 세션 1(flash_prep) → 세션 2(스윕 ×N) 를 잇는다.

왜 래퍼인가 (로그 23 §0): UID(4Bh) 를 읽는 것은 세션 1(g2_jedec 비트스트림, PS SPI) 이고
CSV 를 만드는 것은 세션 2(g3_chip_<mhz>, PL) 다. 사람이 중간에 끼면 UID 가 파일에 닿지
못한다. 이 스크립트가 둘을 한 시간 안에 두고, 세션 1 이 준 UID 로 등록부에서 라벨을
역조회해 캡처에 넘긴다. 라벨은 사람이 입력하지 않는다.

    [시작]  사람이 chip 을 꽂아둔 상태
      세션1  program_g2 + flash_prep  →  #PREP UID → 라벨 역조회 → chip_pe.md +1
      세션2  program_g3 + 스윕        →  CSV 2개   (×N, --reseat 면 회차 사이 재장착 프롬프트)
    [종료]  "k/N 완료" 요약 + build/data/session_<label>_<uid>_<batch_id>.log

제약 — **배치 중 칩이 바뀌지 않는다고 가정한다.** UID 를 배치 시작 시 한 번만 읽고 그 값을
배치 전체 CSV 에 박는다 (로그 23 부록 A). 여러 칩을 다루는 배치는 run_newchip.py 가 맡으며,
거기서는 재장착마다 UID 재확인이 필요하다 (UID 전용 소형 앱 flash_uid.c — W5-M 에서).

두지 않는 옵션 (로그 23 §7): --skip-prep-check 류(안전장치 해제) · --dphi(VCO 고정) ·
--steps(--mhz 가 정함) · --target(라벨은 등록부가 답한다).

의존: xsct(PATH), pyserial, host/capture/{sweep_uart_capture,chip_registry}.py
"""

import argparse
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import serial

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "capture"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_pe                                       # noqa: E402
import chip_registry                                 # noqa: E402
import sweep_uart_capture as cap                     # noqa: E402

PREP_ELF = REPO / "build" / "vitis_prep" / "flash_prep" / "build" / "flash_prep.elf"
PROGRAM_G2 = REPO / "ps" / "scripts" / "program_g2.tcl"
PROGRAM_G3 = REPO / "ps" / "scripts" / "program_g3.tcl"
PREP_SECTORS = "0~127"        # flash_prep N_PAGES=2048 × 256B = 128 섹터 전 범위 고정
PREP_TIMEOUT_S = 15 * 60      # 지우기+쓰기+검증 ~1분. 넉넉히


class Abort(SystemExit):
    pass


class Session:
    """세션 로그 — 라벨·UID 를 알기 전엔 메모리에 쌓고, 알면 파일로 내린다."""

    def __init__(self, batch_id):
        self.batch_id = batch_id
        self.buf = []
        self.path = None

    def log(self, msg):
        line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
        print(line, file=sys.stderr)
        self.write(line)

    def write(self, text):          # 화면에 안 찍고 로그에만 (xsct 출력 등)
        if self.path:
            with open(self.path, "a") as f:
                f.write(text + "\n")
        else:
            self.buf.append(text)

    def open(self, name):
        self.path = cap.DEFAULT_OUTDIR / f"session_{name}_{self.batch_id}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "a") as f:
            f.write("\n".join(self.buf) + "\n")
        self.buf = []


def run_xsct(args, ses, what):
    """xsct 는 tcl error 에서 exit 1 을 준다 (2026-09-07 실측). 비영이면 배치 중단."""
    cmd = ["xsct", *map(str, args)]
    ses.log(f"{what}: {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10 * 60)
    ses.write(r.stdout)
    if r.returncode != 0:
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
        raise Abort(f"{what} 실패 (xsct exit {r.returncode}) — 즉시 중단\n{tail}")


def require_tty(why):
    if not sys.stdin.isatty():
        raise Abort(f"{why} — stdin 이 tty 가 아니다. 사람이 해야 하는 단계다")


def run_prep(ser, ses):
    """세션 1. #PREP PASS + UID 가 있어야 돌아온다. 그 외 전부 중단."""
    if not PREP_ELF.exists():
        raise Abort(f"missing {PREP_ELF} — vitis -s ps/scripts/build_flash_prep.py 먼저")
    ser.reset_input_buffer()               # rst -system 이전의 잔여물. 이후 쓰레기는 접두로 거른다
    run_xsct([PROGRAM_G2, PREP_ELF], ses, "세션1 프로그래밍 (g2_jedec + flash_prep)")

    uid = None
    deadline = datetime.now(timezone.utc).timestamp() + PREP_TIMEOUT_S
    while datetime.now(timezone.utc).timestamp() < deadline:
        raw = ser.readline().decode(errors="replace").strip()
        i = raw.find("#PREP")
        if i < 0:
            continue
        line = raw[i:]
        ses.log(line)
        tok = line.split()
        if len(tok) < 2:
            continue
        if len(tok) >= 3 and tok[1] == "UID":
            uid = chip_registry.normalize_uid(tok[2])
        elif tok[1] == "PASS":
            if uid is None:
                raise Abort("#PREP PASS 인데 #PREP UID 가 없다 — flash_prep.c 가 4Bh 판인지 확인")
            return uid
        elif tok[1] in ("FAIL", "ERROR"):
            raise Abort(f"flash_prep 실패: {line} — 스윕으로 넘어가지 않는다")
    raise Abort(f"flash_prep {PREP_TIMEOUT_S}s 내 미완료 — 보드/UART 확인")


def resolve_label(uid, ses, today):
    """등록부 역조회. 없으면 신규 칩 — 사람에게 라벨을 물어 공란 행을 채운다."""
    label = chip_registry.label_for(uid)
    if label:
        ses.log(f"등록부: {uid} → {label}")
        return label
    require_tty(f"UID {uid} 는 등록부에 없다 (신규 칩). 라벨 입력 필요")
    free = [l for l, u in chip_registry.parse().items() if u is None]
    print(f"\n신규 UID {uid}. 등록부의 UID 공란 라벨: {' '.join(free) or '(없음)'}", file=sys.stderr)
    label = input("이 칩의 라벨 (chipNN): ").strip()
    chip_registry.register(label, uid, today)      # 규칙 위반이면 여기서 SystemExit
    ses.log(f"등록부 기입: {label} ← {uid} (docs/chip_registry.md — git diff 로 확인할 것)")
    return label


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_argument_group("측정 설계")
    g.add_argument("--repeat", type=int, default=1, metavar="N", help="스윕 반복 횟수 (1/3/5 …)")
    g.add_argument("--reseat", action="store_true", help="매 회차 사이 재장착 프롬프트. 배치 전체 reseat=1")
    g.add_argument("--n-reads", type=int, default=100, choices=(100, 112, 448),
                   help="기대 N. ELF 의 BEGIN n= 과 다르면 중단 (N 은 빌드 시 고정 — 여기서 못 바꾼다)")
    g.add_argument("--base-sector", type=int, default=0,
                   help="수정안 #1 승인 시. 미승인이므로 0 만 허용")
    h = ap.add_argument_group("하드웨어")
    h.add_argument("--mhz", type=int, default=25, choices=(25, 45, 75))
    h.add_argument("--pl", type=int, choices=(4, 6), help="PAY_LEAD 보험 비트스트림 (pl4|pl6)")
    h.add_argument("--port", default="/dev/ttyUSB1")
    h.add_argument("--baud", type=int, default=115200)
    p = ap.add_argument_group("절차")
    p.add_argument("--no-prep", action="store_true",
                   help="사전 쓰기 생략 (비휘발). UID 를 읽을 세션이 없으므로 --uid 필수")
    p.add_argument("--uid", help="--no-prep 전용: 이 배치의 칩 UID (등록부에 있어야 함)")
    p.add_argument("--prep-only", action="store_true", help="flash_prep 만 돌리고 종료")
    p.add_argument("--blind", action="store_true", help="chip_pe.md 에 증분 대신 (봉인)")
    args = ap.parse_args()

    if args.base_sector != 0:
        ap.error("--base-sector: 수정안 #1 미승인 — 0 만 허용")
    if args.repeat < 1:
        ap.error("--repeat 는 1 이상")
    if args.no_prep and args.prep_only:
        ap.error("--no-prep 과 --prep-only 는 함께 쓸 수 없다")
    if args.no_prep != bool(args.uid):
        ap.error("--uid 는 --no-prep 과 함께, 그때만 쓴다")
    if not shutil.which("xsct"):
        raise Abort("xsct 가 PATH 에 없다 — Vitis 2024.2 settings64.sh 를 source 할 것")
    chip_registry.parse()                     # 등록부가 깨져 있으면 보드를 건드리기 전에 죽는다
    if args.reseat and args.repeat > 1:
        require_tty("--reseat 는 재장착 프롬프트가 필요")

    now = datetime.now(timezone.utc)
    batch_id = cap.utc_stamp(now)
    today = now.strftime("%Y-%m-%d")
    ses = Session(batch_id)
    ses.log(f"batch {batch_id}: mhz={args.mhz} pl={args.pl} repeat={args.repeat} "
            f"reseat={int(args.reseat)} n_reads={args.n_reads} blind={int(args.blind)}")

    done = invalid = 0
    label = uid = None
    try:
        # 포트는 프로그래밍 전에 연다 — 앱이 con 직후 찍는 첫 줄(#PREP JEDEC / #G0 BEGIN)을
        # 놓치지 않기 위해. rst 쓰레기는 접두 필터가 거른다 (런북 3 의 캡처-먼저 순서와 같다)
        with serial.Serial(args.port, args.baud, timeout=2) as ser:
            if args.no_prep:
                uid = chip_registry.normalize_uid(args.uid)
                label = chip_registry.label_for(uid)
                if label is None:
                    raise Abort(f"--uid {uid} 는 등록부에 없다. 신규 칩은 prep 을 돌려 기계가 읽은 UID 로만 등록한다")
                ses.open(f"{label}_{uid}")
                ses.log(f"--no-prep: 사람이 준 UID {uid} → {label} (기계 확인 없음 — 세션 규칙에 의존)")
            else:
                try:
                    uid = run_prep(ser, ses)
                except Abort:
                    ses.open("prepfail")
                    raise
                label = resolve_label(uid, ses, today)
                ses.open(f"{label}_{uid}")
                chip_pe.append_pe(today, label, uid, PREP_SECTORS, "+1",
                                  f"flash_prep (batch {batch_id})", blind=args.blind)
                ses.log(f"chip_pe.md: {label} {PREP_SECTORS} {'(봉인)' if args.blind else '+1'}")
                if args.prep_only:
                    ses.log("--prep-only: 종료")
                    return

            g3_args = [PROGRAM_G3, args.mhz] + ([f"pl{args.pl}"] if args.pl else [])
            for k in range(1, args.repeat + 1):
                if k > 1 and args.reseat:
                    input(f"\n[{k}/{args.repeat}] {label} 을 빼고 다시 꽂은 뒤 엔터: ")
                    ses.log(f"[{k}/{args.repeat}] 재장착 확인")
                ser.reset_input_buffer()
                run_xsct(g3_args, ses, f"[{k}/{args.repeat}] 세션2 프로그래밍 (g3_chip_{args.mhz})")
                r = cap.capture_sweep(ser, label, uid, reseat=int(args.reseat),
                                      repeat_idx=k, batch_id=batch_id, log=sys.stderr)
                ses.log(f"[{k}/{args.repeat}] {'VALID' if r.valid else 'INVALID'} "
                        f"{r.main_path.name} ({r.n_main} rows)")
                done += 1
                if not r.valid:
                    invalid += 1
                    continue
                n = int(r.begin.get("n", 0))
                if n != args.n_reads:
                    raise Abort(f"요청 N={args.n_reads} 인데 ELF 는 n={n} — 파일은 남겼다 "
                                f"(n_reads 열이 진실). N 은 g0_sweep.c 상수라 빌드를 바꿔야 한다")
    except KeyboardInterrupt:
        ses.log("Ctrl-C — 배치 중단")
    except Abort as e:
        ses.log(str(e))
        ses.log(f"{done}/{args.repeat} 완료 (invalid {invalid}) — 중단")
        raise
    ses.log(f"{done}/{args.repeat} 완료 (invalid {invalid})")
    sys.exit(0 if done == args.repeat and invalid == 0 else 1)


if __name__ == "__main__":
    main()
