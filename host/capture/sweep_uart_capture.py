#!/usr/bin/env python3
"""UART 스윕 스트림 수신 → 계약 §6 CSV 파일화 (PS bare-metal의 PC측 반쪽).

ps/src/g0_sweep.c가 UART로 뿜는 행 프로토콜을 받아 파일 두 개로 나눈다:
  M,<row>  → build/data/sweep_<label>[_<uid16>]_<stamp>.csv        (메인, §6 열 순서)
  R,<row>  → build/data/sweep_<label>[_<uid16>]_<stamp>_reads.csv  (읽기별 e_i 원본, 필수)
PS는 시계·git이 없으므로 메타데이터 열과 파일명 스탬프는 여기서 붙인다.
generated_at = 수신 시작 시각(UTC), git_rev = 이 리포 HEAD.

메타 열 (수정안 #3, 상정 중): target, generated_at, git_rev, uid, reseat, repeat_idx, batch_id.
  - target 은 라벨(chip01 / loopback). 사람이 입력하지 않는다 — UID 로 등록부
    (docs/chip_registry.md) 를 역조회한 값이다
  - 파일명: chip* 는 sweep_<label>_<uid16>_<stamp>, loopback 은 종전대로 sweep_loopback_<stamp>

불변식 — 이 파일이 집행한다 (래퍼가 아니라. 모든 경로가 여기를 지난다):
  - chip 대상은 UID 없이 CSV 를 만들지 않는다. loopback 은 UID 없이 허용
  - --raw 는 진단용 원문 덤프. CSV 를 만들지 않는다

무효 런(§6): "#G0 SWEEP END valid=0"(①②③④⑥은 PS가 판정) 또는 END 미수신·행
결측(⑤ — Ctrl-C, 보드 리셋, 케이블 뽑힘 포함)이면 두 파일 모두 _invalid 접미.

라이브러리: capture_sweep(ser, label, uid, ...) 에 이미 열린 pyserial 핸들을 넘긴다 —
래퍼(host/run/)가 세션 1(flash_prep)에서 받은 UID 를 들고 같은 포트로 세션 2 를 잇는다.

사용: sweep_uart_capture.py (--uid <16hex> | --loopback | --raw) [--port] [--baud] ...
의존: pyserial
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

import serial

sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_registry  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUTDIR = REPO / "build" / "data"

MAIN_COLS = ("phase_step,phase_ps,n_reads,b_bits,bit_errors,reads_with_error,"
             "bit_err_sq_sum,f_sclk_hz,dphi_ps")
READS_COLS = "phase_step,read_idx,err_count"
META_COLS = "target,generated_at,git_rev,uid,reseat,repeat_idx,batch_id"


class Result(NamedTuple):
    valid: bool
    n_main: int
    n_reads: int
    main_path: Path
    reads_path: Path
    begin: dict        # "#G0 SWEEP BEGIN" 의 key=value (steps, n, b, f_sclk_hz, dphi_ps)


def utc_stamp(t=None):
    return (t or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def git_rev():
    return subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True).stdout.strip() or "unknown"


def check_target(label, uid):
    """불변식. 통과하면 정규화된 uid(loopback 은 '') 를 돌려준다."""
    if label == "loopback":
        if uid:
            raise SystemExit("loopback 은 UID 를 갖지 않는다")
        return ""
    if label not in chip_registry.LABELS:
        raise SystemExit(f"target {label!r}: loopback | chip01..chip10 만 허용 (§6)")
    if not uid:
        raise SystemExit(f"{label}: UID 없이 chip CSV 를 만들 수 없다 (수정안 #3 R13)")
    return chip_registry.normalize_uid(uid)


def sweep_base(outdir, label, uid, stamp):
    return Path(outdir) / (f"sweep_{label}_{stamp}" if label == "loopback"
                           else f"sweep_{label}_{uid}_{stamp}")


def capture_sweep(ser, label, uid, outdir=DEFAULT_OUTDIR, *,
                  reseat=0, repeat_idx=1, batch_id=None, log=sys.stderr):
    """열린 시리얼 핸들에서 스윕 1회를 받아 CSV 2개로 쓴다. 파일은 불변식 통과 후에만 생긴다.
    Ctrl-C 는 파일을 _invalid 로 정리한 뒤 다시 던진다 (호출자가 배치 중단을 결정)."""
    uid = check_target(label, uid)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    stamp = utc_stamp(now)
    meta = (f"{label},{now.isoformat(timespec='seconds')},{git_rev()},"
            f"{uid},{int(reseat)},{int(repeat_idx)},{batch_id or stamp}")

    base = sweep_base(outdir, label, uid, stamp)
    main_path, reads_path = Path(f"{base}.csv"), Path(f"{base}_reads.csv")

    valid = False          # END valid=1 + 행수 완전 일치여야만 True — 그 외 전부 무효 ⑤
    began = False
    begin = {}
    steps = n_cfg = 0      # BEGIN 라인에서 파싱 — 행수 검증(⑤: 결측·유실) 기준
    n_main = n_reads = 0
    interrupted = None
    try:
        with open(main_path, "x") as fm, open(reads_path, "x") as fr:   # 덮어쓰기 금지
            fm.write(f"{MAIN_COLS},{META_COLS}\n")
            fr.write(f"{READS_COLS}\n")
            print(f"listening on {ser.port} @{ser.baudrate} → {main_path}", file=log)
            while True:
                line = ser.readline().decode(errors="replace").strip()
                if not line:
                    continue
                i = line.find("#G0")            # rst 쓰레기가 줄바꿈 없이 첫 줄에 붙어도 잡는다 (run_prep 과 동일)
                if i >= 0:
                    line = line[i:]
                    print(line, file=log)
                    if "SWEEP BEGIN" in line:
                        began = True
                        begin = dict(t.split("=", 1) for t in line.split() if "=" in t)
                        steps, n_cfg = int(begin.get("steps", 0)), int(begin.get("n", 0))
                    elif "ERROR" in line:
                        break
                    elif "SWEEP END" in line:
                        # PS가 valid=1이어도 PC까지 전 행이 도착했어야 유효 —
                        # BEGIN을 놓쳤거나(늦은 접속) UART 행 유실이면 무효 ⑤
                        complete = (began and steps > 0
                                    and n_main == steps and n_reads == steps * n_cfg)
                        if "valid=1" in line and not complete:
                            print(f"행 결측 — 무효 ⑤: main {n_main}/{steps}, "
                                  f"reads {n_reads}/{steps * n_cfg}", file=log)
                        valid = ("valid=1" in line) and complete
                        break
                elif began and line.startswith("M,"):
                    fm.write(f"{line[2:]},{meta}\n")
                    n_main += 1
                elif began and line.startswith("R,"):
                    fr.write(f"{line[2:]}\n")
                    n_reads += 1
    except KeyboardInterrupt as e:
        print("interrupted — 무효 ⑤(미완주)", file=log)
        interrupted = e

    if not valid:
        # 짝 규칙(<stem>.csv ↔ <stem>_reads.csv) 유지: 접미는 공통 stem에 붙인다
        main_path = main_path.rename(Path(f"{base}_invalid.csv"))
        reads_path = reads_path.rename(Path(f"{base}_invalid_reads.csv"))
    print(f"{'VALID' if valid else 'INVALID'}: {n_main} rows, {n_reads} read rows\n"
          f"  {main_path}\n  {reads_path}", file=log)
    if interrupted:
        raise interrupted
    return Result(valid, n_main, n_reads, main_path, reads_path, begin)


def dump_raw(ser, out=sys.stdout):
    """진단용: 수신 원문을 그대로 흘린다. CSV 를 만들지 않는다. Ctrl-C 로 종료."""
    print(f"raw dump on {ser.port} @{ser.baudrate} — CSV 미생성", file=sys.stderr)
    try:
        while True:
            line = ser.readline().decode(errors="replace").rstrip("\r\n")
            if line:
                print(line, file=out)
    except KeyboardInterrupt:
        pass


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR, type=Path)
    who = ap.add_mutually_exclusive_group(required=True)
    who.add_argument("--uid", help="flash_prep 의 #PREP UID <16hex>. 라벨은 등록부 역조회")
    who.add_argument("--loopback", action="store_true", help="G0 루프백 (UID 없음)")
    who.add_argument("--raw", action="store_true", help="진단용 원문 덤프 — CSV 미생성")
    ap.add_argument("--reseat", type=int, choices=(0, 1), default=0)
    ap.add_argument("--repeat-idx", type=int, default=1)
    ap.add_argument("--batch-id", help="배치 시작 stamp. 생략 시 이 스윕의 stamp")
    args = ap.parse_args()

    if args.raw:
        with serial.Serial(args.port, args.baud, timeout=None) as ser:
            dump_raw(ser)
        return

    if args.loopback:
        label, uid = "loopback", None
    else:
        label = chip_registry.label_for(args.uid)
        if label is None:
            raise SystemExit(f"UID {args.uid.upper()} 는 등록부에 없다 — "
                             "host/run/run_sweep_chip.py 로 등록하거나 docs/chip_registry.md 기입")
        uid = args.uid
    check_target(label, uid)               # 포트를 열기 전에 거부

    try:
        with serial.Serial(args.port, args.baud, timeout=None) as ser:
            r = capture_sweep(ser, label, uid, args.outdir, reseat=args.reseat,
                              repeat_idx=args.repeat_idx, batch_id=args.batch_id)
    except KeyboardInterrupt:
        sys.exit(1)
    sys.exit(0 if r.valid else 1)


if __name__ == "__main__":
    main()
