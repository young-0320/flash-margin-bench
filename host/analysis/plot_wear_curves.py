# plot_wear_curves.py — 수명 역산 교정 표 4장 → 칩별 소거 시간 곡선 그림 (2×2)
#
# 사용: uv run python host/analysis/plot_wear_curves.py [-o build/plots/wear_curves_2026-09.png]
#
# 입력: docs/results/data/wear_curves/wear_curves_<chip>_2026-09.csv (wear_curves.py 산출을 승격한 것)
# 그림: 윗줄 빠른 무리(chip01 · chip04) · 아랫줄 느린 무리(chip03 · chip07). 칸마다 섹터 0-6 의 1k 구간 소거 p50 선과
#       p10-p90 띠. y 는 네 칸 공유(ms) — 무리 사이 절대값 차이가 보이게. x 는 칩별(chip01 만 300k).
#       표에 없는 구간(chip07 53-60k · 77-80k)은 선을 끊는다

import argparse
import csv
import glob
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CURVES_GLOB = str(REPO / "docs" / "results" / "data" / "wear_curves" / "wear_curves_*_2026-09.csv")
LAYOUT = (("chip01", "chip04"), ("chip03", "chip07"))
GROUP = {"chip01": "fast", "chip04": "fast", "chip03": "slow", "chip07": "slow"}
BIN = 1000

# 플롯 팔레트 (dataviz 검증 통과 — 7색 categorical, 대비 WARN 은 범례로 보완)
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
SECTOR_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7"]


def load(pattern=CURVES_GLOB):
    """CSV 들 → {chip: {sector: [(bin_start, p10, p50, p90) ...]}} (ms, bin 순)."""
    out = {}
    for path in sorted(glob.glob(pattern)):
        rows = defaultdict(list)
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows[int(r["sector"])].append((int(r["bin_start"]), float(r["erase_us_p10"]) / 1e3,
                                               float(r["erase_us_p50"]) / 1e3, float(r["erase_us_p90"]) / 1e3))
                chip = r["chip"]
        out[chip] = {s: sorted(v) for s, v in rows.items()}
    return out


def with_gaps(points):
    """빠진 구간 자리에 NaN 을 끼워 선이 이어지지 않게 한다. x 는 구간 가운데(k 사이클)."""
    cols = ([], [], [], [])
    prev = None
    for b, *q in points:
        if prev is not None and b - prev > BIN:
            for c in cols:
                c.append(float("nan"))
        for c, v in zip(cols, ((b + BIN / 2) / 1e3, *q)):
            c.append(v)
        prev = b
    return cols


def plot(curves, out_png):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharey=True, dpi=150)
    fig.set_facecolor(SURFACE)
    for row, chips in enumerate(LAYOUT):
        for col, chip in enumerate(chips):
            ax = axes[row][col]
            ax.set_facecolor(SURFACE)
            ax.grid(True, color=GRID, lw=0.7)
            ax.set_axisbelow(True)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(BASELINE)
            for side in ("right", "top"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=INK2)
            for s, pts in sorted(curves[chip].items()):
                x, lo, mid, hi = with_gaps(pts)
                ax.fill_between(x, lo, hi, color=SECTOR_COLORS[s], alpha=0.12, lw=0)
                ax.plot(x, mid, color=SECTOR_COLORS[s], lw=1.4, label=f"sector {s}")
            ax.set_xlim(0, max(b for pts in curves[chip].values() for b, *_ in pts) / 1e3 + 1)
            ax.set_ylim(bottom=0)
            ax.set_title(f"{chip}  ({GROUP[chip]} group)", color=INK, fontsize=10, loc="left")
            if row == 1:
                ax.set_xlabel("cumulative P/E cycles (k)", color=INK2, fontsize=9)
            if col == 0:
                ax.set_ylabel("erase time (ms)", color=INK2, fontsize=9)
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=7, frameon=False, fontsize=8.5, labelcolor=INK2)
    fig.suptitle("Wear calibration curves — 1k-cycle bins, line = p50, band = p10–p90",
                 color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0.05, 1, 0.97))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    print(f"→ {out_png}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="수명 역산 교정 표 → 칩별 소거 시간 곡선 그림")
    ap.add_argument("-o", "--out", default=str(REPO / "build" / "plots" / "wear_curves_2026-09.png"))
    ap.add_argument("--curves", default=CURVES_GLOB, help="교정 표 glob")
    args = ap.parse_args(argv)
    plot(load(args.curves), args.out)


if __name__ == "__main__":
    main()
