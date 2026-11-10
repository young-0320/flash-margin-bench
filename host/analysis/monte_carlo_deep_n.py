#!/usr/bin/env python3
"""초심부(deep) 모드의 스텝당 읽기 수 N 을 정하는 몬테카를로 (욕조 v2, 로그 55).

사용: uv run python host/analysis/monte_carlo_deep_n.py [--reps 1000] [--walls 0] [--out build/mc_deep_n]   (로그 55 §6 의 표는 기본값 그대로의 산출)

질문: 표준 모드(N_STD = 8,064 = 112 × 72)로 보이는 벽 바깥 「한 스텝」 에서, 꼬리가 가우시안인지
아닌지를 가를 수 있으려면 N 이 몇이어야 하나.

진실(벽 모양)은 v1 실측에서 가져온다 — data/ 의 25MHz 스윕마다 좌우 벽을 probit 직선으로 맞춰
(μ, σ) 를 얻는다: BER(x) = C · Φ((x - μ) / σ), C = 그 런의 천장 BER, x 는 벽 바깥 → 안쪽 방향(오른쪽 벽은 뒤집음).

한 벽 · 한 N 의 시험 (reps 회 반복):
  1. 시험 스텝 t = 진실 BER 이 표준 모드의 한계(1 / N_STD 비트) 아래로 처음 내려가는 바깥 스텝.
     표준 모드로는 오류가 거의 안 보이는 자리다.
  2. 초심부 측정을 모의한다 — 스텝마다 오류 수 ~ Binomial(N · 2048, 진실 BER).
  3. 그 측정 안에서 t 안쪽의 잘 보이는 스텝(오류 20개 이상 · 천장의 95% 미만)으로 다시 (μ, σ) 를 맞추고
     t 의 오류 수를 예측한다 — 실제 분석이 할 일 그대로.
  4. 통계량 r = log((관측 + 0.5) / (예측 + 0.5)).
  H0 = 꼬리가 가우시안(진실 그대로). H1 = t 에서 BER 이 가우시안보다 10배(한 자릿수) 높다.
  H0 의 r 상위 5% 를 문턱으로 잡고(오경보 5%, 맞춤 오차까지 포함), H1 에서 문턱을 넘는 비율이 검정력이다.

판정 기준 (돌리기 전에 정함, 2026-11-10):
  N 후보는 112 의 배수. **벽의 80% 이상에서 검정력 0.8 이상** 인 가장 작은 N 을 초심부 N 으로 한다.
  맞춤에 쓸 점이 2개 미만인 벽은 시험 불가로 따로 센다.

--model empirical (2026-11-10 추가, 로그 55 [U55-4] — 리뷰 R5): 단일 가우시안은 v1 자료에서 안 맞는다.
  그래서 H0 의 시험 스텝 BER 을 「가우시안 예측 × 실측 어긋남」 으로 둔다. 어긋남 분포는 v1 벽마다
  안쪽 점(오류 20개 이상)으로 맞추고 바깥 점(오류 10개 이상, 맞춤에 안 쓴 가장 바깥 점)을 예측해
  관측 ÷ 예측의 로그를 모은 것이다 — 이력 부류(ISI) 턱 · 가파른 꼬리가 다 들어 있다. H1 = 그 위에 10배.
  가정: v1 깊이(1e-4 - 1e-6)의 어긋남이 1e-9 대에서도 같은 분포다. 판정 기준은 위와 같다.

시간은 추정만 낸다 — 읽기 한 번 90 µs(플래시 2,048비트 @25MHz + 명령) 하한 · 283 µs(v1 실측 80 s / 282,240회,
UART 읽기별 기록 포함) 상한 × 시험 스텝 수.
"""

import argparse
import csv
import glob
import math
from pathlib import Path
from statistics import NormalDist

import numpy as np

REPO = Path(__file__).resolve().parents[2]
BITS = 2048
N_STD = 112 * 72
DPHI = 1e6 / 63 / 1000                                      # 15.873 ps
F_H1 = 10.0                                                 # H1: 시험 스텝 BER 이 가우시안의 10배
ALPHA, POWER, SHARE = 0.05, 0.8, 0.8
MIN_CNT, CEIL_FRAC = 20, 0.95
CANDS = [112 * m for m in (72, 144, 288, 576, 1152, 2304, 4608, 9216, 18432)]
ND = NormalDist()


def walls(path):
    """한 런의 좌우 벽 → [(x 스텝 배열(바깥 → 안), BER 배열, 천장 BER, 스텝당 비트)]. 벽은 덩어리 밖 6스텝까지 포함."""
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    if len({r["n_reads"] for r in rows}) != 1:                # v2 파일(훑기 · 벽 집중 섞임)은 뺀다
        return []
    if len(rows) != 2520 or float(rows[0]["f_sclk_hz"]) != 25e6:
        return []
    e = np.array([int(r["bit_errors"]) for r in rows], float)
    n = int(rows[0]["n_reads"]) * int(rows[0]["b_bits"])
    nz = np.nonzero(e)[0]
    if len(nz) == 0 or nz.max() - nz.min() > 300:           # 원형 경계에 걸친 런은 없다(전수 확인) — 있으면 뺀다
        return []
    ber = e / n
    ceil = ber.max()
    a, b = nz.min(), nz.max()
    top = np.nonzero(ber >= 0.99 * ceil)[0]
    out = []
    left = np.arange(a - 6, top.min() + 1)                  # 바깥 → 안
    right = np.arange(b + 6, top.max() - 1, -1)
    for idx in (left, right):
        idx = idx[(idx >= 0) & (idx < 2520)]
        out.append((np.arange(len(idx), dtype=float), ber[idx], ceil, n))
    return out


def fit(x, ber, ceil, cnt):
    """probit 직선 — Φ⁻¹(BER/C) = (x - μ)/σ. 쓸 점: 오류 MIN_CNT 이상 · 천장의 CEIL_FRAC 미만."""
    m = (cnt >= MIN_CNT) & (ber < CEIL_FRAC * ceil)
    if m.sum() < 2:
        return None
    z = np.array([ND.inv_cdf(min(max(v / ceil, 1e-15), 1 - 1e-12)) for v in ber[m]])
    k, c = np.polyfit(x[m], z, 1)
    if k <= 0:
        return None
    return -c / k, 1 / k                                    # μ, σ (스텝 단위)


def truth(x, ber, ceil):
    """v1 실측 벽에서 진실 (μ, σ). v1 은 오류 수가 작아 문턱을 낮춰 맞춘다(오류 1개 이상)."""
    cnt = np.where(ber > 0, MIN_CNT, 0)
    return fit(x, ber, ceil, cnt)


def misfit(ws_raw):
    """실측 어긋남 분포 — 벽마다 안쪽 점으로 맞추고 맞춤에 안 쓴 가장 바깥 점(오류 10개 이상)을 예측, log(관측/예측)."""
    d = []
    for x, ber, ceil, n in ws_raw:
        cnt = np.rint(ber * n)
        far = np.nonzero((cnt >= 10) & (ber < CEIL_FRAC * ceil))[0]
        if len(far) == 0:
            continue
        o = far.min()                                       # 가장 바깥 점 (배열은 바깥 → 안)
        inner = np.arange(len(ber)) > o
        f = fit(x[inner], ber[inner], ceil, np.where(inner, cnt, 0)[inner])
        if f is None:
            continue
        pred = ceil * ND.cdf((x[o] - f[0]) / f[1])
        if pred > 0:
            d.append(math.log(ber[o] / pred))
    return np.array(d)


def trial(mu, sig, ceil, nbits, reps, rng, dsamp=None):
    """H0 · H1 의 r 표본. 시험 스텝 t 를 진실에서 정하고, 측정 · 맞춤 · 예측을 reps 번.
    dsamp 가 있으면 H0 의 시험 스텝 BER 에 실측 어긋남 exp(d) 를 곱한다 (--model empirical)."""
    x = np.arange(-30, 1, dtype=float) + math.floor(mu)     # 벽 바깥 30스텝 · μ 근처까지
    p = ceil * np.array([ND.cdf((v - mu) / sig) for v in x])
    lim = 1 / (N_STD * BITS)
    out = np.nonzero(p < lim)[0]
    if len(out) == 0:
        return None
    t = out.max()                                           # 표준 한계 아래로 처음 내려가는 바깥 스텝
    inner = slice(t + 1, None)
    res = {}
    for h, mult in (("h0", 1.0), ("h1", F_H1)):
        pt = np.tile(p, (reps, 1))
        dev = np.exp(rng.choice(dsamp, reps)) if dsamp is not None else np.ones(reps)
        pt[:, t] = np.minimum(p[t] * dev * mult, ceil)
        cnt = rng.binomial(nbits, pt)
        r = np.full(reps, np.nan)
        for i in range(reps):
            f = fit(x[inner], cnt[i, inner] / nbits, ceil, cnt[i, inner])
            if f is None:
                continue
            lam = nbits * ceil * ND.cdf((x[t] - f[0]) / f[1])
            r[i] = math.log((cnt[i, t] + 0.5) / (lam + 0.5))
        res[h] = r
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--reps", type=int, default=1000)
    ap.add_argument("--walls", type=int, default=0, help="벽 표본 수 (0 = 전부) — 고정 시드로 뽑는다")
    ap.add_argument("--model", choices=("gauss", "empirical"), default="empirical", help="H0 진실 모델 (empirical = 실측 어긋남, 로그 55 [U55-4])")
    ap.add_argument("--out", default=str(REPO / "build" / "mc_deep_n"))
    a = ap.parse_args()
    rng = np.random.default_rng(20261110)
    ws, raw = [], []
    for pth in sorted(glob.glob(str(REPO / "data" / "sweep_chip*.csv"))):
        if pth.endswith(("_reads.csv", "_invalid.csv")):
            continue
        for x, ber, ceil, n in walls(pth):
            raw.append((x, ber, ceil, n))
            t = truth(x, ber, ceil)
            if t:
                ws.append((Path(pth).name, t[0], t[1], ceil))
    dsamp = misfit(raw) if a.model == "empirical" else None
    if dsamp is not None:
        q = np.exp(np.percentile(dsamp, [5, 25, 50, 75, 95]))
        print(f"실측 어긋남 (관측/가우시안 예측) {len(dsamp)}벽 — 5 · 25 · 50 · 75 · 95%: " + " · ".join(f"{v:.2g}" for v in q)
              + f" · 10배 넘게 어긋남 {(np.abs(dsamp) > math.log(10)).mean() * 100:.0f}%")
    sig = np.array([w[2] for w in ws]) * DPHI
    nall = len(ws)
    if a.walls and a.walls < nall:
        ws = [ws[i] for i in sorted(rng.choice(nall, a.walls, replace=False))]
    print(f"벽 {nall}개(표본 {len(ws)}) — σ 중앙값 {np.median(sig):.1f} ps (10-90% {np.percentile(sig, 10):.1f}-{np.percentile(sig, 90):.1f})")

    Path(a.out).mkdir(parents=True, exist_ok=True)
    rows = []
    for n in CANDS:
        nbits = n * BITS
        pw, bad = [], 0
        for _, mu, s, ceil in ws:
            res = trial(mu, s, ceil, nbits, a.reps, rng, dsamp)
            if res is None or np.isnan(res["h0"]).mean() > 0.5:
                bad += 1
                continue
            h0, h1 = res["h0"][~np.isnan(res["h0"])], res["h1"][~np.isnan(res["h1"])]
            thr = np.quantile(h0, 1 - ALPHA)
            pw.append((h1 > thr).mean())
        pw = np.array(pw)
        share = (pw >= POWER).mean() if len(pw) else 0
        hrs = (n * 30 * 90e-6 / 3600, n * 30 * 283e-6 / 3600)  # 벽 시험 스텝 약 30개(양쪽 · 천장 빼고)
        rows.append({"N": n, "N_over_112": n // 112, "floor_ber": 1 / nbits, "walls_ok": len(pw), "walls_untestable": bad,
                     "power_median": np.median(pw), "power_p20": np.percentile(pw, 20), "share_power_ge_0.8": share,
                     "hours_low": hrs[0], "hours_high": hrs[1]})
        print(f"N={n:>9,} (112×{n // 112:>5}) 바닥 {1 / nbits:.1e} · 시험 가능 {len(pw)}/{len(ws)} · 검정력 중앙 {np.median(pw):.2f}"
              f" · 하위20% {np.percentile(pw, 20):.2f} · 0.8 이상 벽 {share * 100:.0f}% · 스윕 {hrs[0]:.1f}-{hrs[1]:.1f} h")
    with open(Path(a.out) / f"deep_n_{a.model}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    ok = [r for r in rows if r["share_power_ge_0.8"] >= SHARE]
    print(f"\n판정 (벽의 {SHARE * 100:.0f}% 이상에서 검정력 {POWER}): " + (f"N = {ok[0]['N']:,} (112×{ok[0]['N_over_112']})" if ok else "후보 안에 없음"))


if __name__ == "__main__":
    main()
