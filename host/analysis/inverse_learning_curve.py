# inverse_learning_curve.py — 교정 칩 수 k 에 따른 역산 성능 (학습 곡선) — 「교정을 늘려도 안 좋아진다(포화)」 를 숫자로 (로그 52 §16)
#
# 사용: uv run python host/analysis/inverse_learning_curve.py [--reps 5] [--out build/inverse/lc] [--plot docs/results/plots/inverse_learning_curve_2026-10.png]
#
# 방법 (결과 전 고정):
#   · 무리마다 따로. 교정 칩(접미사 없는 곡선 · 신품 40ms 경계)에서 k 칩을 고르는 **모든 조합**마다, 고른 k 칩으로만 교정하고
#     같은 무리의 **나머지 칩 전부**를 LOCO 와 같은 12개 정답 지점(1k · 3k · 10k-100k)에서 맞힌다
#   · 관측 = 등록 LOCO 와 같은 rows P5(그 1k 구간 A 행에서 사이클 5개) × reps 회. 모델 = 기본(MODEL_VERSION, v4.3) 그대로 —
#     R 은 고른 k 칩의 속도 흩어짐에서 유도되므로 k = 1 이면 R = 1. ρ 는 등록값 고정(9칩 전체로 잰 값 — 약한 누설, 문서에 적음)
#   · 지표: 68 · 95% HPD 적중률 · 배율 오차 |ln(추정/정답)| 평균(추정 = 모델의 대표값) · 68% 폭 중앙값. 조합마다 내고, k 의 값은 조합
#     평균 · 오차 막대는 조합 간 표준오차
#   · 포화 판정: k* = 그 뒤의 모든 k → k+1 에서 배율 오차 · 68% · 95% 적중의 변화가 전부 두 k 의 조합 간 표준오차 합 안에 드는 가장 작은 k.
#     (처음엔 배율 오차 하나로만 정했는데, reps 1 시험에서 k=1 의 표준오차가 커서 95% 적중이 46 → 79% 로 뛰는데도 「k=1 포화」 로 나왔다 —
#      지표 하나는 검정력이 모자라 셋 다 보도록 고쳤다. 본 측정(reps 5) 전, 2026-10-23)

import argparse
import itertools
import json
import math
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wear_inverse as wi  # noqa: E402

SPLIT = 40_000


def run(reps, seed=0):
    curves, fresh = wi.load_curves(), wi.load_fresh()
    arows = {c: wi.ARows.load(c) for c in curves}
    groups = {"fast": sorted(c for c in curves if fresh[c] < SPLIT), "slow": sorted(c for c in curves if fresh[c] >= SPLIT)}
    out = []
    for grp, chips in groups.items():
        for k in range(1, len(chips)):
            for cal in itertools.combinations(chips, k):
                sub = {c: curves[c] for c in cal}
                hits68, hits95, lnerr, widths = [], [], [], []
                for test in (c for c in chips if c not in cal):
                    for cyc in wi.LOCO_CYCLES:
                        b = (cyc - 1) // 1000 * 1000 + 1
                        if b not in curves[test]:
                            continue
                        rng = random.Random(f"{seed}:{test}:{cyc}")
                        for _ in range(reps):
                            worn = arows[test].sample_rows(b, 5, rng)
                            r = wi.invert(fresh[test], worn, sub, fresh, "ratio", SPLIT, None, preps=5)
                            est = r.get("point", r["median"])[0] + 499.5
                            hits68.append(any(a <= cyc <= z for a, z in r["hpd68"]))
                            hits95.append(any(a <= cyc <= z for a, z in r["hpd95"]))
                            lnerr.append(abs(math.log(est / cyc)))
                            widths.append(sum(z - a + 1 for a, z in r["hpd68"]))
                out.append({"group": grp, "k": k, "cal": list(cal), "n": len(lnerr),
                            "in68": sum(hits68) / len(hits68), "in95": sum(hits95) / len(hits95),
                            "lnerr": sum(lnerr) / len(lnerr), "w68": st.median(widths)})
    return out


def summarize(rows):
    res = {}
    for grp in ("fast", "slow"):
        for k in sorted({r["k"] for r in rows if r["group"] == grp}):
            rs = [r for r in rows if r["group"] == grp and r["k"] == k]
            def ms(key):
                v = [r[key] for r in rs]
                m = sum(v) / len(v)
                se = (st.stdev(v) / math.sqrt(len(v))) if len(v) > 1 else 0.0
                return m, se
            res[(grp, k)] = {"combos": len(rs), "in68": ms("in68"), "in95": ms("in95"), "lnerr": ms("lnerr"), "w68": ms("w68")}
    return res


def saturation(res, grp):
    ks = sorted(k for g, k in res if g == grp)
    def flat(k):
        return all(abs(res[(grp, k)][m][0] - res[(grp, k + 1)][m][0]) <= res[(grp, k)][m][1] + res[(grp, k + 1)][m][1]
                   for m in ("lnerr", "in68", "in95"))
    for k in ks[:-1]:
        if all(flat(j) for j in ks[ks.index(k):-1]):
            return k
    return None


def render(res):
    lines = ["| 무리 | 교정 칩 k | 조합 | 68% 적중 | 95% 적중 | 배율 오차 \\|ln\\| | 68% 폭 (사이클) |", "|---|---|---|---|---|---|---|"]
    for (grp, k), v in sorted(res.items()):
        f = lambda key, pct=True: (f"{v[key][0]:.1%} ± {v[key][1]:.1%}" if pct else f"{v[key][0]:.3f} ± {v[key][1]:.3f}")
        lines.append(f"| {'빠른' if grp == 'fast' else '느린'} | {k} | {v['combos']} | {f('in68')} | {f('in95')} | {f('lnerr', False)} | "
                     f"{v['w68'][0]:,.0f} |")
    for grp in ("fast", "slow"):
        s = saturation(res, grp)
        lines.append(f"\n포화 지점({'빠른' if grp == 'fast' else '느린'}): " + (f"k = {s} (그 뒤 k → k+1 에서 배율 오차 · 68% · 95% 적중 변화가 모두 조합 간 표준오차 합 안)" if s else "판정 안 됨 (마지막 k 까지 변화가 표준오차를 넘거나 점이 부족)"))
    return "\n".join(lines)


def plot(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    SURFACE, INK, INK2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
    C68, C95, CERR = "#2a78d6", "#eb6834", "#1baf7a"
    fig, axes = plt.subplots(2, 2, figsize=(10, 6.4), dpi=160, sharex="col")
    fig.set_facecolor(SURFACE)
    for j, grp in enumerate(("fast", "slow")):
        ks = sorted(k for g, k in res if g == grp)
        for i, ax in enumerate(axes[:, j]):
            ax.set_facecolor(SURFACE)
            ax.grid(True, color=GRID, lw=0.7)
            ax.set_axisbelow(True)
            for side in ("right", "top"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(BASELINE)
            ax.tick_params(colors=INK2, labelsize=8.5)
        ax = axes[0, j]
        for key, col, nom, lab in (("in68", C68, 0.68, "68% 적중"), ("in95", C95, 0.95, "95% 적중")):
            y = [res[(grp, k)][key][0] for k in ks]
            e = [res[(grp, k)][key][1] for k in ks]
            ax.errorbar(ks, y, yerr=e, color=col, lw=2, marker="o", ms=6, mec=SURFACE, mew=1.5, capsize=3, label=lab)
            ax.axhline(nom, color=col, lw=1, ls=(0, (4, 3)), alpha=0.7)
            ax.annotate(f"명목 {nom:.0%}", (ks[0], nom), xytext=(2, 3), textcoords="offset points", va="bottom", fontsize=8, color=INK2)
        ax.set_ylim(0.2, 1.04)
        ax.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0, decimals=0))
        ax.set_title(f"{'빠른' if grp == 'fast' else '느린'} 무리 — 구간 적중률", color=INK, fontsize=10, loc="left")
        ax.legend(frameon=False, fontsize=8.5, labelcolor=INK2, loc="lower right")
        ax = axes[1, j]
        y = [res[(grp, k)]["lnerr"][0] for k in ks]
        e = [res[(grp, k)]["lnerr"][1] for k in ks]
        ax.errorbar(ks, y, yerr=e, color=CERR, lw=2, marker="o", ms=6, mec=SURFACE, mew=1.5, capsize=3)
        ax.set_ylim(0, max(0.9, max(y) * 1.15))
        ax.set_title("배율 오차 |ln(추정/정답)| — 작을수록 좋음", color=INK, fontsize=10, loc="left")
        ax.set_xlabel("교정 칩 수 k (같은 무리)", color=INK2, fontsize=9)
        ax.set_xticks(ks)
        s = saturation(res, grp)
        if s:
            for a in axes[:, j]:
                a.axvline(s, color=MUTED, lw=1, ls=(0, (2, 2)))
            ax.annotate(f"포화 k = {s}", (s, ax.get_ylim()[1] * 0.92), xytext=(4, 0), textcoords="offset points", fontsize=8.5, color=INK2)
    fig.suptitle("교정 칩을 늘릴수록 처음 보는 칩을 얼마나 더 잘 맞히나 — 조합 평균 ± 표준오차 (v4.3 · rows P5)",
                 color=INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=SURFACE)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--out", default="build/inverse/lc")
    ap.add_argument("--plot")
    a = ap.parse_args()
    rows = run(a.reps)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "combos.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    res = summarize(rows)
    md = render(res)
    (out / "summary.md").write_text(md + "\n", encoding="utf-8")
    print(md)
    if a.plot:
        plot(res, a.plot)


if __name__ == "__main__":
    main()
