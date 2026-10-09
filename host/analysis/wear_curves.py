# wear_curves.py — 마모 루프 A 행 → 섹터별 1k 구간 분위수 표 (수명 역산 교정 곡선의 입력)
#
# 사용: uv run python host/analysis/wear_curves.py --chip chip04 \
#          data/wear/1790423530 data/wear/1790482991 data/wear/1790491294 \
#          --drop-cycles 66654-66671 -o build/data/wear_curves_chip04.csv
#
# 입력: 세션 폴더(들)의 A.txt — `#WEAR A cycle= sector= t_erase_us= t_program_us= ts= sum=` 행.
#       파서는 host_side.parse_row (호스트 쪽 문자열의 정본). 체크섬이 깨진 행은 버리고 개수만 센다.
# 규칙:
#   · 구간은 (cycle-1)//1000 — 1~1000 이 구간 0. 결과 문서(wear_endurance_*.md §3-§5)와 같은 묶음
#   · 같은 (cycle, sector) 가 여러 세션에 있으면 **뒤에 적은 세션**이 이긴다 — x 축은 tally 를 따르므로
#     되돌려 재개한 세션의 값이 정본이다 (chip04 66,601-66,653). 세션은 시간 순으로 적는다
#   · --drop-cycles a-b 로 명시한 사이클은 뺀다 (chip04 66,654-66,671 SPI 접촉 불량). 값으로 거르지
#     않는다 — 어떤 행을 왜 뺐는지는 짝 md 에 사람이 적는다
# 출력 CSV 한 행 = (구간, 섹터). n 은 그 칸의 A 행 수 — 1,000 미만이면 공백·결측이 있는 구간이다.
#   chip,bin_start,bin_end,sector,n,erase_us_p10,erase_us_p50,erase_us_p90,program_us_p10,program_us_p50,program_us_p90,
#   erase_us_q00,erase_us_q05,…,erase_us_q100   (v4 — 소거 시간 5% 간격 분위수 21개. 역산 모델이 셀의 분포 모양을 그대로 쓴다)

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "tests"))
import host_side as hs                                      # noqa: E402

BIN = 1000
Q_LEVELS = tuple(range(0, 101, 5))                          # 0, 5, …, 100 — 5% 간격 분위수 21개 (v4 셀 분포)
Q_FIELDS = tuple(f"erase_us_q{q:02d}" for q in Q_LEVELS)    # erase_us_q00 … erase_us_q100
FIELDS = ("chip", "bin_start", "bin_end", "sector", "n",
          "erase_us_p10", "erase_us_p50", "erase_us_p90",
          "program_us_p10", "program_us_p50", "program_us_p90", *Q_FIELDS)


def load_sessions(session_dirs, drop=()):
    """세션 폴더들의 A.txt → {(cycle, sector): (t_erase_us, t_program_us)}, 깨진 행 수.

    뒤 세션이 앞 세션을 덮어쓴다. drop 은 (a, b) 닫힌 구간 목록."""
    rows, rejected = {}, 0
    for d in session_dirs:
        p = Path(d) / "A.txt"
        if not p.exists():
            raise SystemExit(f"{p} 가 없다")
        with p.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                i = line.find(hs.PREFIX)
                r = hs.parse_row(line[i + len(hs.PREFIX):]) if i >= 0 else None
                if r is None or r["type"] != "A":
                    rejected += 1
                    continue
                c = r["cycle"]
                if any(a <= c <= b for a, b in drop):
                    continue
                rows[(c, r["sector"])] = (r["t_erase_us"], r["t_program_us"])
    return rows, rejected


def pct(values, q):
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def bin_table(chip, rows):
    """(cycle, sector) 행 → 구간·섹터별 분위수 행 목록 (구간·섹터 오름차순)."""
    cells = defaultdict(list)
    for (c, s), (te, tp) in rows.items():
        cells[((c - 1) // BIN, s)].append((te, tp))
    out = []
    for (k, s) in sorted(cells):
        te = [x[0] for x in cells[(k, s)]]
        tp = [x[1] for x in cells[(k, s)]]
        out.append({"chip": chip, "bin_start": k * BIN + 1, "bin_end": (k + 1) * BIN, "sector": s, "n": len(te),
                    "erase_us_p10": pct(te, 0.1), "erase_us_p50": pct(te, 0.5), "erase_us_p90": pct(te, 0.9),
                    "program_us_p10": pct(tp, 0.1), "program_us_p50": pct(tp, 0.5), "program_us_p90": pct(tp, 0.9),
                    **{f: pct(te, q / 100) for f, q in zip(Q_FIELDS, Q_LEVELS)}})
    return out


def parse_range(text):
    a, _, b = text.partition("-")
    return int(a), int(b or a)


def main(argv=None):
    ap = argparse.ArgumentParser(description="마모 루프 A 행 → 섹터별 1k 구간 분위수 표")
    ap.add_argument("sessions", nargs="+", help="run_wear 세션 폴더 (A.txt 가 있는 곳), 시간 순")
    ap.add_argument("--chip", required=True, help="칩 라벨 — CSV 의 chip 열")
    ap.add_argument("--drop-cycles", action="append", default=[], metavar="A-B",
                    help="집계에서 뺄 사이클 (닫힌 구간). 여러 번 줄 수 있다")
    ap.add_argument("-o", "--out", help="출력 CSV. 기본 build/data/wear_curves_<chip>.csv")
    args = ap.parse_args(argv)

    drop = [parse_range(t) for t in args.drop_cycles]
    rows, rejected = load_sessions(args.sessions, drop)
    table = bin_table(args.chip, rows)

    out = Path(args.out) if args.out else REPO / "build" / "data" / f"wear_curves_{args.chip}.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(table)

    cycles = sorted({c for c, _ in rows})
    short = sorted({(r["bin_start"], r["bin_end"]) for r in table if r["n"] < BIN})
    print(f"{args.chip}: A 행 {len(rows):,} (cycle {cycles[0]:,}-{cycles[-1]:,}) · 깨진/무시 행 {rejected:,} · "
          f"뺀 구간 {drop or '없음'} → {out} ({len(table)} 행)")
    if short:
        print(f"  n<{BIN} 인 구간 {len(short)}개 (공백·결측·구간 끝): " +
              ", ".join(f"{a:,}-{b:,}" for a, b in short[:12]) + (" …" if len(short) > 12 else ""))


if __name__ == "__main__":
    main()
