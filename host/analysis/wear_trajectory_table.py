# wear_trajectory_table.py — 칩별 0 → 100k 소거 · 프로그램 시간 추이 표 (무리별)
#
# 사용: uv run python host/analysis/wear_trajectory_table.py erase   > docs/results/data/wear_curves/wear_erase_trajectory_2026-10.md
#       uv run python host/analysis/wear_trajectory_table.py program > docs/results/data/wear_curves/wear_program_trajectory_2026-10.md
#
# 입력: docs/results/data/wear_curves/wear_curves_chip*_20*.csv (교정 · _nocal · _ali · _64C/_65C 전부) · 신품값은 newchip_survey_2026-09.csv.
# 값 = 섹터 0-6 의 1k 구간 p50 의 중앙값(ms). 괄호 = 소거는 신품(newchip prep 소거 중앙값) 대비, 프로그램은 첫 1k 구간 대비 배율.
# 무리는 신품 소거 40ms 경계(S-5). 표에 없는 점(—)은 그 칩의 곡선에 그 구간이 없는 것.

import csv
import glob
import os
import statistics as st
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CURVES = REPO / "docs" / "results" / "data" / "wear_curves"
SURVEY = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"
POINTS = (1, 3, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100)
SPLIT_MS = 40.0
TAGS = {"nocal": "교정 밖", "ali": "알리 · 교정 밖", "64C": "65°C · 교정 밖", "65C": "65°C · 교정 밖"}


def load():
    fresh = {r["label"]: int(r["erase_us_median"]) / 1000 for r in csv.DictReader(open(SURVEY, encoding="utf-8")) if r["erase_us_median"]}
    out = []
    for f in sorted(glob.glob(str(CURVES / "wear_curves_chip*_20*.csv"))):
        parts = os.path.basename(f)[:-4].split("_")
        chip, tag = parts[2], (parts[3] if len(parts) == 5 else "")
        by = {}
        for r in csv.DictReader(open(f, encoding="utf-8")):
            by.setdefault(int(r["bin_start"]), []).append((int(r["erase_us_p50"]), int(r["program_us_p50"])))
        top = max(by) + 999
        out.append({"chip": chip, "tag": tag, "fresh": fresh.get(chip), "top": top,
                    "erase": {k: st.median(e for e, _ in by[(k - 1) * 1000 + 1]) / 1000 for k in POINTS if (k - 1) * 1000 + 1 in by},
                    "program": {k: st.median(p for _, p in by[(k - 1) * 1000 + 1]) / 1000 for k in POINTS if (k - 1) * 1000 + 1 in by}})
    return out


def table(rows, kind):
    head = "| 칩 | 신품 소거 (ms) | " + ("" if kind == "erase" else "첫 1k 프로그램 (ms) | ") + " | ".join(f"{k}k" for k in POINTS) + " |"
    lines = [head, "|" + "---|" * (len(POINTS) + (2 if kind == "erase" else 3))]
    for r in sorted(rows, key=lambda r: r["fresh"]):
        name = r["chip"] + (f" ({TAGS.get(r['tag'], r['tag'])})" if r["tag"] else "")
        base = r["fresh"] if kind == "erase" else r["program"].get(1)
        cells = [f"{r[kind][k]:.{1 if kind == 'erase' else 2}f} ({r[kind][k] / base:.2f})" if k in r[kind] else "—" for k in POINTS]
        lines.append(f"| {name} | {r['fresh']:.1f} | " + ("" if kind == "erase" else f"{base:.2f} | ") + " | ".join(cells) + " |")
    return "\n".join(lines)


def main():
    kind = sys.argv[1] if len(sys.argv) > 1 else "erase"
    rows = [r for r in load() if r["fresh"]]
    fast = [r for r in rows if r["fresh"] < SPLIT_MS]
    slow = [r for r in rows if r["fresh"] >= SPLIT_MS]
    what = "소거" if kind == "erase" else "프로그램"
    base = "신품 소거(newchip prep, 섹터 0-127 중앙값)" if kind == "erase" else "그 칩의 첫 1k 구간(1-1,000) 프로그램"
    twin = "wear_program_trajectory_2026-10.md" if kind == "erase" else "wear_erase_trajectory_2026-10.md"
    print(f"""# wear_{kind}_trajectory_2026-10 — 칩별 {what} 시간 추이 · 0 → 100k (빠른 · 느린 무리)

> 수치와 표만 둔다. 쌍둥이 문서 [`{twin}`]({twin}). 해석은 칩별 `../../wear/wear_endurance_*.md` · `wear_endurance_200k.md`.

- **무엇**: 마모 루프 A 행의 {what} 시간 — 섹터 0-6 의 1k 구간 p50 을 섹터 7개에서 다시 중앙값 낸 값(ms). 괄호는 {base} 대비 배율. 구간 이름 「Nk」 는
  (N−1)k+1 - Nk 구간(예: 100k = 99,001-100,000). 0x00 마모 루프 값이라 신품 prep(PRBS)의 프로그램과 눈금이 다르다
- **칩**: 곡선 CSV 가 있는 전부 — 교정 9칩(접미사 없음) · 교정 밖(`_nocal` JV chip10 · 14 와 chip21 · `_ali` chip12 · `_64C`/`_65C` 온도 chip16 · 17). 무리는 신품 소거 {SPLIT_MS:g}ms 경계.
  chip22(65°C)는 승격 전이라 없다. 200k 까지 간 칩의 100k 너머는 칩별 수치 md
- **원본**: `docs/results/data/wear_curves/wear_curves_chip*_20*.csv` · 신품값 `../newchip_survey_2026-09.csv`

## 1. 빠른 무리 (신품 소거 {SPLIT_MS:g}ms 미만)

{table(fast, kind)}

## 2. 느린 무리 (신품 소거 {SPLIT_MS:g}ms 이상)

{table(slow, kind)}

## 재현

```bash
uv run python host/analysis/wear_trajectory_table.py {kind} > docs/results/data/wear_curves/wear_{kind}_trajectory_2026-10.md
```
""")


if __name__ == "__main__":
    main()
