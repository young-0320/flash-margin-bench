# plot_wear_curves.py — 수명 역산 교정 표 4장 → 칩별 소거 시간 곡선 그림 (2×2)
#
# 사용: uv run python host/analysis/plot_wear_curves.py [-o build/plots/wear_curves_2026-09.png]
#       uv run python host/analysis/plot_wear_curves.py --per-chip build/plots   # 교정 칩마다 한 장 wear_curves_<chip>_2026-09.png
#       uv run python host/analysis/plot_wear_curves.py --ratio [--mark 1.63 --mark-label '...'] -o <png>   # 칩별 배율 곡선 한 장
#
# 입력: docs/results/data/wear_curves/wear_curves_<chip>_2026-09.csv (wear_curves.py 산출을 승격한 것)
# 그림: 윗줄 빠른 무리(chip01 · chip04) · 아랫줄 느린 무리(chip03 · chip07). 칸마다 섹터 0-6 의 1k 구간 소거 p50 선과
#       p10-p90 띠. y 는 네 칸 공유(ms) — 무리 사이 절대값 차이가 보이게. x 는 칩별(chip01 만 300k).
#       표에 없는 구간(chip07 53-60k · 77-80k)은 선을 끊는다. 2×2 는 9월 4칩의 기록이고, 2026-10-02 부터는 같은 칸을
#       교정 칩마다 한 장씩(--per-chip) 낸다 — y 는 모든 장이 같다

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
LAYOUT = (("chip01", "chip04"), ("chip03", "chip07"))      # 기본 그림(2×2)은 9월 4칩 그대로. 그 뒤 칩은 --per-chip 에
GROUP = {"chip01": "fast", "chip04": "fast", "chip09": "fast", "chip03": "slow", "chip07": "slow"}
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


def panel(ax, chip, sectors):
    """한 칩의 칸 — 섹터 0-6 의 소거 p50 선과 p10-p90 띠. 2×2 와 칩별 그림이 같이 쓴다."""
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    for side in ("right", "top"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=INK2)
    for s, pts in sorted(sectors.items()):
        x, lo, mid, hi = with_gaps(pts)
        ax.fill_between(x, lo, hi, color=SECTOR_COLORS[s], alpha=0.12, lw=0)
        ax.plot(x, mid, color=SECTOR_COLORS[s], lw=1.4, label=f"sector {s}")
    ax.set_xlim(0, max(b for pts in sectors.values() for b, *_ in pts) / 1e3 + 1)
    ax.set_ylim(bottom=0)
    ax.set_title(f"{chip}  ({GROUP[chip]} group)", color=INK, fontsize=10, loc="left")


def plot(curves, out_png):
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharey=True, dpi=150)
    fig.set_facecolor(SURFACE)
    for row, chips in enumerate(LAYOUT):
        for col, chip in enumerate(chips):
            ax = axes[row][col]
            panel(ax, chip, curves[chip])
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


def plot_chips(curves, out_dir):
    """교정 칩마다 한 장 — 이름은 교정 표와 짝(`wear_curves_<chip>_2026-09.png`). y 는 모든 장이 같다(전 칩 p90 최대) —
    나란히 놓으면 2×2 처럼 무리 사이 절대값 차이가 보인다."""
    top = max(hi for sectors in curves.values() for pts in sectors.values() for *_, hi in pts) * 1.05
    for chip, sectors in sorted(curves.items()):
        fig, ax = plt.subplots(figsize=(8, 4.6), dpi=150)
        fig.set_facecolor(SURFACE)
        panel(ax, chip, sectors)
        ax.set_ylim(0, top)
        ax.set_xlabel("cumulative P/E cycles (k)", color=INK2, fontsize=9)
        ax.set_ylabel("erase time (ms)", color=INK2, fontsize=9)
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="lower center", ncol=7, frameon=False, fontsize=8.5, labelcolor=INK2)
        fig.suptitle("Wear calibration curve — 1k-cycle bins, line = p50, band = p10–p90",
                     color=INK, fontsize=11, x=0.01, ha="left")
        fig.tight_layout(rect=(0, 0.06, 1, 0.97))
        out = Path(out_dir) / f"wear_curves_{chip}_2026-09.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out, facecolor=SURFACE)
        plt.close(fig)
        print(f"→ {out}")


SURVEY_CSV = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"
RATIO_PANELS = (("빠른 무리 (신품 40ms 미만)", ("chip04", "chip01", "chip09")), ("느린 무리 (신품 40ms 이상)", ("chip03", "chip07")))
CHIP_COLORS = {"chip04": "#2a78d6", "chip01": "#eb6834", "chip09": "#1baf7a", "chip03": "#eda100", "chip07": "#e87ba4"}


def plot_ratio(curves, out_png, xmax=100, mark=None):
    """칩마다 섹터 0-6 p50 의 중앙값 ÷ 신품값(집계표) — 같은 무리 안 노화 속도 차이를 한 장에. 띠는 섹터 p50 의 최소-최대.
    mark=(배율, 라벨) 이면 빠른 무리 칸에 가로 점선 — 관측 하나가 칩마다 다른 사이클에 닿는 것을 보인다."""
    fresh = {}
    with open(SURVEY_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["erase_us_median"]:
                fresh[r["label"]] = float(r["erase_us_median"]) / 1e3
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), sharey=True, dpi=160)
    fig.set_facecolor(SURFACE)
    for ax, (title, chips) in zip(axes, RATIO_PANELS):
        ax.set_facecolor(SURFACE)
        ax.grid(True, color=GRID, lw=0.7)
        ax.set_axisbelow(True)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(BASELINE)
        for side in ("right", "top"):
            ax.spines[side].set_visible(False)
        ax.tick_params(colors=INK2, labelsize=8.5)
        ax.axhline(1.0, color=BASELINE, lw=1)
        for chip in chips:
            bins = sorted({b for pts in curves[chip].values() for b, *_ in pts if b <= xmax * 1000})
            by = {b: [] for b in bins}
            for pts in curves[chip].values():
                for b, _lo, mid, _hi in pts:
                    if b in by:
                        by[b].append(mid / fresh[chip])
            x = [(b + BIN / 2) / 1e3 for b in bins]
            med = [sorted(by[b])[len(by[b]) // 2] for b in bins]
            ax.fill_between(x, [min(by[b]) for b in bins], [max(by[b]) for b in bins], color=CHIP_COLORS[chip], alpha=0.12, lw=0)
            ax.plot(x, med, color=CHIP_COLORS[chip], lw=2, label=f"{chip} (신품 {fresh[chip]:.1f}ms)")
            ax.annotate(chip, (x[-1], med[-1]), xytext=(4, 0), textcoords="offset points", va="center", fontsize=8.5, color=INK2)
        if mark and "빠른" in title:
            ax.axhline(mark[0], color=MUTED, lw=1.2, ls=(0, (4, 3)))
            ax.annotate(mark[1], (xmax * 0.42, mark[0]), xytext=(0, -12), textcoords="offset points", fontsize=8.5, color=INK2)
        ax.set_xlim(0, xmax + 9)
        ax.set_title(title, color=INK, fontsize=10.5, loc="left")
        ax.set_xlabel("누적 P/E 사이클 (천 회)", color=INK2, fontsize=9)
        ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2, loc="upper left")
    axes[0].set_ylabel("소거 시간 ÷ 신품값 (섹터 0-6 중앙값)", color=INK2, fontsize=9)
    axes[0].set_ylim(bottom=0.9)
    fig.suptitle("같은 무리 안에서도 늙는 속도가 다르다 — 1천 사이클 구간, 선은 섹터 중앙값, 띠는 섹터 최소-최대",
                 color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    print(f"→ {out_png}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="수명 역산 교정 표 → 칩별 소거 시간 곡선 그림")
    ap.add_argument("-o", "--out", default=str(REPO / "build" / "plots" / "wear_curves_2026-09.png"))
    ap.add_argument("--curves", default=CURVES_GLOB, help="교정 표 glob")
    ap.add_argument("--per-chip", metavar="DIR", help="교정 칩마다 한 장씩 DIR 에 (wear_curves_<chip>_2026-09.png)")
    ap.add_argument("--ratio", action="store_true", help="칩별 신품 대비 배율 곡선 한 장 (무리별 두 칸, x 는 100k 까지)")
    ap.add_argument("--mark", type=float, help="--ratio 의 빠른 무리 칸에 가로 점선 (배율)")
    ap.add_argument("--mark-label", default="", help="그 점선의 글씨")
    args = ap.parse_args(argv)
    if args.per_chip:
        plot_chips(load(args.curves), args.per_chip)
    elif args.ratio:
        plot_ratio(load(args.curves), args.out, mark=(args.mark, args.mark_label) if args.mark else None)
    else:
        plot(load(args.curves), args.out)


if __name__ == "__main__":
    main()
