# baseline_compare.py — 기준선 비교: 선행식 이진 판별 · 단순 회귀 · 현행 모델을 같은 모의 블라인드(LOCO) 점에서
#
# 사용:
#   uv run python host/analysis/baseline_compare.py [--plot <폴더>]
#
# 방법의 정본은 docs/results/baseline_compare.md 「방법」 절(결과 전에 커밋) — 여기는 그 구현이다. 수치는 사람이
# docs/results/data/baseline_compare_2026-10.md 로 옮긴다
#   ① 이진 판별 (Sakib 외 2018)  α = 관측이 신품 문턱 아래로 떨어지는 비율(논문 4절 식 (1)), 확신도 1 − α ≥ 95% 면 「썼다」.
#                                 문턱: (a) 데이터시트 typ  (b) 다른 신품 칩 섹터 값의 위쪽 끝  (c) (b) 를 배율로
#   ② 단순 회귀                   같은 무리 나머지 교정 칩의 평균 배율 곡선을 거꾸로 읽는다 — 숫자 하나
#   ③ 현행 모델                   wear_inverse.loco 그대로
# 양성 = LOCO 점(관측은 그 1k 구간의 섹터 0-6 p50 일곱 개), 음성 = 신품을 잰 칩의 newchip prep 섹터 0-6.
# 신품 섹터 원자료는 data/session_*.log (리포 밖) — 로그가 없으면 돌지 않는다

import argparse
import math
import statistics
from pathlib import Path

import wear_inverse as wi

SPLIT_US = 40_000                          # 무리 경계 — wear_inverse 의 기본(--split-ms 40)
DATASHEET_TYP_US = {"IG": 60_000, "IQ": 45_000}   # W25Q64FV Rev L 4KB 섹터 소거 typ (docs/ref/w25q64fv_datasheet_revl.pdf 76쪽)
SUFFIX = {"chip01": "IG", "chip02": "IQ", "chip03": "IG", "chip04": "IG", "chip06": "IQ", "chip07": "IG", "chip08": "IG",
          "chip09": "IQ", "chip15": "IG", "chip16": "IG", "chip18": "IG"}   # IC 윗면 마킹 끝자리 (docs/chip_registry.md) — 없는 칩은 미확인 → IG 로 둔다
FRESH_SESSIONS = {                         # 칩의 신품 newchip prep 세션 — 집계표가 소거 값으로 채택한 것 (chip14 는 등록 세션)
    "chip01": "20260922T153213Z", "chip02": "20260915T153852Z", "chip03": "20260915T155433Z", "chip04": "20260916T125643Z",
    "chip06": "20260916T162838Z", "chip07": "20260920T071531Z", "chip08": "20260920T072456Z", "chip09": "20260920T072000Z",
    "chip10": "20260920T072822Z", "chip12": "20260930T160205Z", "chip14": "20261001T061625Z", "chip15": "20260930T161054Z",
    "chip16": "20261001T063724Z", "chip17": "20260930T162156Z", "chip18": "20260930T161746Z",
}
CONFIDENCE = 0.95                          # 확신도 1 − α 가 이 이상이면 「썼다」
SUBSETS = (("전체", lambda g, x: True), ("x ≤ 20k", lambda g, x: x <= 20_000), ("x 20-50k", lambda g, x: 20_000 < x <= 50_000),
           ("x 50k 초과", lambda g, x: x > 50_000), ("빠른 무리", lambda g, x: g == "fast"), ("느린 무리", lambda g, x: g == "slow"))


# ---------- 입력 ----------

def load_fresh_sectors():
    """신품 prep 로그 → {chip: {sector: 소거 µs}} (섹터 0-127, 섹터당 한 번)."""
    out = {}
    for chip, stamp in FRESH_SESSIONS.items():
        paths = sorted((wi.REPO / "data").glob(f"session_{chip}_*_{stamp}.log"))
        if not paths:
            raise SystemExit(f"{chip} 의 신품 prep 로그가 없다: data/session_{chip}_*_{stamp}.log")
        erase, _ = wi.parse_prep_logs(paths)
        out[chip] = {s: v[0] for s, v in erase.items()}
    return out


# ---------- ① 이진 판별 ----------

def confidence(obs, threshold):
    """확신도 1 − α. α = 관측(쓴 칩의 섹터 값)이 신품 문턱 아래로 떨어지는 비율 — 논문 4절 식 (1)."""
    return sum(v > threshold for v in obs) / len(obs)


def upper(pool, q):
    """신품 분포의 위쪽 끝 — q 1 이면 최댓값, 아니면 그 분위."""
    pool = sorted(pool)
    return pool[min(len(pool) - 1, math.ceil(q * len(pool)) - 1)]


def fresh_pool(sectors, exclude, ratio):
    """판정받는 칩을 뺀 신품 칩들의 섹터 값 — ratio 면 칩마다 자기 섹터 32-127 중앙값으로 나눈다."""
    pool = []
    for chip, sec in sectors.items():
        if chip == exclude:
            continue
        div = statistics.median(sec[s] for s in wi.REFERENCE) if ratio else 1.0
        pool += [v / div for v in sec.values()]
    return pool


def binary(chip, obs_us, ref_us, sectors, q=1.0):
    """한 점의 확신도 → ((a), (b), (c)). q 는 신품 위쪽 끝의 분위(민감도용)."""
    a = confidence(obs_us, DATASHEET_TYP_US[SUFFIX.get(chip, "IG")])
    b = confidence(obs_us, upper(fresh_pool(sectors, chip, False), q))
    c = confidence([v / ref_us for v in obs_us], upper(fresh_pool(sectors, chip, True), q))
    return a, b, c


# ---------- ② 단순 회귀 ----------

def regress(chip, obs_ratio, curves, fresh):
    """같은 무리 나머지 칩의 평균 배율 곡선(줄지 않게 다듬음)이 관측 배율과 처음 만나는 사이클."""
    grp = wi.group_of(fresh[chip], SPLIT_US)
    rest = [c for c in curves if c != chip and wi.group_of(fresh[c], SPLIT_US) == grp]
    pts, top = [(1.0, 0)], 1.0
    for b in sorted({b for c in rest for b in curves[c] if b <= wi.MAX_CYCLE}):
        top = max(top, statistics.mean(statistics.median(p50 for _, p50, _ in curves[c][b].values()) / fresh[c]
                                       for c in rest if b in curves[c]))
        pts.append((top, b + 999))
    if obs_ratio <= 1:
        return 0.0
    for (r0, x0), (r1, x1) in zip(pts, pts[1:]):
        if r1 >= obs_ratio:
            return x0 + (x1 - x0) * (obs_ratio - r0) / (r1 - r0)
    return float(wi.MAX_CYCLE)


# ---------- 지표 · 출력 ----------

def point_cell(pairs):
    """[(정답, 추정)] → 「추정 ÷ 정답 중앙값 · 절대 오차 중앙값 · |ln| 중앙값」. 추정 0 은 ln 을 위해 1 로 본다."""
    med = statistics.median
    return (f"{med(e / x for x, e in pairs):.2f} · {med(abs(e - x) for x, e in pairs):,.0f} · "
            f"{med(abs(math.log(max(e, 1) / x)) for x, e in pairs):.2f}")


def frac(flags):
    return f"{sum(flags)}/{len(flags)}"


INK, INK2, RULE, GRID, SURFACE = "#0b0b0b", "#52514e", "#c3c2b7", "#ebeae6", "#fcfcfb"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"


def _axes(ax, cycles):
    """두 그림 공통 — 바탕 · 격자 · 축 색, x 는 LOCO 지점을 같은 간격으로."""
    ax.set_facecolor(SURFACE)
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(RULE)
    ax.tick_params(colors=INK2, labelsize=8)
    ax.set_xticks(range(len(cycles)), [f"{c // 1000}k" for c in cycles])
    ax.set_xlabel("실제로 쓴 횟수 (누적 P/E)", fontsize=9, color=INK2)


def plot_binary(flags, nflags, path):
    """① 이진 판별 — 무리별 두 칸, 지점마다 쓴 칩 중 「썼다」 로 잡은 비율. 정답은 언제나 100%."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    cycles = list(wi.LOCO_CYCLES)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), sharey=True, facecolor=SURFACE)
    for ax, (grp, title) in zip(axes, (("fast", "빠른 무리 — 신품 소거 26-34ms"), ("slow", "느린 무리 — 신품 소거 47-51ms"))):
        _axes(ax, cycles)
        n = len({c for c, g, _ in flags if g == grp})
        for i, (name, color, marker) in enumerate((("선행 연구 그대로 (데이터시트 기준)", BLUE, "o"), ("선행 판정, 기준만 신품 실측으로", ORANGE, "s"),
                                                     ("선행 판정 + 우리 정규화", AQUA, "D"))):
            pts = [(k, [f[i] for (_, g, x), f in flags.items() if g == grp and x == c]) for k, c in enumerate(cycles)]
            ax.plot([k for k, v in pts], [statistics.mean(v) * 100 for _, v in pts], color=color, lw=2.2, marker=marker, ms=7,
                    markeredgecolor=SURFACE, markeredgewidth=1, label=name, zorder=3, clip_on=False)
        ax.axhline(100, color=INK2, lw=2, ls=(0, (5, 3)), zorder=6)
        ax.set_ylim(0, 112)
        ax.set_yticks(range(0, 101, 20))
        ax.set_title(f"{title} · {n}칩", fontsize=11, color=INK, loc="left")
    axes[0].text(0, 103, "정답 — 모든 지점이 쓴 칩이다 (100%)", fontsize=9, color=INK, va="bottom")
    axes[0].set_ylabel("쓴 칩 중 「썼다」 로 잡은 비율 (%)", fontsize=9, color=INK2)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=3, frameon=False, fontsize=9, labelcolor=INK2)
    fig.suptitle("쓴 칩을 「썼다」 로 잡았나 — 선행 연구 방식은 빠른 칩을 수만 번 쓸 때까지 신품으로 통과시킨다", fontsize=12.5, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.905, f"점선 아래로 떨어진 만큼이 쓴 칩을 신품으로 잘못 통과시킨 것 · 신품 {len(nflags)}칩은 세 방법 모두 「안 썼다」 로 맞혔다"
             f" (오경보 {sum(f[0] for f in nflags.values())} · {sum(f[1] for f in nflags.values())} · {sum(f[2] for f in nflags.values())})",
             fontsize=9, color=INK2, ha="left")
    fig.tight_layout(rect=(0, 0.06, 1, 0.9))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)


def plot_estimate(pos, path):
    """② · ③ 횟수 추정 — 지점마다 정답 · 우리 모델의 추정과 68% 구간 · 단순 회귀의 추정, 칩을 나란히."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    cycles = list(wi.LOCO_CYCLES)
    chips = sorted({p[0] for p in pos})
    fig, ax = plt.subplots(figsize=(10, 5.6), facecolor=SURFACE)
    _axes(ax, cycles)
    for k, c in enumerate(cycles):
        ax.plot([k - 0.42, k + 0.42], [c / 1000] * 2, color=INK, lw=1.6, zorder=2, label="정답" if k == 0 else None)
    for chip, _, cyc, _, est2, est3, _, _, h68 in pos:
        x = cycles.index(cyc) + (chips.index(chip) - (len(chips) - 1) / 2) * 0.12
        first = (chip, cyc) == pos[0][0:3:2]
        ax.plot([x, x], [h68[0][0] / 1000, h68[-1][1] / 1000], color=BLUE, alpha=0.35, lw=3, solid_capstyle="round", zorder=3,
                label="우리 모델 68% 구간" if first else None)
        ax.plot(x, est3 / 1000, marker="o", ms=5, color=BLUE, markeredgecolor=SURFACE, markeredgewidth=0.8, ls="none", zorder=5,
                label="우리 모델 추정" if first else None)
        ax.plot(x, est2 / 1000, marker="D", ms=4.5, color=ORANGE, markeredgecolor=SURFACE, markeredgewidth=0.8, ls="none", zorder=4,
                label="단순 회귀 추정 (구간 없음)" if first else None)
    ax.set_ylim(0, 102)
    ax.set_ylabel("추정한 횟수 (천 회)", fontsize=9, color=INK2)
    ax.legend(frameon=False, fontsize=8.5, loc="upper left", labelcolor=INK2)
    fig.suptitle("몇 번 썼나 — 우리 모델도 단순 회귀만큼 빗나가지만, 그 범위를 구간으로 말한다", fontsize=12.5, color=INK, x=0.01, ha="left")
    fig.text(0.01, 0.905, f"검은 선(정답)에 가까울수록 잘 맞힌 것 · 막대가 선을 품으면 구간이 맞은 것 (68% 구간 {sum(p[6] for p in pos)}/{len(pos)}) · "
             "지점마다 교정 7칩을 하나씩 빼고 맞힌 값", fontsize=9, color=INK2, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)


def main():
    ap = argparse.ArgumentParser(description="기준선 비교 — 선행식 이진 판별 · 단순 회귀 · 현행 모델")
    ap.add_argument("--plot", metavar="폴더", help="그림 두 장을 이 폴더에 — baseline_compare_binary · _estimate (PNG)")
    args = ap.parse_args()
    curves, fresh = wi.load_curves(), wi.load_fresh()
    sectors = load_fresh_sectors()
    rows = wi.loco(curves, fresh, "ratio", SPLIT_US, rate_range=None)

    pos = []                               # LOCO 점마다 (칩, 무리, 정답, 관측 µs 7개, ② 추정, ③ 추정, ∈68, ∈95, 68% 구간)
    for chip, cyc, med, h68, _, in68, in95 in rows:
        obs = [p50 for _, p50, _ in curves[chip][(cyc - 1) // 1000 * 1000 + 1].values()]
        est2 = regress(chip, statistics.median(obs) / fresh[chip], curves, fresh)
        pos.append((chip, wi.group_of(fresh[chip], SPLIT_US), cyc, obs, est2, sum(med) / 2, in68, in95, h68))
    neg = [(chip, [sec[s] for s in wi.WORN], statistics.median(sec[s] for s in wi.REFERENCE)) for chip, sec in sorted(sectors.items())]

    print(f"기준선 비교 · 교정 칩 {sorted(curves)} · LOCO {len(pos)}점 · 신품 {len(neg)}칩 · 모델 {wi.MODEL_VERSION}\n")

    print("## 점 추정 — 추정 ÷ 정답 중앙값 · 절대 오차 중앙값 · |ln(추정 ÷ 정답)| 중앙값\n")
    print("| 부분 | 점 | ② 단순 회귀 | ③ 현행 모델 | ③ 정답∈68% | ③ 정답∈95% | ③ 68% 폭 중앙값 |\n|---|---|---|---|---|---|---|")
    for name, keep in SUBSETS:
        sub = [p for p in pos if keep(p[1], p[2])]
        print(f"| {name} | {len(sub)} | {point_cell([(p[2], p[4]) for p in sub])} | {point_cell([(p[2], p[5]) for p in sub])} | "
              f"{frac([p[6] for p in sub])} | {frac([p[7] for p in sub])} | {statistics.median(sum(z - a + 1 for a, z in p[8]) for p in sub):,.0f} |")
    print(f"\n② 가 곡선 끝({wi.MAX_CYCLE:,})에 붙은 점: {frac([p[4] >= wi.MAX_CYCLE for p in pos])}")

    judged = {p[:3]: binary(p[0], p[3], fresh[p[0]], sectors) for p in pos}
    flags = {k: tuple(v >= CONFIDENCE for v in j) for k, j in judged.items()}
    print("\n## ① 이진 판별 — 검출 (「썼다」 로 판정한 점 / 점)\n")
    print("| 정답 x | 빠른 (a) 데이터시트 | 빠른 (b) 신품 분포 | 빠른 (c) 정규화 뒤 | 느린 (a) | 느린 (b) | 느린 (c) |\n|---|---|---|---|---|---|---|")
    for cyc in wi.LOCO_CYCLES + (None,):
        cells = [frac([f[i] for (_, g, x), f in flags.items() if g == grp and cyc in (x, None)])
                 for grp in ("fast", "slow") for i in range(3)]
        print(f"| {'**전체**' if cyc is None else format(cyc, ',')} | " + " | ".join(cells) + " |")
    print("\n전체(두 무리): " + " · ".join(f"({n}) {frac([f[i] for f in flags.values()])}" for i, n in enumerate("abc")))
    for i, n in enumerate("abc"):
        print(f"({n}) 가 놓친 점 (확신도): " + " · ".join(f"{chip} {x:,} ({j[i]:.0%})" for (chip, _, x), j in judged.items() if j[i] < CONFIDENCE))

    print("\n## ① 이진 판별 — 신품 칩 (오경보)\n")
    print("| 칩 | 무리 | 섹터 0-6 중앙값 ms | (a) typ ms | (a) 확신도 | (b) 문턱 ms | (b) 확신도 | (c) 문턱 배율 | (c) 확신도 |\n|---|---|---|---|---|---|---|---|---|")
    nflags = {}
    for chip, obs, ref in neg:
        j = binary(chip, obs, ref, sectors)
        nflags[chip] = tuple(v >= CONFIDENCE for v in j)
        typ = DATASHEET_TYP_US[SUFFIX.get(chip, "IG")] / 1000
        print(f"| {chip} | {'빠른' if wi.group_of(ref, SPLIT_US) == 'fast' else '느린'} | {statistics.median(obs) / 1000:.1f} | "
              f"{typ:g}{'' if chip in SUFFIX else ' (끝자리 미확인)'} | {j[0]:.0%} | {upper(fresh_pool(sectors, chip, False), 1) / 1000:.1f} | {j[1]:.0%} | "
              f"{upper(fresh_pool(sectors, chip, True), 1):.2f} | {j[2]:.0%} |")
    print("\n오경보: " + " · ".join(f"({n}) 15칩 {frac([f[i] for f in nflags.values()])} · 교정 7칩 "
                                 f"{frac([f[i] for c, f in nflags.items() if c in curves])}" for i, n in enumerate("abc")))
    flip = [chip for chip, obs, _ in neg if chip not in SUFFIX and confidence(obs, DATASHEET_TYP_US["IQ"]) >= CONFIDENCE]
    print(f"끝자리 미확인 칩을 IQ(45ms)로 보면 (a) 가 「썼다」 로 바뀌는 칩: {' · '.join(flip) or '없음'}")

    print("\n## 신품 위쪽 끝의 정의 민감도 — (b) · (c) 의 검출 / 오경보\n")
    print("| 신품 위쪽 끝 | (b) 검출 | (b) 오경보 | (c) 검출 | (c) 오경보 |\n|---|---|---|---|---|")
    for q, name in ((1.0, "최댓값 (논문 그대로)"), (0.99, "99번째 백분위")):
        pj = [binary(p[0], p[3], fresh[p[0]], sectors, q) for p in pos]
        nj = [binary(chip, obs, ref, sectors, q) for chip, obs, ref in neg]
        print(f"| {name} | " + " | ".join(frac([j[i] >= CONFIDENCE for j in js]) for i in (1, 2) for js in (pj, nj)) + " |")

    if args.plot:
        plot_binary(flags, nflags, Path(args.plot) / "baseline_compare_binary_2026-10.png")
        plot_estimate(pos, Path(args.plot) / "baseline_compare_estimate_2026-10.png")


if __name__ == "__main__":
    main()
