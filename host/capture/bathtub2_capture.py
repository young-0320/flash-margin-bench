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
import sys
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
        reason = "interrupted" if interrupted else "no_end"
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
        with v1.serial.Serial(args.port, args.baud, timeout=None) as ser:
            r = capture_bathtub2(ser, label, uid, args.outdir, reseat=args.reseat,
                                 repeat_idx=args.repeat_idx, batch_id=args.batch_id)
    except KeyboardInterrupt:
        sys.exit(1)
    sys.exit(0 if r.valid else 1)


if __name__ == "__main__":
    main()
