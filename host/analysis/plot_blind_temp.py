# plot_blind_temp.py — 온도 칩 블라인드(chip23 · chip26, 2026-11-01) 그림: 무리별 소거 배율 곡선 위에 개봉 newchip 관측과 v4.3 추정을 겹친다
#
# 사용: uv run python host/analysis/plot_blind_temp.py -o docs/results/plots/blind_temp_chip23_chip26_2026-11.png
#
# 곡선은 섹터 0-6 의 1k 구간 p50 중앙값 ÷ 신품값(temp_wear_summary.ratio_curve). 관측 배율은 개봉 prep 의 섹터 0-6 중앙값 ÷ 같은 prep 의 32-127 중앙값
# (모델의 ratio 눈금). 추정 구간 · 정답은 build/inverse/blind_<chip>_2026-11-01.txt · 장부에서 옮겨 적은 값 — 아래 BLIND

import argparse
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from temp_wear_summary import (CURVES_DIR, SURFACE, INK, INK2, MUTED, HOT, MEAS,   # noqa: E402
                               fresh_values, latest, ratio_curve, style)

# 칩: (관측 배율, 정답, 사후 평균, 68%, 95%) — 구간은 1k 칸의 끝값
BLIND = {"chip26": (67143 / 25268.5, 70000, 60500, (31000, 85000), (25000, 100000)),
         "chip23": (89386 / 48835.0, 26528, 92500, (91000, 100000), (78000, 100000))}
PANELS = [("빠른 무리 — chip26 (84°C 이력, 정답 70,000)", "chip26",
           ("chip01", "chip02", "chip04", "chip06", "chip09", "chip18"), (), ("chip24",)),
          ("느린 무리 — chip23 (85°C 이력, 정답 26,528)", "chip23",
           ("chip03", "chip07", "chip15"), ("chip12", "chip21"), ("chip22",))]


def curve(chip, fresh):
    p = sorted(CURVES_DIR.glob(f"wear_curves_{chip}_*.csv"))
    p = [q for q in p if "_nocal" in q.name or q.name.count("_") == 3] or p   # 상온 · _nocal 우선, 없으면 온도 곡선
    x, y = ratio_curve(p[-1], fresh[chip])
    m = x <= 100000
    return x[m] / 1e3, y[m]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()
    fresh = fresh_values()
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    for ax, (title, chip, calib, same_type, other_temp) in zip(axes, PANELS):
        style(ax)
        for i, c in enumerate(calib):
            x, y = curve(c, fresh)
            ax.plot(x, y, color=MUTED, lw=1.1, alpha=0.85, label="상온 교정 칩" if i == 0 else None)
            ax.annotate(c[4:], (x[-1], y[-1]), xytext=(3, 0), textcoords="offset points", va="center", fontsize=7.5, color=MUTED)
        for i, c in enumerate(same_type):
            x, y = curve(c, fresh)
            ax.plot(x, y, color=INK2, lw=1.1, ls=(0, (1.5, 2)), label="상온 · 느린 신품 빠른 노화 형 (교정 밖)" if i == 0 else None)
            ax.annotate(c[4:], (x[-1], y[-1]), xytext=(3, 0), textcoords="offset points", va="center", fontsize=7.5, color=INK2)
        for c in other_temp:
            x, y = ratio_curve(sorted(CURVES_DIR.glob(f"wear_curves_{c}_8?C_*.csv"))[-1], fresh[c])
            ax.plot(x / 1e3, y, color=INK2, lw=1.1, ls=(0, (5, 2)), label=f"{c} (85°C 이력, 정답 100k)")
        x, y = ratio_curve(sorted(CURVES_DIR.glob(f"wear_curves_{chip}_8?C_*.csv"))[-1], fresh[chip])
        ax.plot(x / 1e3, y, color=HOT, lw=2.2, label=f"{chip} 마모 중 곡선 (85°C)")
        obs, truth, mean, i68, i95 = BLIND[chip]
        ax.axhline(obs, color=MEAS, lw=0.8, ls=(0, (2, 2)))
        ax.plot([i95[0] / 1e3, i95[1] / 1e3], [obs, obs], color=MEAS, lw=2, solid_capstyle="butt", label="v4.3 추정 95% · 68% 구간")
        ax.plot([i68[0] / 1e3, i68[1] / 1e3], [obs, obs], color=MEAS, lw=6, solid_capstyle="butt", alpha=0.85)
        ax.scatter([mean / 1e3], [obs], marker="D", s=46, color=MEAS, edgecolor=SURFACE, lw=1.5, zorder=4, label="추정 (사후 평균)")
        ax.scatter([truth / 1e3], [obs], marker="o", s=70, facecolor=SURFACE, edgecolor=INK, lw=1.8, zorder=5, label="정답")
        ax.annotate(f"개봉 newchip 관측 {obs:.2f}배", (1, obs), xytext=(0, 5), textcoords="offset points", fontsize=8, color=INK2)
        ax.set_title(title, color=INK, fontsize=10.5, loc="left")
        ax.set_xlim(0, 112)
        ax.set_ylim(0.45 if same_type else 1.0, None)                  # 느린 칸은 범례 자리를 곡선 아래로
        ax.set_xlabel("누적 P/E 사이클 (k)", color=INK2, fontsize=9)
        ax.legend(loc="lower right", frameon=False, fontsize=7.5, labelcolor=INK2)
    axes[0].set_ylabel("소거 시간 ÷ 신품값 (섹터 0-6)", color=INK2, fontsize=9)
    fig.tight_layout()
    fig.savefig(a.out, facecolor=SURFACE)


if __name__ == "__main__":
    main()
