#!/usr/bin/env python3
"""UART 스윕 스트림 수신 → 계약 §6 CSV 파일화 (G0, PS bare-metal의 PC측 반쪽).

ps/src/g0_sweep.c가 UART로 뿜는 행 프로토콜을 받아 파일 두 개로 나눈다:
  M,<row>  → build/data/sweep_<target>_<stamp>.csv        (메인, §6 열 순서)
  R,<row>  → build/data/sweep_<target>_<stamp>_reads.csv  (읽기별 e_i 원본, 필수)
PS는 시계·git이 없으므로 메타데이터 3열(target, generated_at, git_rev)과 파일명
스탬프는 여기서 붙인다. generated_at = 수신 시작 시각(UTC), git_rev = 이 리포 HEAD.

무효 런(§6): "#G0 SWEEP END valid=0"(①②③④⑥은 PS가 판정) 또는 END 미수신·행
결측(⑤ — Ctrl-C, 보드 리셋, 케이블 뽑힘 포함)이면 두 파일 모두 _invalid 접미.

사용: python3 uart_capture.py [--port /dev/ttyUSB1] [--baud 115200] [--target loopback]
의존: pyserial
"""

import argparse
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import serial

REPO = Path(__file__).resolve().parents[2]

MAIN_COLS = ("phase_step,phase_ps,n_reads,b_bits,bit_errors,reads_with_error,"
             "bit_err_sq_sum,f_sclk_hz,dphi_ps")
READS_COLS = "phase_step,read_idx,err_count"
META_COLS = "target,generated_at,git_rev"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", default="/dev/ttyUSB1")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--target", default="loopback",
                    help="loopback | chip01..chip10 (§6 파일명·target 열)")
    ap.add_argument("--outdir", default=REPO / "build" / "data", type=Path)
    args = ap.parse_args()

    args.outdir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    git_rev = subprocess.run(["git", "-C", REPO, "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True).stdout.strip() or "unknown"
    meta = f"{args.target},{generated_at},{git_rev}"

    base = args.outdir / f"sweep_{args.target}_{stamp}"
    main_path, reads_path = Path(f"{base}.csv"), Path(f"{base}_reads.csv")

    valid = False          # END valid=1 + 행수 완전 일치여야만 True — 그 외 전부 무효 ⑤
    began = False
    steps = n_cfg = 0      # BEGIN 라인에서 파싱 — 행수 검증(⑤: 결측·유실) 기준
    n_main = n_reads = 0
    try:
        with serial.Serial(args.port, args.baud, timeout=None) as ser, \
             open(main_path, "w") as fm, open(reads_path, "w") as fr:
            fm.write(f"{MAIN_COLS},{META_COLS}\n")
            fr.write(f"{READS_COLS}\n")
            print(f"listening on {args.port} @{args.baud} → {main_path}", file=sys.stderr)
            while True:
                line = ser.readline().decode(errors="replace").strip()
                if not line:
                    continue
                if line.startswith("#G0"):
                    print(line, file=sys.stderr)
                    if "SWEEP BEGIN" in line:
                        began = True
                        kv = dict(t.split("=", 1) for t in line.split() if "=" in t)
                        steps, n_cfg = int(kv.get("steps", 0)), int(kv.get("n", 0))
                    elif "ERROR" in line:
                        break
                    elif "SWEEP END" in line:
                        # PS가 valid=1이어도 PC까지 전 행이 도착했어야 유효 —
                        # BEGIN을 놓쳤거나(늦은 접속) UART 행 유실이면 무효 ⑤
                        complete = (began and steps > 0
                                    and n_main == steps and n_reads == steps * n_cfg)
                        if "valid=1" in line and not complete:
                            print(f"행 결측 — 무효 ⑤: main {n_main}/{steps}, "
                                  f"reads {n_reads}/{steps * n_cfg}", file=sys.stderr)
                        valid = ("valid=1" in line) and complete
                        break
                elif began and line.startswith("M,"):
                    fm.write(f"{line[2:]},{meta}\n")
                    n_main += 1
                elif began and line.startswith("R,"):
                    fr.write(f"{line[2:]}\n")
                    n_reads += 1
    except KeyboardInterrupt:
        print("interrupted — 무효 ⑤(미완주)", file=sys.stderr)

    if not valid:
        # 짝 규칙(<stem>.csv ↔ <stem>_reads.csv) 유지: 접미는 공통 stem에 붙인다
        main_path = main_path.rename(Path(f"{base}_invalid.csv"))
        reads_path = reads_path.rename(Path(f"{base}_invalid_reads.csv"))
    print(f"{'VALID' if valid else 'INVALID'}: {n_main} rows, {n_reads} read rows\n"
          f"  {main_path}\n  {reads_path}", file=sys.stderr)
    sys.exit(0 if valid else 1)


if __name__ == "__main__":
    main()
