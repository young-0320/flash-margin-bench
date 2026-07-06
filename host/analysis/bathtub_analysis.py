#!/usr/bin/env python3
"""실측 욕조 곡선 분석 + theta 확정 체크리스트 (G0 준비물).

입력: 스윕 CSV 1개 -> 출력: 폭 3종(1e-2/1e-3/1e-4) + 체크리스트 판정 + 그림.

!! 입력 CSV 스키마는 잠정이다 — docs/interface/ 계약 확정 시 반드시 동기화할 것.
!!   phase_ps      : 위상 (ps)
!!   n_reads       : 위상당 읽기 횟수 N
!!   b_bits        : 읽기 1회 비트 수 B
!!   bit_errors    : N회 읽기의 에러 비트 총합
!!   reads_with_error : (선택) 에러가 1개 이상 있었던 읽기 수
!!   bit_err_sq_sum   : (선택) 읽기별 에러 수 제곱의 합 — 버스트성(체크 4) 판정에
!!                      필수. 없으면 체크 4는 SKIP 되고 경고가 출력된다.
!!                      => FPGA error logger 가 이 값을 누적하도록 인터페이스에
!!                         반영해야 함 (합계 외에 제곱합 누적기 1개 추가)

theta 확정 체크리스트 (mc_reads_per_phase.py docstring 의 사전 선언과 동기):
 1. 가우시안 꼬리 판정 — probit 직선화: erfcinv(2*BER) 이 위상에 대해 선형이면
    가우시안. (주의: log-BER 은 가우시안 꼬리에서 2차 곡선이므로 log 선형성이
    아니라 probit 선형성이 올바른 검사다. R^2 >= R2_MIN 이면 PASS)
 2. BER floor — 윈도우 중앙 구간의 잔류 에러율 < FLOOR_MAX 이면 PASS
    (병행 기록 최저 theta=1e-4 가 오염되지 않을 조건)
 3. sigma_j 추출 — probit 기울기의 역수. PASS/FAIL 이 아니라 측정값이며,
    이 값으로 mc_reads_per_phase.py 를 재실행해 N=100 을 재확인한다.
 4. 버스트성 — 경계 구간에서 읽기 단위 에러 수의 과분산 F = 실측분산/이항분산.
    F <= F_MAX 이면 비트 독립 가정 유효.

판정 문턱값(R2_MIN, FLOOR_MAX, F_MAX)은 잠정 — G0 전 팀 확정 후 이 주석 갱신.

--selftest: 정답을 아는 가우시안 합성 CSV 를 생성해 이 스크립트 자신을 검증한다
(sigma_j 복원, 폭 복원, F~1 확인). G0 전에 도구를 시운전하는 용도.
"""

import argparse
import csv
import math
from pathlib import Path

import numpy as np

from mc_reads_per_phase import (BASELINE, GRID, INK, INK2, MUTED, RAMP, SURFACE,
                                edge_estimate, _style_axes)

REPO = Path(__file__).resolve().parents[2]

THETAS = [1e-2, 1e-3, 1e-4]   # 병행 기록 3종 (채택: 1e-2, 잠정)
FIT_BAND = (1e-4, 5e-2)       # probit 적합에 쓰는 BER 구간
R2_MIN = 0.98                 # 체크 1 잠정 문턱
FLOOR_MAX = 1e-5              # 체크 2 잠정 문턱
F_MAX = 2.0                   # 체크 4 잠정 문턱


def erfcinv(y):
    """erfc 의 역함수 (0 < y <= 1 구간, 이분법). scipy 의존 회피용."""
    lo, hi = 0.0, 10.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        if math.erfc(mid) > y:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def load_sweep(path):
    with open(path) as f:
        rows = list(csv.DictReader(f))
    phis = np.array([float(r["phase_ps"]) for r in rows])
    n = int(rows[0]["n_reads"])
    b = int(rows[0]["b_bits"])
    errs = np.array([int(r["bit_errors"]) for r in rows])
    sq = None
    if "bit_err_sq_sum" in rows[0] and rows[0]["bit_err_sq_sum"] != "":
        sq = np.array([int(r["bit_err_sq_sum"]) for r in rows])
    return phis, n, b, errs, sq


def find_center(ber):
    """욕조 바닥(최소 BER 연속 구간)의 중앙 인덱스."""
    idx = np.where(ber == ber.min())[0]
    return int(idx[len(idx) // 2])


def probit_fit(phis, ber, center, side):
    """한쪽 경계의 probit(erfcinv) 선형 적합.

    반환: (sigma_j_ps, edge_pos_ps, r2, n_points) — 적합 불능이면 None.
    """
    if side == "left":
        sel = np.arange(0, center)
    else:
        sel = np.arange(center, len(phis))
    band = sel[(ber[sel] >= FIT_BAND[0]) & (ber[sel] <= FIT_BAND[1])]
    if len(band) < 4:
        return None
    x = phis[band]
    y = np.array([erfcinv(2.0 * p) for p in ber[band]])
    slope, icpt = np.polyfit(x, y, 1)
    pred = slope * x + icpt
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    sigma = 1.0 / (math.sqrt(2.0) * abs(slope))
    edge_pos = -icpt / slope  # y=0 (BER=0.5) 지점 = 경계 중심
    return sigma, edge_pos, r2, len(band)


def analyze(phis, n, b, errs, sq):
    nb = n * b
    ber = errs / nb
    center = find_center(ber)
    floor_sub = 0.5 / nb
    out = {"n_reads": n, "b_bits": b, "n_steps": len(phis)}

    # 폭 3종 (경계 판정 = MC 와 동일한 log 보간 알고리즘)
    for th in THETAS:
        left = edge_estimate(ber[:, None], phis, center, th, floor_sub, "left")[0]
        right = edge_estimate(ber[:, None], phis, center, th, floor_sub, "right")[0]
        out[f"width_ps@{th:g}"] = round(right - left, 2) \
            if not (math.isnan(left) or math.isnan(right)) else float("nan")

    # 체크 1+3: probit 직선화 -> 가우시안 판정 + sigma_j
    fits = {}
    for side in ("left", "right"):
        f = probit_fit(phis, ber, center, side)
        fits[side] = f
        if f:
            out[f"sigma_j_ps_{side}"] = round(f[0], 1)
            out[f"probit_r2_{side}"] = round(f[2], 4)
    ok = all(fits.values())
    out["check1_gaussian"] = (
        "PASS" if ok and min(f[2] for f in fits.values()) >= R2_MIN
        else "FAIL" if ok else "SKIP(적합점 부족)")

    # 체크 2: floor — theta=1e-2 교차점 사이 안쪽 60% 구간
    l2 = edge_estimate(ber[:, None], phis, center, 1e-2, floor_sub, "left")[0]
    r2_ = edge_estimate(ber[:, None], phis, center, 1e-2, floor_sub, "right")[0]
    if not (math.isnan(l2) or math.isnan(r2_)):
        m = 0.2 * (r2_ - l2)
        mid = (phis >= l2 + m) & (phis <= r2_ - m)
        tot_bits = int(mid.sum()) * nb
        tot_errs = int(errs[mid].sum())
        floor = tot_errs / tot_bits
        out["floor_ber"] = float(f"{floor:.3g}")
        out["floor_bound"] = float(f"{1.0 / tot_bits:.3g}")  # 에러 0일 때 상한
        out["check2_floor"] = "PASS" if max(floor, 1.0 / tot_bits) < FLOOR_MAX else "FAIL"
    else:
        out["check2_floor"] = "SKIP(윈도우 미검출)"

    # 체크 4: 버스트성 — 경계 구간 과분산 (읽기 단위 분산 / 이항 분산)
    if sq is not None:
        edge_band = (ber > 1e-3) & (ber < 0.25)
        factors = []
        for i in np.where(edge_band)[0]:
            mean = errs[i] / n
            var = (sq[i] - n * mean**2) / (n - 1)
            p = ber[i]
            binom = b * p * (1 - p)
            if binom > 0:
                factors.append(var / binom)
        if factors:
            F = float(np.median(factors))
            out["overdispersion_F"] = round(F, 2)
            out["check4_burst"] = "PASS" if F <= F_MAX else "FAIL"
        else:
            out["check4_burst"] = "SKIP(경계 구간 없음)"
    else:
        out["check4_burst"] = "SKIP(bit_err_sq_sum 컬럼 없음 — 인터페이스에 제곱합 필요)"

    return out, ber, center, fits


def make_plot(phis, ber, nb, fits, out_png, title):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    _style_axes(fig, ax)

    nz = ber > 0
    ax.semilogy(phis[nz], ber[nz], "o", ms=3.5, color=RAMP[1], label="measured")
    for th, ls in zip(THETAS, [(0, (4, 3)), (0, (2, 2)), (0, (1, 2))]):
        ax.axhline(th, color=MUTED, lw=1.0, ls=ls)
        ax.annotate(f"θ={th:g}", xy=(phis[0], th), xytext=(2, 3),
                    textcoords="offset points", color=INK2, fontsize=8)
    for side, f in fits.items():
        if not f:
            continue
        sigma, edge_pos, r2, _ = f
        sgn = 1.0 if side == "left" else -1.0  # 비탈은 경계 중심에서 윈도우 안쪽으로 내려감
        d = np.linspace(0.8 * sigma, 4.2 * sigma, 60)
        x = edge_pos + sgn * d
        y = np.array([0.5 * math.erfc(v / (math.sqrt(2) * sigma)) for v in d])
        ax.semilogy(x, y, "--", lw=1.6, color=RAMP[3],
                    label=f"{side} fit: σⱼ={sigma:.0f} ps, R²={r2:.3f}")
    ax.set_ylim(0.3 / nb, 1.0)
    ax.set_xlabel("phase (ps)", color=INK2)
    ax.set_ylabel("BER", color=INK2)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    leg = ax.legend(fontsize=8.5, frameon=False, loc="upper center")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    return out_png


def selftest_csv(path, seed=7):
    """정답을 아는 가우시안 합성 스윕 CSV 생성 (읽기 단위까지 시뮬레이션)."""
    rng = np.random.default_rng(seed)
    sigma_true, edge_l, edge_r = 80.0, 2000.0, 6000.0
    n, b, dphi = 100, 2048, 15.0
    phis = np.arange(0.0, 8000.0 + dphi, dphi)
    s = math.sqrt(2.0) * sigma_true
    p = np.clip(
        0.5 * np.array([math.erfc(x) for x in (phis - edge_l) / s])
        + 0.5 * np.array([math.erfc(x) for x in (edge_r - phis) / s]), 0.0, 0.5)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["phase_ps", "n_reads", "b_bits", "bit_errors",
                    "reads_with_error", "bit_err_sq_sum"])
        for phi, pp in zip(phis, p):
            per_read = rng.binomial(b, pp, size=n)
            w.writerow([phi, n, b, int(per_read.sum()),
                        int((per_read > 0).sum()), int((per_read**2).sum())])
    return sigma_true, edge_r - edge_l


def main():
    ap = argparse.ArgumentParser(description="실측 욕조 곡선 분석 + theta 확정 체크리스트")
    ap.add_argument("csv_path", nargs="?", help="스윕 CSV 경로")
    ap.add_argument("--selftest", action="store_true",
                    help="합성 데이터로 자기 검증 (csv_path 불필요)")
    args = ap.parse_args()

    if args.selftest:
        path = REPO / "build" / "data" / "selftest_sweep.csv"
        sigma_true, width_geo = selftest_csv(path)
        print(f"[selftest] 합성 곡선: sigma_j={sigma_true}ps, 기하 폭={width_geo}ps -> {path.relative_to(REPO)}")
    elif args.csv_path:
        path = Path(args.csv_path)
    else:
        ap.error("csv_path 또는 --selftest 필요")

    phis, n, b, errs, sq = load_sweep(path)
    out, ber, center, fits = analyze(phis, n, b, errs, sq)

    png = make_plot(phis, ber, n * b, fits,
                    REPO / "build" / "plots" / f"bathtub_{path.stem}.png",
                    f"Bathtub analysis: {path.name}  (N={n}, B={b})")

    print(f"\n== 폭 3종 (병행 기록) ==")
    for th in THETAS:
        print(f"  width @ BER={th:<6g}: {out[f'width_ps@{th:g}']} ps")
    print(f"\n== theta 확정 체크리스트 ==")
    print(f"  1. 가우시안(probit R²): {out['check1_gaussian']}"
          f"  [{out.get('probit_r2_left', '-')} / {out.get('probit_r2_right', '-')}, 기준 {R2_MIN}]")
    print(f"  2. BER floor          : {out['check2_floor']}"
          f"  [실측 {out.get('floor_ber', '-')} (상한 {out.get('floor_bound', '-')}), 기준 < {FLOOR_MAX:g}]")
    print(f"  3. sigma_j 추출       : left {out.get('sigma_j_ps_left', '-')} ps /"
          f" right {out.get('sigma_j_ps_right', '-')} ps -> MC 재실행 입력")
    print(f"  4. 버스트성(과분산 F) : {out['check4_burst']}"
          f"  [F={out.get('overdispersion_F', '-')}, 기준 <= {F_MAX}]")
    print(f"\nplot: {png.relative_to(REPO)}")


if __name__ == "__main__":
    main()
