#!/usr/bin/env python3
"""실측 욕조 곡선 분석 + theta 확정 체크리스트 (G0 준비물).

입력: 스윕 CSV 1개 -> 출력: 폭 3종(1e-2/1e-3/1e-4) + 체크리스트 판정 + 그림.

입력 CSV 스키마 = docs/interface/contract.md §6 (2026-07-07 확정). 소비 컬럼:
  phase_ps, n_reads, b_bits, bit_errors (+선택: reads_with_error, bit_err_sq_sum).
  나머지 계약 컬럼(phase_step, f_sclk_hz, dphi_ps, target, generated_at, git_rev)은
  있으면 검증에 활용(phase_step 연속성 = 결측 금지 규약, phase_ps=step×dphi_ps
  재계산 대조 = UART 행 오염 검출), 없어도 동작한다.
동반 파일 <stem>_reads.csv (phase_step, read_idx, err_count — 읽기별 에러 수 원본,
contract 결정 3-4 (A)) 가 옆에 있으면 자동 인식한다:
  - R8 무결성 검사: sum(e_i)==bit_errors, count(e_i>0)==reads_with_error,
    모든 e_i <= b_bits. 불일치 = 무효 런 -> 즉시 중단
  - bit_err_sq_sum 컬럼이 없으면 원본에서 파생해 체크 4 를 돌린다

위상축은 원형이다 — 스윕은 UI(=SCLK 한 주기)를 모듈로로 돌고 위상 원점은 MMCM
정렬에 따라 임의라서, 윈도우가 배열 경계에 걸친 데이터(양끝 깨끗, 가운데 에러 산)
가 나올 수 있다. 분석 전에 저 BER 최장 원형 연속 구간을 배열 중앙으로 회전한다.

theta 확정 체크리스트 (monte_carlo_sweep_params.py docstring 의 사전 선언과 동기):
 1. 가우시안 꼬리 판정 — probit 직선화: erfcinv(2*BER) 이 위상에 대해 선형이면
    가우시안. (주의: log-BER 은 가우시안 꼬리에서 2차 곡선이므로 log 선형성이
    아니라 probit 선형성이 올바른 검사다. R^2 >= R2_MIN 이면 PASS)
 2. BER floor — 윈도우 중앙 구간의 잔류 에러율 < FLOOR_MAX 이면 PASS
    (병행 기록 최저 theta=1e-4 가 오염되지 않을 조건)
 3. sigma_j 추출 — probit 기울기의 역수. PASS/FAIL 이 아니라 측정값이며,
    이 값으로 monte_carlo_sweep_params.py 를 재실행해 N=100 을 재확인한다.
 4. 버스트성 — 경계 구간에서 읽기 단위 에러 수의 과분산 F = 실측분산/이항분산.
    F <= F_MAX 이면 비트 독립 가정 유효.
 5. 인접 스텝 BER 연속성 — 한 스텝(약 16ps) 사이 BER 이 <1e-3 에서 >0.25 로
    점프하려면 sigma_j < ~7ps 가 필요해 MMCM 자체 지터만으로도 물리적으로
    불가능하다. 이런 절벽은 캡처 비트 정렬(프레이밍) 슬립의 서명 — FAIL 이면
    곡선이 아니라 RTL 을 의심할 것.

판정 문턱값(R2_MIN, FLOOR_MAX, F_MAX)은 잠정 — G0 전 팀 확정 후 이 주석 갱신.

--selftest: 정답을 아는 가우시안 합성 스윕을 계약 스키마 그대로(메인 CSV +
동반 _reads.csv, 메타데이터 컬럼 포함) 생성해 이 스크립트 자신을 검증한다.
일반 케이스와 윈도우가 배열 경계에 걸친(wrap) 케이스 둘 다 돌린다.
"""

import argparse
import csv
import math
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

from monte_carlo_sweep_params import (BASELINE, GRID, INK, INK2, MUTED, RAMP, SURFACE,
                                      edge_estimate, _style_axes)

REPO = Path(__file__).resolve().parents[2]

THETAS = [1e-2, 1e-3, 1e-4]   # 병행 기록 3종 (채택: 1e-2, 잠정)
FIT_BAND = (1e-4, 5e-2)       # probit 적합에 쓰는 BER 구간
R2_MIN = 0.98                 # 체크 1 문턱 (2026-07-07 확정)
FLOOR_MAX = 1e-5              # 체크 2 문턱 (2026-07-07 확정)
F_MAX = 2.0                   # 체크 4 문턱 (2026-07-07 확정)
JUMP_LO, JUMP_HI = 1e-3, 0.25  # 체크 5: 한 스텝에 lo -> hi 점프 = 프레이밍 서명


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
    if "_invalid" in path.stem:
        raise SystemExit(f"{path.name}: 무효 런 파일은 분석 입력이 될 수 없다 (contract §6)")
    with open(path) as f:
        rows = list(csv.DictReader(f))
    phis = np.array([float(r["phase_ps"]) for r in rows])
    n = int(rows[0]["n_reads"])
    b = int(rows[0]["b_bits"])
    errs = np.array([int(r["bit_errors"]) for r in rows])
    if "phase_step" in rows[0] and rows[0]["phase_step"] != "":
        steps = np.array([int(r["phase_step"]) for r in rows])
        if not np.array_equal(steps, np.arange(steps[0], steps[0] + len(steps))):
            raise SystemExit(f"{path.name}: phase_step 결측/비연속 — 무효 런 (contract §6)")
        if "dphi_ps" in rows[0] and rows[0]["dphi_ps"] != "":
            dphi = float(rows[0]["dphi_ps"])
            if np.any(np.abs(phis - steps * dphi) > dphi / 2):
                raise SystemExit(f"{path.name}: phase_ps ≠ phase_step×dphi_ps (>Δφ/2)"
                                 " — UART 행 오염 의심, 무효 런")
    rwe = None
    if "reads_with_error" in rows[0] and rows[0]["reads_with_error"] != "":
        rwe = np.array([int(r["reads_with_error"]) for r in rows])
    sq = None
    if "bit_err_sq_sum" in rows[0] and rows[0]["bit_err_sq_sum"] != "":
        sq = np.array([int(r["bit_err_sq_sum"]) for r in rows])
    return phis, n, b, errs, rwe, sq


def load_reads_companion(path, n_steps, n, b, errs, rwe):
    """동반 <stem>_reads.csv 로드 + R8 무결성 검사. 없으면 None."""
    rp = path.with_name(path.stem + "_reads.csv")
    if not rp.exists():
        return None
    with open(rp) as f:
        rows = list(csv.DictReader(f))
    e = np.zeros((n_steps, n), dtype=np.int64)
    for r in rows:
        e[int(r["phase_step"]), int(r["read_idx"])] = int(r["err_count"])
    bad = []
    if not np.array_equal(e.sum(axis=1), errs):
        bad.append("sum(e_i) != bit_errors")
    if rwe is not None and not np.array_equal((e > 0).sum(axis=1), rwe):
        bad.append("count(e_i>0) != reads_with_error")
    if (e > b).any():
        bad.append("e_i > b_bits")
    if bad:
        raise SystemExit(f"{rp.name}: R8 무결성 불일치 [{', '.join(bad)}] — 무효 런 (contract R8)")
    print(f"[R8] 동반 원본({rp.name}) 무결성 검사 통과")
    return e


def circular_recenter(ber, arrays):
    """저 BER 최장 원형 연속 구간의 중앙이 배열 중앙에 오도록 전 배열을 회전.

    위상 원점은 어차피 임의(MMCM 정렬)이므로 회전은 재레이블일 뿐이다.
    반환: (roll_offset, 회전된 배열 리스트)
    """
    low = ber < 1e-3
    if not low.any() or low.all():
        return 0, arrays
    m = np.concatenate([low, low])  # 원형 run 을 선형 탐색으로
    best_len, best_start, cur = 0, 0, None
    for i, v in enumerate(m):
        if v and cur is None:
            cur = i
        elif not v and cur is not None:
            if i - cur > best_len and cur < len(low):
                best_len, best_start = i - cur, cur
            cur = None
    if cur is not None and len(m) - cur > best_len and cur < len(low):
        best_len, best_start = len(m) - cur, cur
    best_len = min(best_len, len(low))
    center = (best_start + best_len // 2) % len(low)
    r = len(low) // 2 - center
    return r, [np.roll(a, r) for a in arrays]


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
        out["_edges_adopted"] = (l2, r2_)
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
        out["check4_burst"] = "SKIP(제곱합 없음 — bit_err_sq_sum 컬럼 또는 _reads.csv 필요)"

    # 체크 5: 인접 스텝 BER 연속성 — 프레이밍(비트 정렬) 슬립 검출
    jumps = [i for i in range(len(ber) - 1)
             if (ber[i] < JUMP_LO and ber[i + 1] > JUMP_HI)
             or (ber[i + 1] < JUMP_LO and ber[i] > JUMP_HI)]
    out["check5_continuity"] = (
        "PASS" if not jumps
        else f"FAIL({len(jumps)}건, 첫 점프 index {jumps[0]})")

    return out, ber, center, fits


def make_plot(phis, ber, nb, fits, out_png, title, edges=None):
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
    if edges and not any(math.isnan(v) for v in edges):
        l, r = edges
        ax.annotate("", xy=(l, 1e-2), xytext=(r, 1e-2),
                    arrowprops=dict(arrowstyle="<->", color=INK, lw=1.2))
        ax.annotate(f"width@θ=1e-2: {r - l:.0f} ps", xy=((l + r) / 2, 1e-2),
                    xytext=(0, 6), textcoords="offset points",
                    ha="center", color=INK, fontsize=9)
    ax.set_ylim(0.3 / nb, 1.0)
    ax.set_xlabel("phase (ps, origin arbitrary)", color=INK2)
    ax.set_ylabel("BER", color=INK2)
    ax.set_title(title, color=INK, fontsize=10, loc="left")
    leg = ax.legend(fontsize=8.5, frameon=False, loc="upper center")
    for t in leg.get_texts():
        t.set_color(INK2)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    return out_png


def _git_rev():
    try:
        rev = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
        if subprocess.run(["git", "diff", "--quiet"], cwd=REPO).returncode != 0:
            rev += "-dirty"
        return rev
    except Exception:
        return "unknown"


def selftest_csv(path, seed=7, wrap=False):
    """정답을 아는 가우시안 합성 스윕을 계약 스키마(contract §6) 그대로 생성.

    메인 CSV(12컬럼, 메타데이터 행 반복) + 동반 _reads.csv(읽기별 에러 수 원본).
    bit_err_sq_sum 은 계약대로 원본 e_i 에서 파생해 채운다 (호스트 경로 리허설).
    wrap=True 면 곡선을 반 바퀴 돌려 윈도우가 배열 경계에 걸치게 한다.
    """
    rng = np.random.default_rng(seed + (1 if wrap else 0))
    sigma_true, edge_l, edge_r = 80.0, 2000.0, 6000.0
    n, b, dphi, f_sclk = 100, 2048, 15.87, 25_000_000
    phis = np.arange(0.0, 8000.0 + dphi, dphi)
    s = math.sqrt(2.0) * sigma_true
    p = np.clip(
        0.5 * np.array([math.erfc(x) for x in (phis - edge_l) / s])
        + 0.5 * np.array([math.erfc(x) for x in (edge_r - phis) / s]), 0.0, 0.5)
    if wrap:
        p = np.roll(p, len(p) // 2)
    stamp, rev = datetime.now().isoformat(timespec="seconds"), _git_rev()
    target = "selftest_wrap" if wrap else "selftest"
    path.parent.mkdir(parents=True, exist_ok=True)
    reads_path = path.with_name(path.stem + "_reads.csv")
    with open(path, "w", newline="") as f, open(reads_path, "w", newline="") as fr:
        w, wr = csv.writer(f), csv.writer(fr)
        w.writerow(["phase_step", "phase_ps", "n_reads", "b_bits", "bit_errors",
                    "reads_with_error", "bit_err_sq_sum",
                    "f_sclk_hz", "dphi_ps", "target", "generated_at", "git_rev"])
        wr.writerow(["phase_step", "read_idx", "err_count"])
        for i, (phi, pp) in enumerate(zip(phis, p)):
            per_read = rng.binomial(b, pp, size=n)
            w.writerow([i, round(phi, 2), n, b, int(per_read.sum()),
                        int((per_read > 0).sum()), int((per_read**2).sum()),
                        f_sclk, dphi, target, stamp, rev])
            for j, e in enumerate(per_read):
                if e:  # 0 은 생략해도 행렬 복원에 무해 (기본값 0) — 파일 크기 절약
                    wr.writerow([i, j, int(e)])
    return sigma_true, edge_r - edge_l


def run(path):
    phis, n, b, errs, rwe, sq = load_sweep(path)
    e = load_reads_companion(path, len(phis), n, b, errs, rwe)
    if sq is None and e is not None:
        sq = (e ** 2).sum(axis=1)

    ber0 = errs / (n * b)
    roll, rolled = circular_recenter(ber0, [errs] + ([sq] if sq is not None else []))
    if roll:
        print(f"[recenter] 윈도우가 스윕 경계에 걸림 -> {roll:+d} 스텝 원형 회전 (위상 원점은 임의)")
        errs = rolled[0]
        if sq is not None:
            sq = rolled[1]

    out, ber, center, fits = analyze(phis, n, b, errs, sq)

    png = make_plot(phis, ber, n * b, fits,
                    REPO / "build" / "plots" / f"bathtub_{path.stem}.png",
                    f"Bathtub analysis: {path.name}  (N={n}, B={b})",
                    edges=out.get("_edges_adopted"))

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
    print(f"  5. BER 연속성         : {out['check5_continuity']}"
          f"  [한 스텝 {JUMP_LO:g}->{JUMP_HI:g} 점프 = 프레이밍 슬립 서명]")
    print(f"\nplot: {png.relative_to(REPO)}")
    return out


def main():
    ap = argparse.ArgumentParser(description="실측 욕조 곡선 분석 + theta 확정 체크리스트")
    ap.add_argument("csv_path", nargs="?", help="스윕 CSV 경로 (contract §6 스키마)")
    ap.add_argument("--selftest", action="store_true",
                    help="합성 데이터로 자기 검증 — 일반 + wrap 두 케이스 (csv_path 불필요)")
    args = ap.parse_args()

    if args.selftest:
        for wrap in (False, True):
            tag = "selftest_sweep_wrap" if wrap else "selftest_sweep"
            path = REPO / "build" / "data" / f"{tag}.csv"
            sigma_true, width_geo = selftest_csv(path, wrap=wrap)
            print(f"\n{'=' * 62}\n[selftest{'/wrap' if wrap else ''}] 합성 곡선:"
                  f" sigma_j={sigma_true}ps, 기하 폭={width_geo}ps"
                  f" -> {path.relative_to(REPO)}")
            run(path)
    elif args.csv_path:
        run(Path(args.csv_path))
    else:
        ap.error("csv_path 또는 --selftest 필요")


if __name__ == "__main__":
    main()
