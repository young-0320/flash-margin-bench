"""욕조 v2 — 닳은 창 대 안 닳은 창 DCD (chip02 · chip03, 발표용 한 장).

입력은 승격된 요약 CSV(`docs/results/data/bathtub_v2_chip0{2,3}_std_2026-11.csv`). chip02 의 A4 두 런(14:25 · 14:26Z,
수정 전 ELF)은 16런 비교에서 뺐던 대로 뺀다. 칩마다 창 8곳의 런별 DCD(작은 점) · 창 평균(큰 점),
안 닳은 6창의 평균(점선)과 95% 예측 구간(띠, 평균 ± t₅ · SD · √(1 + 1/6)) — [D55-37] 판정 그대로.
두 패널의 세로 폭은 같게(±YSPAN) 두어 칩 사이 흔들림 크기를 눈으로 비교할 수 있게 한다.

    uv run python host/analysis/bathtub2_wear_figure.py   → build/bathtub/v2/bathtub_v2_wear_compare.png
"""
import csv
import math
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bathtub_freq_compare import REPO  # noqa: E402
from monte_carlo_sweep_params import BASELINE, INK, INK2, MUTED, RAMP, SURFACE, _style_axes  # noqa: E402

DATA = REPO / "docs" / "results" / "data"
CHIPS = (("chip02", "빠른 무리", "bathtub_v2_chip02_std_2026-11.csv", ("20261117T142542Z", "20261117T142659Z")),
         ("chip03", "느린 무리", "bathtub_v2_chip03_std_2026-11.csv", ()))
ORDER = (0, 7, 32, 48, 64, 80, 96, 121)
UNWORN = (32, 48, 64, 80, 96, 121)
T5 = 2.5706                                   # t 분포 자유도 5 의 97.5% 점
YSPAN = 4.5                                   # 패널 세로 반폭 (ps)
WORN, NEIGHBOR = "#d9622b", RAMP[1]


def load(name, skip):
    with open(DATA / name, newline="") as fh:
        rows = [r for r in csv.DictReader(fh) if not any(s in r["file"] for s in skip)]
    by = {}
    for r in rows:
        by.setdefault(int(r["base_sector"]), []).append(float(r["dcd_ps"]))
    return by


def main():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6))
    for ax, (chip, group, name, skip) in zip(axes, CHIPS):
        _style_axes(fig, ax)
        by = load(name, skip)
        means = {s: st.mean(v) for s, v in by.items()}
        un = [means[s] for s in UNWORN]
        m, sd = st.mean(un), st.stdev(un)
        h = T5 * sd * math.sqrt(1 + 1 / 6)
        ax.axhspan(m - h, m + h, color=BASELINE, alpha=0.35, lw=0, zorder=0)
        ax.axhline(m, color=MUTED, lw=1, ls="--", zorder=1)
        ax.text(len(ORDER) - 0.45, m + h, "안 닳은 6창 95% 예측 구간", ha="right", va="bottom", fontsize=8.5, color=INK2)
        for i, s in enumerate(ORDER):
            col = WORN if s == 0 else NEIGHBOR if s == 7 else MUTED
            ax.plot([i] * len(by[s]), by[s], "o", ms=4, mfc="none", mec=col, mew=1.2, zorder=2)
            ax.plot([i - 0.28, i + 0.28], [means[s]] * 2, color=col, lw=2.5, solid_capstyle="round", zorder=3)
        d = means[0] - m
        ax.annotate(f"닳은 창 {d:+.2f}ps", (0, means[0]), xytext=(0.5, means[0] + (2.3 if d >= 0 else -1.6)),
                    fontsize=9, color=INK, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
        ax.set_xticks(range(len(ORDER)))
        ax.set_xticklabels([f"{s}\n닳음" if s == 0 else f"{s}\n이웃" if s == 7 else str(s) for s in ORDER], color=INK2)
        ax.set_xlim(-0.6, len(ORDER) - 0.4)
        ax.set_ylim(m - YSPAN, m + YSPAN)
        n = len(by[0])
        ax.set_title(f"{chip} ({group}) — 창마다 {n}런, 한 장착", color=INK, fontsize=10)
        ax.set_xlabel("섹터 (창 시작)", color=INK2)
    axes[0].set_ylabel("DCD (ps)", color=INK2)
    fig.suptitle("200k 닳은 창과 안 닳은 창의 DCD — 차이가 런 간 흔들림 안 (25MHz, v2 측정)", color=INK, fontsize=11)
    fig.text(0.5, 0.015, "빈 점 = 런 하나 · 굵은 막대 = 창 평균 · 점선 = 안 닳은 6창 평균. 두 패널 세로 폭은 같다(9ps)",
             ha="center", fontsize=8.5, color=INK2)
    fig.tight_layout(rect=(0, 0.04, 1, 0.95))
    out = REPO / "build" / "bathtub" / "v2" / "bathtub_v2_wear_compare.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=SURFACE)
    print(out)


if __name__ == "__main__":
    main()
