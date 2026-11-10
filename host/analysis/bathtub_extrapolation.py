# bathtub_extrapolation.py — v1 25MHz 벽마다 「바깥 꼬리를 가우시안 하나로 외삽할 수 있는가」 를 판정한다 (워크플로 14 B7 · 로그 55 [U55-4])
#
# 사용: uv run python host/analysis/bathtub_extrapolation.py
#
# 입력: data/sweep_<chip>[_<UID>]_<UTC>.csv — 25MHz(2520 스텝) 런만. 고르기 · 덩어리 · 천장은 bathtub_stats.analyze 그대로
# 벽 = 덩어리 안에서 천장(최댓값의 99% 이상) 바깥 스텝. 바깥(바닥 쪽) → 안쪽(천장 쪽) 순서, x = 바깥 첫 오류 스텝에서 안쪽으로 ps
#   L · R 은 덩어리 기준 (L = 위상이 낮은 쪽, bathtub_stats · bathtub_isi_shelf 와 같다)
# 턱 = 천장의 30-70% 이고 PRBS 이력 부류 개수와 n_reads 이내로 맞는 스텝 (bathtub_isi_shelf 의 exact · near 와 같은 맞춤).
#   벽에서 가장 바깥의 턱 스텝을 「첫 턱」 으로 본다
# 바깥 꼬리 = 바닥과 첫 턱(없으면 천장) 사이 스텝. 기준 높이 C = 천장 BER (턱이 있으면 그 턱 부류 개수 / n_bits = 그 부류만의 천장)
# 쓸 점 = 바깥 꼬리 중 오류 MIN_CNT 개 이상 · BER < FIT_CAP × C. probit 직선 Φ⁻¹(BER/C) = (x - μ)/σ 을 가중 최소제곱으로 맞춘다
#   가중 = 이항 잡음의 z 분산의 역수 — sd_z = √(p(1-p)/n_bits) / (C · φ(z)), p = 관측 BER (델타 방법)
#   잔차 통계량 T = max |잔차 / sd_z| (표준화 잔차의 최댓값)
# T* (문턱) — 이항 잡음만으로 95% 이상이 통과하도록 모의해서 정한다: 점 3개 이상 · 기울기 > 0 인 벽마다 맞춘 (μ, σ) 를 진실로 두고
#   같은 x 에서 오류 수 ~ Binomial(n_bits, C · Φ) 를 NULL_REPS 번 뽑아 같은 규칙(쓸 점 고르기 · 맞춤 · T)을 돌린다.
#   점 수 무리(3 · 4 · 5 이상)마다 T 의 95% 분위수를 내고 그 최댓값을 T* 로 둔다 — 어느 무리도 95% 이상 통과
# 판정
#   가능 = 턱 없음 · 쓸 점 3개 이상 · 기울기 > 0 · T ≤ T*
#   부분 = 턱 있음 · 턱 바깥(가장 바깥 부류) 쓸 점 3개 이상 · C = 그 부류 높이로 기울기 > 0 · T ≤ T* → 그 부류만 외삽
#   불가 = 그 밖 (점 2개 이하 · 턱이 있는데 바깥 부류가 안 맞음 · 잔차 · 기울기)
# 외삽 거리 (가능 · 부분) = 맞춘 직선에서 BER 1e-4 교차 → 1e-9 · 1e-12 교차 거리 (ps, dual-Dirac 처럼 가우시안 하나)
#   d(b) = σ · (Φ⁻¹(1e-4/C) - Φ⁻¹(b/C)). 불확도 = 가중 맞춤의 기울기 표준오차(이항 분산 기준, χ²/자유도 > 1 이면 √(χ²/자유도) 를 곱함)
#   를 d 로 옮긴 1σ. 맞춤 모형이 맞다는 가정 안의 오차다 — 1e-5 아래 꼬리 모양의 오차는 들어 있지 않다
# 검증 (LOO) — monte_carlo_deep_n.misfit() 처럼 가장 바깥 쓸 점을 빼고 안쪽 쓸 점(2개 이상)으로 맞춰 그 점을 예측, 관측 / 예측
#   (가) 판정대로 — 가능 · 부분 벽. 판정이 그 점을 이미 보고 골랐으므로 선택 편향이 있다
#   (나) 정직한 판 — 쓸 점 4개 이상인 벽에서 가장 바깥 점을 뺀 나머지로만 판정하고, 통과한 벽에서 그 점을 예측
#   비교 기준 = 같은 절차의 전 벽 (쓸 점 3개 이상) · monte_carlo_deep_n.misfit() 의 전 벽(로그 55 의 0.011-230)과 가능 벽
# 출력: build/bathtub/v1/extrap/
#   walls.csv · per_chip.csv · summary.txt
#   p1_class_<chip>.png  — bathtub_p1_figures 의 칩 그림에 벽마다 판정 색 (욕조 왼쪽 패널 = 덩어리 R, 오른쪽 = 덩어리 L)
#   example_{ok,partial,no}.png — 판정마다 한 벽: BER 과 맞춘 곡선 · 외삽선 / probit 공간 직선과 잔차

import argparse
import csv
import glob
from collections import Counter, defaultdict
from math import comb
from pathlib import Path
from statistics import NormalDist

import numpy as np

import bathtub_p1_figures as p1
import monte_carlo_deep_n as mc
from bathtub_isi_shelf import SHELF_HI, SHELF_LO, candidates, prbs_pages
from bathtub_stats import CEIL_FRAC, DATA, NAME, N_STEPS, REPO, analyze
from monte_carlo_sweep_params import BASELINE, INK, INK2, MUTED, SURFACE, _style_axes

OUT = REPO / "build" / "bathtub" / "v1" / "extrap"
MIN_CNT = 5               # 쓸 점의 오류 수 하한 — 1개짜리 z 잡음(약 0.3)을 피하고 5개면 약 0.11 (bathtub_freq_compare 와 같은 값)
FIT_CAP = 0.95            # 쓸 점의 BER 상한 = C 의 95% — 천장 근처 Φ⁻¹ 발산 (bathtub_freq_compare · monte_carlo_deep_n 와 같은 값)
MIN_PTS = 3               # 직선 + 잔차를 말하려면 3점 (2점은 늘 맞는다)
NULL_REPS = 200           # 벽마다 이항 잡음 모의 횟수
PASS = 0.95               # 이항 잡음만으로 통과해야 하는 비율
SEED = 20261111
REF, TARGETS = 1e-4, (1e-9, 1e-12)
ND = NormalDist()
PPF = np.vectorize(ND.inv_cdf)
CLS = ("가능", "부분", "불가")
COLOR = {"가능": "#2a78d6", "부분": "#eb6834", "불가": MUTED}   # dataviz 기본 범주 1 · 2 + 회색(불가 = 뒤로 물림), 선 모양도 다르게
TAG = {"가능": "ok", "부분": "partial", "불가": "no"}


def walls(r):
    """런 → 벽 두 개 [(쪽, 오류 수 배열 바깥 → 안쪽)]. 천장 스텝은 뺀다."""
    b = r["e"][(r["first_nz_step"] + np.arange(r["n_block"])) % N_STEPS]
    top = np.flatnonzero(b >= CEIL_FRAC * b.max())
    return [("L", b[:top[0]]), ("R", b[top[-1] + 1:][::-1])], int(b.max())


def ledge(cnt, ceil, cands, nr):
    """가장 바깥 턱 → (위치, 부류 이름, 부류 개수) 또는 None. bathtub_isi_shelf 의 맞춤(exact · near) 그대로."""
    for k, c in enumerate(cnt):
        if SHELF_LO * ceil < c < SHELF_HI * ceil:
            name, v = min(cands, key=lambda cv: abs(int(cv[1].sum()) - int(c)))
            if abs(int(v.sum()) - int(c)) <= nr:
                return k, name, int(v.sum())
    return None


def usable(cnt, C, nbits):
    return (cnt >= MIN_CNT) & (cnt / nbits < FIT_CAP * C)


def fit(x, cnt, C, nbits):
    """가중 probit 직선. 반환 dict(a 기울기, b 절편, cov, T, chi2, z, sd) — x 는 ps, z = a·x + b."""
    p = cnt / nbits
    z = PPF(p / C)
    sd = np.sqrt(p * (1 - p) / nbits) / (C * np.exp(-z * z / 2) / np.sqrt(2 * np.pi))
    w = 1 / sd ** 2
    X = np.column_stack([x, np.ones_like(x)])
    cov = np.linalg.inv(X.T @ (X * w[:, None]))
    a, b = cov @ (X.T @ (w * z))
    s = (z - a * x - b) / sd
    return {"a": a, "b": b, "cov": cov, "T": float(np.abs(s).max()), "chi2": float((s * s).sum()), "z": z, "sd": sd}


def region(w):
    """벽 → 바깥 꼬리 (x ps, 오류 수, C, 턱 정보). 턱이 있으면 그 바깥만, C = 그 부류 높이."""
    cnt = w["cnt"][:w["ledge"][0]] if w["ledge"] else w["cnt"]
    C = (w["ledge"][2] if w["ledge"] else w["ceil"]) / w["nbits"]
    return np.arange(len(cnt)) * w["dphi"], cnt, C


def null_T(w, f, rng):
    """맞춘 (a, b) 를 진실로 이항 잡음만 넣은 [(쓸 점 수, T)]."""
    x, cnt, C = region(w)
    p = C * np.array([ND.cdf(v) for v in f["a"] * x + f["b"]])
    out = []
    for sim in rng.binomial(w["nbits"], p, size=(NULL_REPS, len(x))):
        m = usable(sim, C, w["nbits"])
        if m.sum() < MIN_PTS:
            continue
        g = fit(x[m], sim[m], C, w["nbits"])
        out.append((int(m.sum()), g["T"] if g["a"] > 0 else np.inf))
    return out


def dist(f, C, n):
    """1e-4 교차 → 1e-9 · 1e-12 교차 거리 ps 와 1σ. 기울기 오차만 들어간다."""
    dof = n - 2
    var_a = f["cov"][0, 0] * max(1.0, f["chi2"] / dof)
    out = {}
    for t in TARGETS:
        d = (ND.inv_cdf(REF / C) - ND.inv_cdf(t / C)) / f["a"]
        out[t] = (d, d * np.sqrt(var_a) / f["a"])
    return out


def loo(x, cnt, C, nbits):
    """가장 바깥 쓸 점을 안쪽 쓸 점으로 예측 → (관측 / 예측, 안쪽 맞춤). 쓸 점 3개 미만이면 None."""
    idx = np.flatnonzero(usable(cnt, C, nbits))
    if len(idx) < MIN_PTS:
        return None
    o, inner = idx[0], idx[1:]
    f = fit(x[inner], cnt[inner], C, nbits)
    if f["a"] <= 0:
        return None
    pred = nbits * C * ND.cdf(f["a"] * x[o] + f["b"])
    return (cnt[o] / pred if pred > 0 else np.inf), f, len(inner)


def q(v):
    v = np.asarray(v, float)
    if not len(v):
        return "없음"
    p = np.percentile(v, [5, 25, 50, 75, 95])
    return (f"n {len(v)} — 5 · 25 · 50 · 75 · 95%: " + " · ".join(f"{e:.3g}" for e in p)
            + f" · 10배 넘게 어긋남 {(np.abs(np.log10(v)) > 1).mean() * 100:.0f}%")


def cp95(k, n):
    """이항 비율 k/n 의 95% Clopper-Pearson 구간 — 이분법 (scipy 없이)."""
    def cdf(j, p):
        return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(j + 1))

    def solve(f):                                          # f 는 p 에 대해 감소
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > 0 else (lo, mid)
        return (lo + hi) / 2
    lo = 0.0 if k == 0 else solve(lambda p: 0.025 - (1 - cdf(k - 1, p)))
    hi = 1.0 if k == n else solve(lambda p: cdf(k, p) - 0.025)
    return lo, hi


def plot_chip(plt, chip, rs, ws, out_png):
    """bathtub_p1_figures.plot_chip 의 런 곡선을 쪽마다 판정 색으로 다시 그린다 (평균 곡선은 뺀다)."""
    ui = N_STEPS * rs[0]["dphi"]
    tally = Counter(w["cls"] for w in ws)
    fig, al, ar = p1.panels(plt, f"{chip} — 25MHz 벽 외삽 판정 {len(ws)}벽: "
                            + " · ".join(f"{c} {tally[c]}" for c in CLS))
    side = {(w["utc"], w["side"]): w["cls"] for w in ws}
    style = {"가능": "-", "부분": "--", "불가": ":"}
    xs = []
    for r in rs:
        x, ber, fl = p1.curve(r)
        y = np.where(ber > 0, ber, np.nan)
        z = np.where(ber > 0, np.nan, fl)
        (lx, ly), (rx, ry) = p1.split(x, y, ui)
        (_, lz), (_, rz) = p1.split(x, z, ui)
        for ax, px, py, pz, sd in ((al, lx, ly, lz, "R"), (ar, rx, ry, rz, "L")):
            c = side[(r["utc"], sd)]
            ax.plot(px, py, style[c], color=COLOR[c], lw=1.0, alpha=0.7)
            ax.plot(px, pz, "x", color=MUTED, ms=3, alpha=0.5)
        xs.append(x[ber > 0])
    for c in CLS:
        al.plot([], [], style[c], color=COLOR[c], lw=1.5, label=f"{c} ({tally[c]}벽)")
    al.plot([], [], "x", color=MUTED, ms=4, label="0 errors (1/n_bits)")
    fls = [p1.floor_ps(r) for r in rs]
    allx = np.concatenate(xs)
    text = f"바닥(오류 0) 런별 {min(fls):,.0f} - {max(fls):,.0f}ps"
    fl = min(1 / r["n_bits_per_step"] for r in rs)
    p1.finish(plt, fig, al, ar, ui, fl, p1.ARROW_UP * fl, allx.max(), ui + allx.min(), text, p1.trunc_note(rs), out_png)


def plot_example(plt, w, out_png):
    """한 벽 — 왼쪽: BER(로그)과 맞춘 곡선 · 1e-12 까지 외삽, 오른쪽: probit 공간 직선과 표준화 잔차."""
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    x, cnt, C = region(w)
    xa = np.arange(len(w["cnt"])) * w["dphi"]
    ber = w["cnt"] / w["nbits"]
    m = usable(cnt, C, w["nbits"])
    f = w["fit"]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11, 4.6))
    for ax in (a1, a2):
        _style_axes(fig, ax)
    col = COLOR[w["cls"]]
    nz = ber > 0
    a1.plot(xa[nz], ber[nz], "-o", color=INK2, lw=1, ms=4, mfc="none", label="벽 스텝 (천장 바깥)")
    a1.plot(xa[~nz], np.full((~nz).sum(), 1 / w["nbits"]), "x", color=MUTED, ms=5, label="0 errors (1/n_bits)")
    a1.plot(x[m], cnt[m] / w["nbits"], "o", color=col, ms=8, label=f"맞춤에 쓴 점 ({m.sum()}개)")
    if w["ledge"]:
        k = w["ledge"][0]
        a1.plot(xa[k], ber[k], "s", color=INK, ms=8, mfc="none", label=f"첫 턱 — {w['ledge'][1]}")
    a1.axhline(C, color=BASELINE, lw=1, ls="--")
    a1.text(xa[-1], C / 1.8, "C = " + ("턱 부류 높이" if w["ledge"] else "천장") + f" {C:.3g}", ha="right", color=INK2, fontsize=8)
    if f is not None and f["a"] > 0:
        lo = (ND.inv_cdf(TARGETS[-1] / C) - f["b"]) / f["a"]
        xx = np.linspace(min(lo, 0) - 5, xa[-1], 200)
        yy = C * np.array([ND.cdf(v) for v in f["a"] * xx + f["b"]])
        a1.plot(xx, yy, "-", color=col, lw=2, alpha=0.8, label="맞춘 가우시안 · 외삽")
        for t in (REF,) + TARGETS:
            xt = (ND.inv_cdf(t / C) - f["b"]) / f["a"]
            a1.axhline(t, color=BASELINE, lw=0.8)
            a1.plot([xt], [t], "|", color=col, ms=12, mew=2)
        if w["cls"] != "불가":
            d = w["dist"]
            a1.text(0.02, 0.04, "1e-4 → 1e-9 " + f"{d[1e-9][0]:.1f} ± {d[1e-9][1]:.1f}ps · 1e-4 → 1e-12 {d[1e-12][0]:.1f} ± {d[1e-12][1]:.1f}ps",
                    transform=a1.transAxes, color=INK, fontsize=8.5,
                    bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec=BASELINE, lw=0.8))
        a1.set_xlim(min(lo, 0) - 5, xa[-1] + 5)
    a1.set_yscale("log")
    a1.set_ylim(TARGETS[-1] / 10, 1)
    a1.set_xlabel("바깥 첫 오류 스텝에서 안쪽으로 (ps)", color=INK2)
    a1.set_ylabel("BER", color=INK2)
    a1.legend(frameon=False, fontsize=7.5, loc="upper left")
    if f is not None:
        z, sd = f["z"], f["sd"]
        a2.errorbar(x[m], z, yerr=2 * sd, fmt="o", color=col, ms=6, capsize=3, label=r"$\Phi^{-1}$(BER / C) ± 2 sd (이항)")
        xx = np.linspace(x[m].min() - 5, x[m].max() + 5, 50)
        a2.plot(xx, f["a"] * xx + f["b"], "-", color=INK2, lw=1.2, label="가중 직선")
        for xi, zi, s in zip(x[m], z, (z - f["a"] * x[m] - f["b"]) / sd):
            a2.annotate(f"{s:+.1f}", (xi, zi), textcoords="offset points", xytext=(6, -10), color=INK2, fontsize=8)
        a2.legend(frameon=False, fontsize=8, loc="upper left")
    a2.set_xlabel("바깥 첫 오류 스텝에서 안쪽으로 (ps)", color=INK2)
    a2.set_ylabel(r"z = $\Phi^{-1}$(BER / C)  (숫자 = 표준화 잔차)", color=INK2)
    fig.suptitle(f"{w['cls']} — {w['chip']} {w['utc']} 덩어리 {w['side']} 벽 · {w['reason']}", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0]))
        wr.writeheader()
        wr.writerows({k: (f"{v:.4g}" if isinstance(v, float) else v) for k, v in r.items()} for r in rows)


def main():
    argparse.ArgumentParser(description="v1 25MHz 벽마다 바깥 꼬리의 가우시안 외삽 가능 · 부분 · 불가 판정 (build/bathtub/v1/extrap/)").parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)

    by_chip, ws, cache = defaultdict(list), [], {}
    for p in sorted(glob.glob(str(DATA / "sweep_*.csv"))):
        m = NAME.match(Path(p).name)
        if not m:
            continue
        st, r = analyze(p)
        if st != "ok":
            continue
        r.update(chip=m[1], utc=m[3], file=Path(p).name)
        by_chip[m[1]].append(r)
        with open(p, newline="", encoding="utf-8") as fh:
            row = next(csv.DictReader(fh))
        nr, bb = int(row["n_reads"]), int(row["b_bits"])
        if (nr, bb) not in cache:
            cache[(nr, bb)] = candidates(prbs_pages(nr, bb))
        two, ceil = walls(r)
        for side, cnt in two:
            ws.append({"chip": m[1], "utc": m[3], "file": r["file"], "side": side, "n_reads": nr, "nbits": nr * bb,
                       "dphi": r["dphi"], "ceil": ceil, "cnt": cnt, "ledge": ledge(cnt, ceil, cache[(nr, bb)], nr)})

    # 1. 쓸 점 3개 이상인 벽을 맞추고 이항 잡음 모의로 T* 를 정한다
    sims = []
    for w in ws:
        x, cnt, C = region(w)
        mk = usable(cnt, C, w["nbits"])
        w["n_pts"] = int(mk.sum())
        w["fit"] = fit(x[mk], cnt[mk], C, w["nbits"]) if w["n_pts"] >= MIN_PTS else None
        if w["fit"] is not None and w["fit"]["a"] > 0:
            sims += null_T(w, w["fit"], rng)
    sims = np.array(sims)
    grp = {"3": sims[:, 0] == 3, "4": sims[:, 0] == 4, "5+": sims[:, 0] >= 5}
    q95 = {g: float(np.quantile(sims[s, 1], PASS)) for g, s in grp.items() if s.sum()}
    tstar = max(q95.values())

    # 2. 판정
    for w in ws:
        f, led = w["fit"], w["ledge"]
        if f is None:
            w["cls"], w["reason"] = "불가", (f"턱 바깥 부류 쓸 점 {w['n_pts']}개" if led else f"쓸 점 {w['n_pts']}개")
        elif f["a"] <= 0:
            w["cls"], w["reason"] = "불가", "기울기 ≤ 0"
        elif f["T"] > tstar:
            w["cls"], w["reason"] = "불가", ("턱 바깥 부류 " if led else "") + f"잔차 T {f['T']:.1f} > {tstar:.2f}"
        else:
            w["cls"], w["reason"] = ("부분" if led else "가능"), f"쓸 점 {w['n_pts']}개 · T {f['T']:.2f}"
        w["dist"] = dist(f, region(w)[2], w["n_pts"]) if w["cls"] != "불가" else None

    # 3. LOO
    for w in ws:
        x, cnt, C = region(w)
        w["loo"] = loo(x, cnt, C, w["nbits"])
        w["loo_honest"] = None                             # (나) 바깥 점을 뺀 나머지로만 판정 → 통과하면 그 점 예측
        if w["loo"] is not None and w["loo"][2] >= MIN_PTS:
            g = w["loo"][1]
            w["loo_honest"] = "통과" if g["T"] <= tstar else "탈락"
    mc_d = {}
    for p in sorted({w["file"] for w in ws}):
        for side, mw in zip("LR", mc.walls(str(DATA / p))):
            d = mc.misfit([mw])
            if len(d):
                mc_d[(p, side)] = float(np.exp(d[0]))

    # 출력 — 표
    rows = []
    for w in ws:
        f, d, lg = w["fit"], w["dist"], w["ledge"]
        rows.append({"chip": w["chip"], "utc": w["utc"], "file": w["file"], "side": w["side"], "n_reads": w["n_reads"],
                     "ceil_errors": w["ceil"], "wall_steps": len(w["cnt"]),
                     "ledge_from_outside": lg[0] if lg else "", "ledge_class": lg[1] if lg else "", "ledge_class_count": lg[2] if lg else "",
                     "C_used": region(w)[2], "n_pts": w["n_pts"], "class": w["cls"], "reason": w["reason"],
                     "sigma_ps": 1 / f["a"] if f is not None and f["a"] > 0 else "", "T": f["T"] if f is not None else "",
                     "d_1e4_1e9_ps": d[1e-9][0] if d else "", "d_1e4_1e9_se_ps": d[1e-9][1] if d else "",
                     "d_1e4_1e12_ps": d[1e-12][0] if d else "", "d_1e4_1e12_se_ps": d[1e-12][1] if d else "",
                     "loo_obs_over_pred": float(w["loo"][0]) if w["loo"] else "", "loo_honest_gate": w["loo_honest"] or "",
                     "mc_misfit_obs_over_pred": mc_d.get((w["file"], w["side"]), "")})
    write_csv(OUT / "walls.csv", rows)
    pc = []
    for chip in sorted(by_chip):
        t = Counter(w["cls"] for w in ws if w["chip"] == chip)
        pc.append({"chip": chip, "runs": len(by_chip[chip]), "walls": sum(t.values()), **{c: t[c] for c in CLS}})
    write_csv(OUT / "per_chip.csv", pc)

    # 출력 — 요약
    tot = Counter(w["cls"] for w in ws)
    L = [f"v1 25MHz 런 {sum(len(v) for v in by_chip.values())} · 벽 {len(ws)} (칩 {len(by_chip)})",
         f"기준: 쓸 점 = 오류 {MIN_CNT}개 이상 · BER < {FIT_CAP} × C, 점 {MIN_PTS}개 이상, 가중 probit 직선, T = max |표준화 잔차|",
         f"T* = {tstar:.3f} — 이항 잡음 모의 (맞춘 벽 {sum(w['fit'] is not None and w['fit']['a'] > 0 for w in ws)}개 × {NULL_REPS}회, "
         f"seed {SEED}) 점 수 무리별 95% 분위: " + " · ".join(f"{g}점 {v:.3f} (n {int(grp[g].sum())})" for g, v in q95.items()),
         "  T* 에서 이항 잡음만의 통과율: " + " · ".join(f"{g}점 {(sims[s, 1] <= tstar).mean() * 100:.1f}%" for g, s in grp.items() if s.sum()),
         "", "== 판정 ==",
         "전체: " + " · ".join(f"{c} {tot[c]}" for c in CLS),
         "불가 사유: " + " · ".join(f"{k} {v}" for k, v in Counter(
             ("턱 + " if w["ledge"] else "") + ("점 부족" if w["fit"] is None else "기울기" if w["fit"]["a"] <= 0 else "잔차")
             for w in ws if w["cls"] == "불가").most_common()),
         f"턱이 있는 벽 {sum(w['ledge'] is not None for w in ws)} — 부류: " + " · ".join(
             f"{k} {v}" for k, v in Counter(w["ledge"][1] for w in ws if w["ledge"]).most_common()),
         "쓸 점 수 분포 (전 벽): " + " · ".join(f"{k}점 {v}" for k, v in sorted(Counter(w["n_pts"] for w in ws).items())),
         "실측 T 분포 (점 3개 이상 · 기울기 > 0): " + q([w["fit"]["T"] for w in ws if w["fit"] is not None and w["fit"]["a"] > 0]).replace("10배 넘게 어긋남", "T > 10"),
         "", "칩별 (가능 · 부분 · 불가):"]
    ok = [w for w in ws if w["cls"] == "가능"]
    hon = [w["loo"][0] for w in ws if w["loo"] is not None and w["loo_honest"] == "통과"]
    k_off = int(sum(abs(np.log10(v)) > 1 for v in hon))
    lo, hi = cp95(k_off, len(hon)) if hon else (np.nan, np.nan)
    L[L.index("== 판정 ==") + 2:L.index("== 판정 ==") + 2] = [
        f"주의: 「가능」 은 검증되지 않은 판정이다 — 가능 벽 {len(ok)} 중 쓸 점 3개가 {sum(w['n_pts'] == 3 for w in ok)} 라 "
        "바깥 점을 빼면 판정을 다시 할 수 없다(아래 LOO (가) 는 판정이 그 점을 보고 고른 값).",
        f"  정직하게 볼 수 있는 것은 쓸 점 4개 이상에서 바깥 점을 뺀 판정을 통과한 {len(hon)} 벽뿐이고, 그중 {k_off}/{len(hon)} 이 "
        f"10배 넘게 어긋났다 (95% Clopper-Pearson {lo * 100:.0f}-{hi * 100:.0f}%)"]
    L += [f"  {r['chip']} 런 {r['runs']:>3} 벽 {r['walls']:>3}: {r['가능']:>3} · {r['부분']:>3} · {r['불가']:>3}" for r in pc]
    L += ["", "== 외삽 거리 (ps, 맞춘 직선) — 중앙값 · 5-95% 범위 · 1σ 중앙값 ==",
          "  주의: 1σ 는 이항 잡음만이다 — 모형 오차(꼬리가 가우시안 하나가 아님)는 빠져 있다. "
          "한 스텝 외삽에서도 관측 / 예측이 4-20배 어긋났다 (아래 LOO (나))"]
    for c in ("가능", "부분"):
        ds = [w["dist"] for w in ws if w["cls"] == c]
        for t in TARGETS:
            v = np.array([d[t][0] for d in ds])
            s = np.array([d[t][1] for d in ds])
            if len(v):
                L.append(f"  {c} 1e-4 → {t:.0e}: 중앙 {np.median(v):.1f} · {np.percentile(v, 5):.1f}-{np.percentile(v, 95):.1f} · 1σ 중앙 {np.median(s):.1f} (n {len(v)})")
        sg = [1 / w["fit"]["a"] for w in ws if w["cls"] == c]
        if sg:
            L.append(f"  {c} σ: 중앙 {np.median(sg):.1f}ps · {np.percentile(sg, 5):.1f}-{np.percentile(sg, 95):.1f}")
    L += ["", "== LOO — 가장 바깥 쓸 점의 관측 / 예측 (안쪽 쓸 점으로 맞춤) =="]
    for lab, sel in (("(가) 가능", lambda w: w["cls"] == "가능"), ("(가) 부분", lambda w: w["cls"] == "부분"),
                     ("(가) 불가 중 쓸 점 3개 이상", lambda w: w["cls"] == "불가"),
                     ("기준 — 전 벽 (쓸 점 3개 이상)", lambda w: True),
                     ("(나) 정직한 판 — 바깥 점 뺀 판정 통과", lambda w: w["loo_honest"] == "통과"),
                     ("(나) 정직한 판 — 바깥 점 뺀 판정 탈락", lambda w: w["loo_honest"] == "탈락")):
        L.append(f"  {lab}: " + q([w["loo"][0] for w in ws if w["loo"] is not None and sel(w)]))
    L.append("  misfit() (monte_carlo_deep_n, 안쪽 오류 20개 이상 · 바깥 10개 이상) 전 벽: " + q(list(mc_d.values())))
    L.append("  misfit() 중 가능 벽: " + q([mc_d[(w["file"], w["side"])] for w in ws if w["cls"] == "가능" and (w["file"], w["side"]) in mc_d]))
    L.append("  misfit() 중 부분 벽 (misfit 은 C = 천장으로 맞춘다 — 부류 높이가 아니라서 부분 벽에는 맞지 않는 비교): "
             + q([mc_d[(w["file"], w["side"])] for w in ws if w["cls"] == "부분" and (w["file"], w["side"]) in mc_d]))
    L.append(f"  (나) 로 시험한 벽 {sum(w['loo_honest'] is not None for w in ws)} (쓸 점 4개 이상) — 판정 가능 벽 중 쓸 점 4개 이상 "
             f"{sum(w['cls'] == '가능' and w['n_pts'] >= 4 for w in ws)}, 부분 벽 중 {sum(w['cls'] == '부분' and w['n_pts'] >= 4 for w in ws)}")

    # 그림
    for chip in sorted(by_chip):
        plot_chip(plt, chip, by_chip[chip], [w for w in ws if w["chip"] == chip], OUT / f"p1_class_{chip}.png")
    L += ["", "== 예시 그림 — 가능 · 부분: 쓸 점이 가장 많은 벽(같으면 T 가 작은 쪽). "
          "불가: 가장 흔한 사유(턱 없음 · 잔차)에서 가장 흔한 점 수 중 T 가 중앙값에 가장 가까운 벽 =="]
    for c in CLS:
        cand = [w for w in ws if w["cls"] == c and w["fit"] is not None and w["fit"]["a"] > 0]
        if c == "불가":
            cand = [w for w in cand if not w["ledge"]]
            n0 = Counter(w["n_pts"] for w in cand).most_common(1)[0][0]
            cand = [w for w in cand if w["n_pts"] == n0]
            tm = np.median([w["fit"]["T"] for w in cand])
            w = min(cand, key=lambda w: abs(w["fit"]["T"] - tm))
        else:
            w = max(cand, key=lambda w: (w["n_pts"], -w["fit"]["T"]))
        plot_example(plt, w, OUT / f"example_{TAG[c]}.png")
        L.append(f"  {c}: {w['chip']} {w['utc']} {w['side']} — {w['reason']} → example_{TAG[c]}.png")

    (OUT / "summary.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"출력: {OUT.relative_to(REPO)}/ — walls.csv ({len(rows)}행) · per_chip.csv · summary.txt · p1_class_<chip>.png {len(by_chip)} · example_*.png")


if __name__ == "__main__":
    main()
