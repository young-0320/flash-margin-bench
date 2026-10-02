#!/usr/bin/env python3
"""prep_survey_parse.py — flash_prep 세션 로그에서 신품 조사 수치를 뽑는다 (W10-P).

실행:  uv run python host/analysis/prep_survey_parse.py data/session_chip04_*.log
       uv run python host/analysis/prep_survey_parse.py --csv build/data/session_*.log

뽑는 것: 라벨·UID·일자 + 소거 median/min/max(µs) + blank_pre/post(bits).
`docs/results/data/newchip_survey_2026-09.md` 의 표와 짝 CSV 에 그대로 옮겨 붙이는 용도다.
폭(width)은 여기서 안 나온다 — 그건 스윕 CSV 에서 bathtub_analysis.py 가 낸다.

한 세션에 prep 이 없으면(--no-prep 런) 조용히 건너뛴다 — 그런 로그도 같은 디렉터리에 섞인다.
"""

import argparse
import re
import statistics
import sys
from pathlib import Path

UID = re.compile(r"#PREP UID ([0-9A-F]{16})")
ERASE = re.compile(r"#PREP ERASE (\d+) (\d+)\s*$", re.M)
BLANK = re.compile(r"#PREP BLANK (pre|post)\s+range=(\d+)-(\d+) bits=(\d+)")
NAME = re.compile(r"session_(chip\d+|prepfail)_([0-9A-F]{16})_(\d{8})T")


def parse(path):
    txt = path.read_text(encoding="utf-8", errors="replace")
    us = [int(m.group(2)) for m in ERASE.finditer(txt)]
    if not us:
        return None                       # prep 없는 세션 (--no-prep) — 조용히 건너뛴다
    blanks = {m.group(1): int(m.group(4)) for m in BLANK.finditer(txt)}
    m = NAME.search(path.name)
    uid_m = UID.search(txt)
    d = m.group(3) if m else "?"
    return dict(label=m.group(1) if m else "?",
                uid=uid_m.group(1) if uid_m else (m.group(2) if m else "?"),
                date=f"{d[:4]}-{d[4:6]}-{d[6:]}" if d != "?" else "?",
                n=len(us), median=round(statistics.median(us)), lo=min(us), hi=max(us),
                pre=blanks.get("pre"), post=blanks.get("post"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("logs", nargs="+", type=Path)
    ap.add_argument("--csv", action="store_true", help="집계 CSV 에 붙일 열만 출력")
    args = ap.parse_args()

    rows = [r for r in (parse(p) for p in sorted(args.logs)) if r]
    if not rows:
        sys.exit("prep 이 있는 세션 로그가 없다")
    for r in rows:
        b = lambda v: "미관측" if v is None else v          # noqa: E731
        if args.csv:
            print(f"{r['label']},{r['uid']},{r['date']},,,,{r['median']},{r['lo']},{r['hi']},,{b(r['pre'])},{b(r['post'])},,")
        else:
            print(f"| {r['label']} | {r['uid']} | {r['date']} | | | **{r['median']:,}** | "
                  f"{r['lo']:,} ~ {r['hi']:,} | {b(r['pre'])} | {b(r['post'])} |   "
                  f"(섹터 {r['n']}개, 산포 {r['hi'] / r['lo']:.2f}배)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
