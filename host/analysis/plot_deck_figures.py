# plot_deck_figures.py — 최종 발표 슬라이드 그림 둘 (승격 그림에 없는 것만)
#
# 사용: uv run python host/analysis/plot_deck_figures.py [-o build/deck]
#
# 입력: docs/results/data/wear_curves/wear_curves_chip*_20*.csv · docs/results/data/newchip_survey_2026-09.csv
# 그림: deck_erase_200k.png — chip06(빠른) · chip03(느린) 섹터 0-6 소거 p50, 0 → 200k (계단 현상 대 완만한 증가)
#       deck_temp_100k.png — 100k 소거 배율 · 프로그램 배율을 무리 × 온도로 (100k 를 다 간 칩만)
#       deck_ratio_100k.png — 교정 9칩 소거 배율 곡선 (plot_wear_curves.py --ratio 와 같은 값, 슬라이드 크기에 맞춰 글자를 키움)
# 배율 정의는 wear_temperature_85C.md 표와 같다: 소거 = 섹터 0-6 p50 중앙값 ÷ 신품값, 프로그램 = 같은 값 100k 구간 ÷ 첫 1k 구간

import argparse
import csv
import glob
from collections import defaultdict
from pathlib import Path
from statistics import median

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

REPO = Path(__file__).resolve().parents[2]
CURVES = REPO / "docs" / "results" / "data" / "wear_curves"
SURVEY_CSV = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"

SURFACE = "#f6f6f3"                                          # 슬라이드 배경
INK, INK2, MUTED = "#1a1a1a", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
FAST, SLOW = "#008300", "#4a3aa7"
T65, T85 = "#2a78d6", "#eb6834"

GROUPS = {"빠른": {"상온": ["chip01", "chip02", "chip04", "chip06", "chip09", "chip18"], "65°C": ["chip16", "chip17"], "85°C": ["chip24"]},
          "느린": {"상온": ["chip03", "chip07", "chip15"], "빠른 노화 형": ["chip12", "chip21"], "85°C": ["chip22"]}}


def load(chip):
    """칩 하나 → {bin_start: {sector: (erase_ms, program_ms)}} — 곡선 CSV 는 칩마다 하나(접미사 무관)."""
    path, = glob.glob(str(CURVES / f"wear_curves_{chip}_*.csv"))
    out = defaultdict(dict)
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            if int(r["sector"]) <= 6:
                out[int(r["bin_start"])][int(r["sector"])] = (float(r["erase_us_p50"]) / 1e3, float(r["program_us_p50"]) / 1e3)
    return out


def fresh_ms():
    with open(SURVEY_CSV, newline="", encoding="utf-8") as f:
        return {r["label"]: float(r["erase_us_median"]) / 1e3 for r in csv.DictReader(f) if r["erase_us_median"]}


def style(ax):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    for side in ("right", "top"):
        ax.spines[side].set_visible(False)
    ax.tick_params(colors=INK2, labelsize=10, length=0)


def plot_erase(out_png):
    fig, axes = plt.subplots(1, 2, figsize=(6.9, 4.2), sharey=True, dpi=220)
    fig.set_facecolor(SURFACE)
    for ax, chip, color, title in ((axes[0], "chip06", FAST, "빠른 무리 chip06 — 계단 현상"), (axes[1], "chip03", SLOW, "느린 무리 chip03 — 완만한 증가")):
        style(ax)
        bins = load(chip)
        for s in range(7):
            x, y, prev = [], [], None
            for b in sorted(b for b in bins if s in bins[b] and b <= 200_000):
                if prev is not None and b - prev > 1000:           # 빠진 구간은 잇지 않는다
                    x.append(float("nan"))
                    y.append(float("nan"))
                x.append((b + 500) / 1e3)
                y.append(bins[b][s][0])
                prev = b
            ax.plot(x, y, color=color, lw=1.1, alpha=0.75)
        ax.set_title(title, color=INK, fontsize=12, loc="left", fontweight="bold")
        ax.set_xlim(0, 205)
        ax.set_xticks([0, 50, 100, 150, 200])
        ax.set_xlabel("누적 P/E 사이클 (천 회)", color=INK2, fontsize=10)
    axes[0].set_ylim(0, 135)
    axes[0].set_ylabel("소거 시간 p50 (ms) · 섹터 7개", color=INK2, fontsize=10)
    axes[0].annotate("약 21ms 계단", (130, 96), xytext=(40, 118), fontsize=10.5, color=INK,
                     arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    fig.tight_layout(pad=0.6)
    fig.savefig(out_png, facecolor=SURFACE)
    plt.close(fig)
    print(f"→ {out_png}")


def ratios(chip, fresh):
    bins = load(chip)
    last = max(b for b in bins if b <= 99_001)
    first = min(bins)
    erase = median(v[0] for v in bins[last].values()) / fresh[chip]
    program = median(v[1] for v in bins[last].values()) / median(v[1] for v in bins[first].values())
    return last, erase, program


RATIO_COLORS = {"chip04": "#2a78d6", "chip18": "#006300", "chip01": "#eb6834", "chip02": MUTED, "chip09": "#1baf7a", "chip06": "#eda100",
                "chip03": "#eda100", "chip15": "#d0453a", "chip07": "#e87ba4"}   # plot_wear_curves.CHIP_COLORS 와 같다


def plot_ratio(out_png):
    fresh = fresh_ms()
    fig, axes = plt.subplots(1, 2, figsize=(7.21, 4.2), sharey=True, dpi=220)
    fig.set_facecolor(SURFACE)
    for ax, title, chips in ((axes[0], "빠른 무리 (신품 40ms 미만)", ["chip01", "chip18", "chip04", "chip06", "chip09", "chip02"]),
                             (axes[1], "느린 무리 (신품 40ms 이상)", ["chip15", "chip03", "chip07"])):
        style(ax)
        ends = []
        for c in chips:
            bins = load(c)
            keys = sorted(b for b in bins if b <= 99_001)
            per = [[v[0] / fresh[c] for v in bins[b].values()] for b in keys]
            x = [(b + 500) / 1e3 for b in keys]
            ax.fill_between(x, [min(v) for v in per], [max(v) for v in per], color=RATIO_COLORS[c], alpha=0.10, lw=0)
            y = [median(v) for v in per]
            ax.plot(x, y, color=RATIO_COLORS[c], lw=1.6)
            ends.append([y[-1], c, x[-1]])
        ends.sort()
        for lo, hi in zip(ends, ends[1:]):                     # 끝 라벨 겹침 방지
            hi[0] = max(hi[0], lo[0] + 0.17)
        for y, c, x1 in ends:
            ax.annotate(c[4:], (x1, y), xytext=(4, 0), textcoords="offset points", va="center", fontsize=10, color=INK2)
        ax.set_xlim(0, 110)
        ax.set_xticks([0, 25, 50, 75, 100])
        ax.set_title(title, color=INK, fontsize=11.5, loc="left", fontweight="bold")
        ax.set_xlabel("누적 P/E 사이클 (천 회)", color=INK2, fontsize=10)
    axes[0].set_ylim(0.9, 4.3)
    axes[0].set_ylabel("소거 시간 ÷ 신품값 · 선 섹터 중앙값, 띠 최소-최대", color=INK2, fontsize=9.5)
    fig.tight_layout(pad=0.6)
    fig.savefig(out_png, facecolor=SURFACE)
    plt.close(fig)
    print(f"→ {out_png}")


MARK = {"상온": ("o", MUTED, MUTED), "빠른 노화 형": ("o", "none", MUTED), "65°C": ("s", T65, T65), "85°C": ("^", T85, T85)}
LABELS = {"상온": "상온", "빠른 노화 형": "상온 · 느린 신품 빠른 노화 형", "65°C": "65°C", "85°C": "85°C"}


def plot_temp(out_png):
    fresh = fresh_ms()
    table = {}
    for g, temps in GROUPS.items():
        for t, chips in temps.items():
            for c in chips:
                table[c] = ratios(c, fresh)
                print(f"{g} {t:12} {c} 끝 구간 {table[c][0]:>6} · 소거 {table[c][1]:.2f} · 프로그램 {table[c][2]:.2f}")
    fig, axes = plt.subplots(1, 2, figsize=(5.63, 2.68), dpi=240)
    fig.set_facecolor(SURFACE)
    seen = {}
    for ax, idx, title in ((axes[0], 1, "소거 100k ÷ 신품"), (axes[1], 2, "프로그램 100k ÷ 첫 1k")):
        style(ax)
        ax.tick_params(labelsize=8.5)
        ax.grid(False, axis="x")
        for gx, (g, temps) in enumerate(GROUPS.items()):
            for t, chips in temps.items():
                off = {"상온": -0.2, "빠른 노화 형": 0.0, "65°C": 0.0, "85°C": 0.2}[t]
                marker, fc, ec = MARK[t]
                for c in chips:
                    h = ax.scatter(gx + off, table[c][idx], s=26, marker=marker, facecolor=fc, edgecolor=ec, linewidth=1.0, zorder=3)
                    seen[LABELS[t]] = h
                    if t in ("65°C", "85°C"):
                        ax.annotate(c[4:], (gx + off, table[c][idx]), xytext=(5, 0), textcoords="offset points", va="center", fontsize=7.5, color=INK2)
        ax.set_xlim(-0.5, 1.55)
        ax.set_xticks([0, 1], ["빠른 무리", "느린 무리"], color=INK2)
        ax.set_title(title, color=INK, fontsize=9.5, loc="left", fontweight="bold")
    axes[0].set_ylim(1, 4.6)
    axes[1].set_ylim(0.9, 2.3)
    order = [LABELS[k] for k in ("상온", "65°C", "85°C", "빠른 노화 형")]
    fig.legend([seen[k] for k in order], order, loc="lower center", ncol=4, frameon=False, fontsize=7.5, labelcolor=INK2, handletextpad=0.1, columnspacing=0.9)
    fig.tight_layout(rect=(0, 0.09, 1, 1), pad=0.4)
    fig.savefig(out_png, facecolor=SURFACE)
    plt.close(fig)
    print(f"→ {out_png}")


def main():
    ap = argparse.ArgumentParser(description="최종 발표 슬라이드 그림")
    ap.add_argument("-o", "--out", default=str(REPO / "build" / "deck"))
    args = ap.parse_args()
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plot_erase(out / "deck_erase_200k.png")
    plot_temp(out / "deck_temp_100k.png")
    plot_ratio(out / "deck_ratio_100k.png")


if __name__ == "__main__":
    main()
