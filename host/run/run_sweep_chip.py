#!/usr/bin/env python3
"""실칩 측정 래퍼 — 한 프로세스가 UART 를 쥔 채 세션 1(flash_prep) → 세션 2(스윕 ×N) → 분석을 잇는다.

    run_sweep_chip.py --mode newchip --mhz 25 --n-reads 112              신품 첫 투입 (prep = P/E +1)
    run_sweep_chip.py --mode sweep --chip chip02 --repeat 3 --reseat     재측정 (P/E 불변)

--mode 가 '무엇을 하는가'(= P/E 를 쓰는가)를, 나머지 옵션이 '어떻게'를 정한다. 모드가 정한 것은
옵션으로 뒤집지 못한다 — newchip 에 --chip 을 줄 수 없고(기계가 UID 를 읽는다), sweep 은 prep 을
켤 수 없다. 앵커 재측정에서 prep 생략을 빠뜨려 칩을 한 번 더 마모시키던 사고를 막는다.

sweep 모드도 세션 1 을 돈다 — 쓰기를 하지 않는 flash_id 로 UID 만 읽어 --chip 과 대조하고,
어긋나면 스윕 전에 중단한다 (2026-09-16). --chip 은 선언이 아니라 검증이다. 남는 한계:
대조는 "다른 칩을 꽂았다" 만 잡고 "재장착을 안 했다" 는 못 잡는다 — 재장착 σ 의 신뢰는
여전히 사람 손에 있다 (로그 23 부록 A).

왜 래퍼인가 (로그 23 §0): UID(4Bh) 를 읽는 것은 세션 1(g2_jedec 비트스트림, PS SPI) 이고
CSV 를 만드는 것은 세션 2(g3_chip_<mhz>, PL) 다. 사람이 중간에 끼면 UID 가 파일에 닿지
못한다. 이 스크립트가 둘을 한 시간 안에 두고, 세션 1 이 준 UID 로 등록부에서 라벨을
역조회해 캡처에 넘긴다. 라벨은 사람이 입력하지 않는다.

    [시작]  사람이 chip 을 꽂아둔 상태
      세션1  newchip: program_g2 + flash_prep  →  #PREP UID → 라벨 역조회 → chip_pe.md +1
             sweep  : program_g2 + flash_id    →  #G2 UID   → --chip 과 대조 (P/E 불변)
      세션2  program_g3 + 스윕        →  CSV 2개   (×N, --reseat 면 회차 사이 재장착 프롬프트)
    [종료]  "k/N 완료" 요약 + build/data/session_<label>_<uid>_<batch_id>.log
            (로그는 시작부터 session_<batch_id>.log 로 쓰이다가 라벨을 알면 개명된다)

제약 — **배치 중 칩이 바뀌지 않는다고 가정한다.** UID 를 배치 시작 시 한 번만 읽고 그 값을
배치 전체 CSV 에 박는다 (로그 23 부록 A). 여러 칩을 다루는 배치는 run_newchip.py 가 맡으며,
거기서는 재장착마다 UID 재확인이 필요하다 (여기 세션 1 이 쓰는 flash_id 를 그대로 쓰면 된다).

두지 않는 옵션 (로그 23 §7): --skip-prep-check 류(안전장치 해제) · --dphi(VCO 고정) ·
--steps(--mhz 가 정함) · --target(라벨은 등록부가 답한다).

의존: xsct(PATH), pyserial, host/capture/{sweep_uart_capture,chip_registry}.py
"""

import argparse
import os
import re
import shutil
import subprocess
import threading
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
ID_ELF = REPO / "build" / "vitis_id" / "flash_id" / "build" / "flash_id.elf"
PROGRAM_G2 = REPO / "ps" / "scripts" / "program_g2.tcl"
PROGRAM_G3 = REPO / "ps" / "scripts" / "program_g3.tcl"
PREP_SECTORS = "0~127"        # flash_prep N_PAGES=2048 × 256B = 128 섹터 전 범위 고정
PREP_TIMEOUT_S = 15 * 60      # 지우기+쓰기+검증 ~1분. 넉넉히
ID_TIMEOUT_S = 60             # flash_id 는 JEDEC+UID 만 읽는다 — 즉시


class Abort(SystemExit):
    pass


class Session:
    """세션 로그 — 시작부터 디스크에 쓴다 (session_<batch_id>.log). 라벨·UID 를 알면 이름만
    바꾼다. 메모리 버퍼를 두지 않으므로 Ctrl-C·예외·강제 종료 어느 경우에도 그 순간까지의
    기록(#PREP UID 포함)이 남는다 (로그 25 중요 2)."""

    def __init__(self, batch_id):
        self.batch_id = batch_id
        self.path = cap.DEFAULT_OUTDIR / f"session_{batch_id}.log"
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, msg):
        line = f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}"
        print(line, file=sys.stderr)
        self.write(line)

    def write(self, text):          # 화면에 안 찍고 로그에만 (xsct 출력 등)
        with open(self.path, "a") as f:
            f.write(text + "\n")

    def rename(self, name):
        self.path = self.path.rename(self.path.with_name(f"session_{name}_{self.batch_id}.log"))


class Drained:
    """xsct 구간에 미리 읽어 둔 바이트를 먼저 흘려보내는 시리얼 래퍼 (readline 만 가로챈다)."""

    def __init__(self, ser, buf):
        self._ser, self._buf = ser, bytes(buf)
        self.port, self.baudrate = ser.port, ser.baudrate

    def readline(self):
        if not self._buf:
            return self._ser.readline()
        i = self._buf.find(b"\n")
        if i < 0:                               # 개행 없는 꼬리는 포트에서 온 다음 조각과 이어 붙인다
            tail, self._buf = self._buf, b""
            return tail + self._ser.readline()
        line, self._buf = self._buf[:i + 1], self._buf[i + 1:]
        return line


def xsct_cmd():
    """Windows 의 xsct 는 .bat 다. CreateProcess 는 .exe 만 자동으로 붙이므로 cmd /c 로 감싼다
    (reproduce.py tool() 과 같은 자리 — shutil.which 는 PATHEXT 를 보므로 선검사만 통과한다)."""
    p = shutil.which("xsct")
    if p and os.name == "nt" and p.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", p]
    return [p or "xsct"]


WIDTH_LINE = re.compile(r"width @ BER=0\.01\s*:\s*([\d.]+)")


def analyze(csv_path, ses):
    """스윕 CSV 를 그 자리에서 분석한다. 측정과 분석의 실패를 가른다 —
    분석이 깨져도 CSV 는 이미 디스크에 있고, 나중에 다시 돌리면 그만이다."""
    cmd = [sys.executable, str(REPO / "host" / "analysis" / "bathtub_analysis.py"),
           str(csv_path), "--json"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    ses.write(r.stdout + r.stderr)
    if r.returncode != 0:
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-5:])
        ses.log(f"  분석 실패 (exit {r.returncode}) — 측정 원본은 남아 있다: {csv_path.name}")
        print(f"  분석 실패 — 측정은 유효하다. 나중에 직접: "
              f"bathtub_analysis.py {csv_path}\n{tail}", file=sys.stderr)
        return
    m = WIDTH_LINE.search(r.stdout)
    checks = [l.strip() for l in r.stdout.splitlines() if "FAIL" in l]
    ses.log(f"  분석 OK width@1e-2={m.group(1) if m else '?'} ps"
            + (f" — 체크 FAIL {len(checks)}건" if checks else ""))
    print(f"  분석 OK  width@1e-2 = {m.group(1) if m else '?'} ps"
          + (f"   ** 체크리스트 FAIL {len(checks)}건 — 로그 확인 **" if checks else ""))


def run_xsct(args, ses, what, ser=None):
    """xsct 는 tcl error 에서 exit 1 을 준다 (2026-09-07 실측). 비영이면 배치 중단.

    ser 를 주면 xsct 가 도는 동안 UART 를 계속 읽어 반환한다. 보드는 ELF 가 뜨는 순간부터
    뿜는데 호스트가 xsct 종료를 기다리느라 안 읽으면 커널·FTDI 버퍼(≈10KB = 6~7스텝)가
    넘쳐 그 구간이 통째로 사라진다 — 2026-09-15 chip02 에서 19스텝 결측(무효 ⑤)으로 실현됐다.
    UART 이용률이 98% 라 여유가 없어서, 읽지 않는 시간이 곧 유실이다."""
    cmd = xsct_cmd() + [str(a) for a in args]
    ses.log(f"{what}: {' '.join(cmd)}")
    buf = bytearray()
    stop = threading.Event()

    def drain():                                 # 포트가 사라지면 조용히 끝낸다 — 판정은 캡처가 한다
        try:
            while not stop.is_set():
                buf.extend(ser.read(4096))       # timeout 만큼만 블록
        except Exception:
            pass

    th = threading.Thread(target=drain, daemon=True) if ser else None
    if th:
        th.start()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10 * 60)
    finally:
        if th:
            stop.set()
            th.join(timeout=5)
            if th.is_alive():                    # 포트를 두 곳에서 읽는 상태로 캡처에 들어가지 않는다
                raise Abort("UART 드레인 스레드가 안 멈춘다 — 포트 상태 확인 후 재시도")
    if buf:
        ses.log(f"  xsct 구간 UART 선수신 {len(buf)}B (버퍼 넘침 방지)")
    ses.write(r.stdout)
    if r.returncode != 0:
        tail = "\n".join((r.stdout + r.stderr).strip().splitlines()[-8:])
        raise Abort(f"{what} 실패 (xsct exit {r.returncode}) — 즉시 중단\n{tail}")
    return bytes(buf)


def require_tty(why):
    if not sys.stdin.isatty():
        raise Abort(f"{why} — stdin 이 tty 가 아니다. 사람이 해야 하는 단계다")


def run_prep(ser, ses):
    """세션 1. #PREP PASS + UID 가 있어야 돌아온다. 그 외 전부 중단."""
    if not PREP_ELF.exists():
        raise Abort(f"missing {PREP_ELF} — vitis -s ps/scripts/build_flash_prep.py 먼저")
    ser.reset_input_buffer()               # rst -system 이전의 잔여물. 이후 쓰레기는 접두로 거른다
    src = Drained(ser, run_xsct([PROGRAM_G2, PREP_ELF], ses,
                                "세션1 프로그래밍 (g2_jedec + flash_prep)", ser=ser))

    uid = None
    deadline = datetime.now(timezone.utc).timestamp() + PREP_TIMEOUT_S
    while datetime.now(timezone.utc).timestamp() < deadline:
        raw = src.readline().decode(errors="replace").strip()
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


def verify_uid(ser, ses, uid, label, what):
    """flash_id 로 소켓의 칩을 확인한다 — 읽기만 하므로 P/E 불변.

    배치 시작뿐 아니라 **재장착 직후에도** 건다. 로그 23 부록 A 가 지목한 위험이
    "재장착 사이에 다른 칩이 들어갔다" 였고, 그때는 책상에 칩이 하나뿐이라 성립하지
    않았다. W10-M 은 10개가 널려 있고 앵커를 사이사이 끼우므로 성립한다.

    세션 로그를 idfail 로 개명하는 것은 **UID 불일치일 때뿐이다.** 그 이름은 "꽂힌 칩이
    다르다" 를 뜻해야 한다 — ELF 누락·flash_id FAIL·타임아웃까지 같은 이름으로 남기면
    나중에 그 파일을 칩을 잘못 집은 기록으로 읽는다 (2026-09-16 15:17 실제로 ELF 누락이
    idfail 로 남았다). 그쪽 실패는 기본 이름 session_<batch_id>.log 로 둔다.
    개명이 여기 있으므로 **재장착 후 대조도 같은 규칙을 따른다** — 호출부에 두면
    배치 시작에만 붙고 재장착 쪽은 빠진다."""
    read = run_id(ser, ses)
    if read != uid:
        other = chip_registry.label_for(read)
        ses.rename("idfail")
        raise Abort(f"{what} 칩 대조 실패 — 소켓의 칩이 {label} 이 아니다. 스윕을 시작하지 않는다\n"
                    f"    읽은 UID : {read} ({other or '등록부에 없는 칩'})\n"
                    f"    기대 UID : {uid} ({label})")
    ses.log(f"{what} 칩 대조 OK: {label} ({uid})")


def run_id(ser, ses):
    """세션 1 (sweep 모드). flash_id 가 읽은 UID 를 돌려준다. 그 외 전부 중단.

    flash_prep 과 달리 이 앱은 플래시에 쓰기 명령을 내보내지 않는다 — P/E 불변이다."""
    if not ID_ELF.exists():
        raise Abort(f"missing {ID_ELF} — vitis -s ps/scripts/build_flash_id.py 먼저")
    ser.reset_input_buffer()               # rst -system 이전의 잔여물. 이후 쓰레기는 접두로 거른다
    src = Drained(ser, run_xsct([PROGRAM_G2, ID_ELF], ses,
                                "세션1 프로그래밍 (g2_jedec + flash_id)", ser=ser))

    deadline = datetime.now(timezone.utc).timestamp() + ID_TIMEOUT_S
    while datetime.now(timezone.utc).timestamp() < deadline:
        raw = src.readline().decode(errors="replace").strip()
        i = raw.find("#G2")
        if i < 0:
            continue
        line = raw[i:]
        ses.log(line)
        tok = line.split()
        if len(tok) < 2:
            continue
        if tok[1] == "ERROR" or "[FAIL]" in line:
            raise Abort(f"flash_id 실패: {line} — 스윕으로 넘어가지 않는다")
        if len(tok) >= 3 and tok[1] == "UID":
            return chip_registry.normalize_uid(tok[2])
    raise Abort(f"flash_id {ID_TIMEOUT_S}s 내 #G2 UID 없음 — 보드/UART 확인")


def resolve_label(uid, ses, today):
    """등록부 역조회. 없으면 신규 칩 — 사람에게 라벨을 물어 공란 행을 채운다."""
    label = chip_registry.label_for(uid)
    if label:
        ses.log(f"등록부: {uid} → {label}")
        return label
    require_tty(f"UID {uid} 는 등록부에 없다 (신규 칩). 라벨 입력 필요")
    free = [l for l, u in chip_registry.parse().items() if u is None]
    print(f"\n신규 UID {uid}. 등록부의 UID 공란 라벨: {' '.join(free) or '(없음)'}", file=sys.stderr)
    while True:                                    # 오타로 죽지 않는다 — prep 은 이미 끝났다
        label = input("이 칩의 라벨 (chipNN): ").strip()
        if label in free:
            break
        print(f"  {label!r} 는 후보가 아니다. 후보: {' '.join(free) or '(없음)'}", file=sys.stderr)
    chip_registry.register(label, uid, today)
    ses.log(f"등록부 기입: {label} ← {uid} (docs/chip_registry.md — git diff 로 확인할 것)")
    return label


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    # --mode 가 '무엇을 하는가'(= P/E 를 쓰는가)를, 나머지 옵션이 '어떻게'를 정한다.
    # 모드가 정한 것은 옵션으로 뒤집지 못한다 — parse_args 아래 검증이 그 역할이다.
    # 앵커 재측정에서 prep 생략을 빠뜨려 칩을 한 번 더 마모시키던 사고
    # (2026-09-15 chip02: 하루 4회)를 표현 불가능하게 만드는 것이 목적이다
    ap.add_argument("--mode", required=True, choices=("newchip", "sweep"),
                    help="newchip: prep(P/E +1) + 스윕 + 분석  |  sweep: 스윕 + 분석 (P/E 불변)")
    w = ap.add_argument_group("칩 지정 (sweep 전용)")
    who = w.add_mutually_exclusive_group()
    who.add_argument("--chip", help="등록부의 라벨 (chip02) — UID 는 역조회 후 flash_id 로 대조한다")
    who.add_argument("--uid", help="UID 직접 지정 (16hex)")
    g = ap.add_argument_group("측정 설계")
    g.add_argument("--repeat", type=int, default=1, metavar="N", help="스윕 반복 횟수 (1/3/5 …)")
    g.add_argument("--reseat", action="store_true",
                   help="매 회차 사이 재장착 프롬프트. 배치 전체 reseat=1")
    g.add_argument("--n-reads", type=int, default=112, choices=(100, 112, 448),
                   help="기대 N. BEGIN 의 n= 과 다르면 그 자리에서 중단 (N 은 빌드 시 고정). "
                        "실칩 g3 는 112 다 — build_g3_sweep.py 가 그렇게 치환한다")
    g.add_argument("--base-sector", type=int, default=0,
                   help="수정안 #1 승인 시. 미승인이므로 0 만 허용")
    h = ap.add_argument_group("하드웨어")
    h.add_argument("--mhz", type=int, default=25, choices=(25, 45, 75))
    h.add_argument("--pl", type=int, choices=(4, 6), help="PAY_LEAD 보험 비트스트림 (pl4|pl6)")
    h.add_argument("--port", default="/dev/ttyUSB1", help="Windows 는 COM<N>")
    h.add_argument("--baud", type=int, default=921600,
                   help="전 앱이 925,925bps 로 맞춘다 (차이 +0.47%%). 구형 ELF 는 115200")
    ap.add_argument("--no-analyze", action="store_true",
                    help="스윕 뒤 배스텁 분석을 돌리지 않는다 (기본은 돌린다)")
    ap.add_argument("--blind", action="store_true", help="chip_pe.md 에 증분 대신 (봉인)")

    args = ap.parse_args()
    args.no_prep = args.mode == "sweep"             # 이하 본문은 이 값만 본다
    args.analyze = not args.no_analyze
    if args.mode == "newchip" and (args.chip or args.uid):
        ap.error("--mode newchip 은 UID 를 기계가 읽는다 — --chip/--uid 를 주지 않는다")
    if args.mode == "sweep" and not (args.chip or args.uid):
        ap.error("--mode sweep 은 어느 칩인지 알 길이 없다 — --chip 또는 --uid 가 필요하다")
    if args.chip:                                   # 라벨 → UID 역조회 (16hex 를 손으로 칠 일이 없다)
        args.uid = chip_registry.parse().get(args.chip)
        if not args.uid:
            ap.error(f"--chip {args.chip}: 등록부에 없거나 UID 가 비어 있다 "
                     f"(docs/chip_registry.md) — 신품이면 --mode newchip 이다")

    if args.base_sector != 0:
        ap.error("--base-sector: 수정안 #1 미승인 — 0 만 허용")
    if args.repeat < 1:
        ap.error("--repeat 는 1 이상")
    if not shutil.which("xsct"):
        raise Abort("xsct 가 PATH 에 없다 — Vitis 2025.2 settings64.sh 를 source 할 것")
    chip_registry.parse()                     # 등록부가 깨져 있으면 보드를 건드리기 전에 죽는다
    if args.reseat and args.repeat > 1:
        require_tty("--reseat 는 재장착 프롬프트가 필요")

    now = datetime.now(timezone.utc)
    batch_id = cap.utc_stamp(now)
    today = now.strftime("%Y-%m-%d")
    ses = Session(batch_id)
    ses.log(f"batch {batch_id}: mode={args.mode} chip={args.chip or '?'} "
            f"mhz={args.mhz} pl={args.pl} repeat={args.repeat} "
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
                verify_uid(ser, ses, uid, label, "세션1")       # 읽기만 한다 (P/E 불변)
                ses.rename(f"{label}_{uid}")
            else:
                try:
                    uid = run_prep(ser, ses)
                except Abort:
                    ses.rename("prepfail")
                    raise
                label = resolve_label(uid, ses, today)
                ses.rename(f"{label}_{uid}")
                chip_pe.append_pe(today, label, uid, PREP_SECTORS, "+1",
                                  f"flash_prep (batch {batch_id})", blind=args.blind)
                ses.log(f"chip_pe.md: {label} {PREP_SECTORS} {'(봉인)' if args.blind else '+1'}")

            g3_args = [PROGRAM_G3, args.mhz] + ([f"pl{args.pl}"] if args.pl else [])
            for k in range(1, args.repeat + 1):
                if k > 1 and args.reseat:
                    input(f"\n[{k}/{args.repeat}] {label} 을 빼고 다시 꽂은 뒤 엔터: ")
                    ses.log(f"[{k}/{args.repeat}] 재장착 확인")
                    verify_uid(ser, ses, uid, label, f"[{k}/{args.repeat}] 재장착 후")
                ser.reset_input_buffer()
                pre = run_xsct(g3_args, ses,
                               f"[{k}/{args.repeat}] 세션2 프로그래밍 (g3_chip_{args.mhz})", ser=ser)
                r = cap.capture_sweep(Drained(ser, pre), label, uid, reseat=int(args.reseat),
                                      repeat_idx=k, batch_id=batch_id, log=sys.stderr,
                                      expect_n=args.n_reads)
                ses.log(f"[{k}/{args.repeat}] {'VALID' if r.valid else 'INVALID'} "
                        f"{r.main_path.name} ({r.n_main} rows)")
                done += 1
                n = int(r.begin.get("n", 0))
                if n and n != args.n_reads:      # valid 판정보다 먼저 — 조기 중단이 여기로 온다
                    raise Abort(f"요청 N={args.n_reads} 인데 ELF 는 n={n} — 파일은 남겼다 "
                                f"(n_reads 열이 진실). N 은 빌드 시 고정이라 ELF 를 바꿔야 한다")
                if r.valid and args.analyze:
                    analyze(r.main_path, ses)
                if not r.valid:
                    invalid += 1
                    continue
    except KeyboardInterrupt:
        ses.log("Ctrl-C — 배치 중단")
    except Abort as e:
        ses.log(str(e))
        ses.log(f"{done}/{args.repeat} 완료 (invalid {invalid}) — 중단")
        raise
    except Exception as e:                 # 포트·xsct 타임아웃·파일 충돌 등 — 요약은 남기고 그대로 던진다
        ses.log(f"예외 {e!r}")
        ses.log(f"{done}/{args.repeat} 완료 (invalid {invalid}) — 중단")
        raise
    ses.log(f"{done}/{args.repeat} 완료 (invalid {invalid})")
    sys.exit(0 if done == args.repeat and invalid == 0 else 1)


if __name__ == "__main__":
    main()
