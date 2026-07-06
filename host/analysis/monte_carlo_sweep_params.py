#!/usr/bin/env python3
"""위상 스윕 파라미터(N, theta) 결정 몬테카를로 (docs/workflow/1.md 병렬 저비용 항목).

가상 실험: 경계가 가우시안 지터 비탈(erfc)인 진짜 욕조 곡선을 가정하고,
"위상 스텝마다 N회 x B비트 읽기 -> 이항 분포로 에러 발생 -> 경계 판정 -> 폭 계산"을
trials회 반복해 폭 추정치의 표준편차 sigma_width 를 N의 함수로 구한다.

경계 판정 정의 (= golden model 이 독립 구현할 알고리즘):
  욕조 중앙에서 바깥으로 걸으며 측정 BER 이 문턱값 theta 를 처음 넘는 두 인접
  스텝 사이를 log10(BER) 선형 보간해 교차점을 구한다. BER=0 스텝은 반 카운트
  floor(0.5/(N*B)) 로 치환한다. 폭 = 오른쪽 교차점 - 왼쪽 교차점.

N 선택 규칙 (사전 등록, 잠정): sigma_width <= dphi/2 를 만족하는 최소 N.
근거: 하드웨어 위상 분해능(dphi)보다 통계 노이즈가 크면 낭비, 훨씬 작아도
양자화에 묻혀 이득이 없다. G0/G4 에서 실측 지터·반복 편차가 나오면 이 규칙
자체를 재조정할 수 있다 — 규칙 변경 시 이 주석과 보고서 문구를 함께 갱신할 것.

채택 theta = 1e-2 (2026-07-06 잠정, G0 루프백 실측 후 최종 확정). 잠정 근거:
노화 검출 SNR(노화 신호/측정 노이즈)이 비탈의 위치 이동·기울기 변화 두 시나리오
모두에서 최대 (theta 스윕 + erfcinv 신호 스케일 비교). G0 는 칩·노화와 무관한
계측기 특성 데이터이므로 이를 근거로 확정해도 사후 선택이 아니다.
G0 확정 체크리스트 (사전 선언 — 통과 시 1e-2 확정, 이후 변경 금지):
  1. 실측 비탈의 probit 직선화: erfcinv(2*BER) 이 위상에 대해 선형 (가우시안
     꼬리와 부합. 주의: log-BER 은 가우시안에서 2차 곡선이므로 검사 척도로
     쓰면 정상 곡선도 탈락시킨다 — bathtub_analysis.py 가 이 판정을 구현)
  2. BER floor < 1e-5 (병행 기록 최저 theta=1e-4 가 오염되지 않을 것)
  3. 실측 sigma_j 로 본 스크립트 재실행, N=100 재확인
  4. 에러의 버스트성 점검 (비트 독립 가정의 유효성)
N 의 하한은 채택 theta 가 아니라 병행 기록 최저 theta(1e-4)의 유효 조건
N*B*theta >= ~20 이 정한다 -> B=2048 이면 N >= 100.

!! B_BITS 주의 — 읽기 1회 패턴 길이(기본 2048비트 = 256바이트 페이지)는 실측이
!! 아니라 설계 추론값이다. 실제 스윕 엔진의 버스트 길이가 확정되면 반드시 여기와
!! 일치시켜야 하며, 값이 바뀌면 다음이 연쇄로 바뀐다:
!!   - FPGA 에러 카운터 폭: 위상당 최대 에러 수 = N*B (N=100, B=2048 -> 204,800
!!     -> 18비트 이상 필요). B 나 N 을 늘리고 카운터를 안 늘리면 오버플로가
!!     조용히 일어나 욕조 곡선 어깨가 왜곡된다 -- PASS/FAIL 이 아니라 값 오염이라
!!     검증에서도 안 잡힌다. 카운터 폭은 docs/interface/ 계약에 명문화할 것.
!!   - 이 시뮬레이션의 N 권고값 (유효 시행수 N*B 가 달라지므로 재실행 필요)

위상축 절대값(스팬·경계 위치)은 임의 스케일이다 — 폭 추정 편차는 경계 근방의
국소 통계로 결정되므로 결과는 sigma_j, dphi, theta, N*B 에만 의존한다.

theta 채택 근거: --thetas 목록을 N 과 같은 방식으로 스윕해 "폭 편차 vs theta" 곡선
(monte_carlo_theta_selection.png)을 만들고, 채택값(--theta)이 저편차 구간에 있음을 보인다.
본실험 분석에서는 채택 theta 외에 1e-2 / 1e-3 / 1e-4 세 폭을 병행 기록한다
(노화가 경계 위치가 아니라 기울기를 바꾸는 경우 포착용).

시간 모델의 스텝 수는 실제 스윕 범위 = 샘플 클럭 한 주기(UI = 1/f_sclk) 기준으로
계산한다. 시뮬레이션 기하(SPAN_PS)는 경계 통계용 임의 스케일로, 시간 계산과 무관.
"""

import argparse
import csv
import math
import subprocess
from datetime import datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]

# 플롯 팔레트 (dataviz 검증 통과)
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
RAMP = ["#86b6ef", "#3987e5", "#1c5cab", "#0d366b"]  # ordinal, 밝음->어두움 = 지터 작음->큼

# 위상축 기하 (ps, 임의 스케일 — 모듈 주석 참조)
SPAN_PS = 8000.0
EDGE_L_PS = 2000.0
EDGE_R_PS = 6000.0

# 시간 모델: 0x0B fast read 오버헤드 = cmd 8 + addr 24 + dummy 8 비트
READ_OVERHEAD_BITS = 40


def true_ber(phis, sigma):
    """진짜 욕조 곡선. 각 경계에서 가우시안 지터 비탈, 윈도우 밖은 0.5로 포화."""
    s = math.sqrt(2.0) * sigma
    p_l = 0.5 * np.array([math.erfc(x) for x in (phis - EDGE_L_PS) / s])
    p_r = 0.5 * np.array([math.erfc(x) for x in (EDGE_R_PS - phis) / s])
    return np.clip(p_l + p_r, 0.0, 0.5)


def edge_estimate(ber, phis, center, theta, floor, side):
    """중앙에서 바깥으로 theta 교차점을 log 보간으로 추정. ber: (steps, trials).

    반환: (trials,) 교차 위상. 교차가 없거나 중앙부터 theta 이상이면 NaN.
    """
    if side == "left":
        idxs = np.arange(center, -1, -1)
    else:
        idxs = np.arange(center, len(phis))
    b = np.maximum(ber[idxs, :], floor)
    hit = b >= theta
    first = hit.argmax(axis=0)
    valid = hit.any(axis=0) & (first > 0)
    out = np.full(ber.shape[1], np.nan)
    f = first[valid]
    cols = np.nonzero(valid)[0]
    b_in, b_out = b[f - 1, cols], b[f, cols]
    phi_in, phi_out = phis[idxs[f - 1]], phis[idxs[f]]
    t = (np.log10(theta) - np.log10(b_in)) / (np.log10(b_out) - np.log10(b_in))
    out[valid] = phi_in + t * (phi_out - phi_in)
    return out


def width_true_at_theta(sigma, theta):
    """노이즈 없는 진짜 곡선에 같은 판정을 적용한 기준 폭 (편향 계산용)."""
    phis = np.arange(0.0, SPAN_PS, 0.01)
    p = true_ber(phis, sigma)[:, None]
    center = len(phis) // 2
    left = edge_estimate(p, phis, center, theta, 1e-30, "left")[0]
    right = edge_estimate(p, phis, center, theta, 1e-30, "right")[0]
    return right - left


def sweep_time_s(n_reads, n_steps, b_bits, f_sclk, t_read_ovh, t_phase_ovh):
    t_read = (READ_OVERHEAD_BITS + b_bits) / f_sclk + t_read_ovh
    return n_steps * (n_reads * t_read + t_phase_ovh)


def simulate(rng, sigma, n_reads, b_bits, theta, dphi, trials):
    phis = np.arange(0.0, SPAN_PS + dphi, dphi)
    nb = n_reads * b_bits
    p = true_ber(phis, sigma)
    errs = rng.binomial(nb, p[:, None], size=(len(phis), trials))
    ber = errs / nb
    center = len(phis) // 2
    floor = 0.5 / nb
    left = edge_estimate(ber, phis, center, theta, floor, "left")
    right = edge_estimate(ber, phis, center, theta, floor, "right")
    widths = right - left
    n_valid = int(np.sum(~np.isnan(widths)))
    return float(np.nanmean(widths)), float(np.nanstd(widths)), n_valid, len(phis)


def _style_axes(fig, ax):
    fig.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.grid(True, which="both", color=GRID, lw=0.7)
    ax.set_axisbelow(True)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.spines["right"].set_visible(False)
    ax.tick_params(colors=INK2, which="both")


def _legend(ax):
    leg = ax.legend(title="edge jitter σⱼ", fontsize=8.5, title_fontsize=8.5,
                    frameon=False, loc="lower left")
    for text in leg.get_texts() + [leg.get_title()]:
        text.set_color(INK2)


def make_plot(rows, sigmas, n_list, theta, dphi, time_of_n, subtitle, n_adopted, out_png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    _style_axes(fig, ax)

    ax.axvline(n_adopted, color=MUTED, lw=1.2, ls=(0, (1, 2)))
    ax.annotate(f"adopted N = {n_adopted}\n(floor set by θ_min=1e-4 logging)",
                xy=(n_adopted, 0.03), xycoords=("data", "axes fraction"),
                xytext=(5, 0), textcoords="offset points",
                color=INK2, fontsize=8.5, va="bottom")

    rule = dphi / 2.0
    ax.axhline(rule, color=MUTED, lw=1.2, ls=(0, (4, 3)))
    ax.annotate(f"selection rule: σ ≤ Δφ/2 = {rule:.1f} ps",
                xy=(n_list[0], rule), xytext=(0, 5), textcoords="offset points",
                color=INK2, fontsize=8.5)

    for i, sigma in enumerate(sigmas):
        color = RAMP[i % len(RAMP)]
        stds = [rows[(sigma, n, theta)]["width_std_ps"] for n in n_list]
        ax.plot(n_list, stds, color=color, lw=2, marker="o", ms=5,
                label=f"{sigma:g} ps")
        chosen = next((n for n, s in zip(n_list, stds) if s <= rule), None)
        if chosen is not None:
            ax.plot([chosen], [rows[(sigma, chosen, theta)]["width_std_ps"]], "o",
                    ms=11, mfc="none", mec=color, mew=1.6)
        ax.annotate(f"σⱼ={sigma:g}", xy=(n_list[-1], stds[-1]),
                    xytext=(6, 0), textcoords="offset points",
                    color=color, fontsize=8.5, va="center")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("reads per phase step, N", color=INK2)
    ax.set_ylabel("window-width estimate std (ps)", color=INK2)
    ax.set_title("Monte Carlo: reads per phase step vs measurement noise\n" + subtitle,
                 color=INK, fontsize=10, loc="left")

    secax = ax.secondary_xaxis("top", functions=(time_of_n, lambda t: np.maximum((t - time_of_n(0)) / (time_of_n(1) - time_of_n(0)), 1e-9)))
    secax.set_xlabel("full sweep time (s)  [sweep span = one clock period]", color=MUTED, fontsize=8.5)
    secax.tick_params(colors=MUTED, labelsize=8)
    secax.spines["top"].set_color(BASELINE)

    _legend(ax)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    return out_png


def make_theta_plot(rows, sigmas, thetas, n_ref, theta_adopted, dphi, out_png):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7.5, 5.0), dpi=150)
    _style_axes(fig, ax)

    rule = dphi / 2.0
    ax.axhline(rule, color=MUTED, lw=1.2, ls=(0, (4, 3)))
    ax.axvline(theta_adopted, color=MUTED, lw=1.2, ls=(0, (1, 2)))
    ax.annotate(f"adopted θ = {theta_adopted:g}",
                xy=(theta_adopted, 0.97), xycoords=("data", "axes fraction"),
                xytext=(5, 0), textcoords="offset points",
                color=INK2, fontsize=8.5, va="top")

    for i, sigma in enumerate(sigmas):
        color = RAMP[i % len(RAMP)]
        stds = [rows[(sigma, n_ref, th)]["width_std_ps"] for th in thetas]
        ax.plot(thetas, stds, color=color, lw=2, marker="o", ms=5,
                label=f"{sigma:g} ps")
        ax.annotate(f"σⱼ={sigma:g}", xy=(thetas[-1], stds[-1]),
                    xytext=(6, 0), textcoords="offset points",
                    color=color, fontsize=8.5, va="center")

    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("edge threshold θ (BER)", color=INK2)
    ax.set_ylabel("window-width estimate std (ps)", color=INK2)
    ax.set_title(f"Monte Carlo: threshold θ vs measurement noise (N={n_ref})",
                 color=INK, fontsize=10, loc="left")

    _legend(ax)
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=SURFACE)
    return out_png


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--b-bits", type=int, default=2048,
                    help="읽기 1회 패턴 길이 (bit) — 추론값, 모듈 docstring 의 B_BITS 주의 참조")
    ap.add_argument("--theta", type=float, default=1e-2,
                    help="경계 판정 BER 문턱값 (채택값 — 근거·재검토 조건은 docstring)")
    ap.add_argument("--thetas", default="3e-2,1e-2,3e-3,1e-3,3e-4,1e-4",
                    help="theta 스윕 목록 — 채택값의 근거 곡선용")
    ap.add_argument("--n-ref", type=int, default=100, help="theta 스윕 시 고정할 N")
    ap.add_argument("--dphi", type=float, default=15.0, help="위상 스텝 (ps)")
    ap.add_argument("--trials", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--sigmas", default="20,50,100,200", help="지터 비탈 폭 후보 (ps, 쉼표 구분)")
    ap.add_argument("--n-list", default="10,30,100,300,1000,3000")
    ap.add_argument("--f-sclk", type=float, default=25e6, help="SPI 클럭 (Hz, 시간 모델용)")
    ap.add_argument("--t-read-ovh", type=float, default=2e-6, help="읽기 1회 부대 시간 (s)")
    ap.add_argument("--t-phase-ovh", type=float, default=10e-6, help="위상 스텝 전환 시간 (s)")
    args = ap.parse_args()

    sigmas = [float(s) for s in args.sigmas.split(",")]
    n_list = [int(n) for n in args.n_list.split(",")]
    thetas = sorted({float(t) for t in args.thetas.split(",")} | {args.theta})
    rng = np.random.default_rng(args.seed)
    rule = args.dphi / 2.0

    ui_ps = 1e12 / args.f_sclk  # 실제 스윕 범위 = 샘플 클럭 한 주기
    n_steps = max(1, round(ui_ps / args.dphi))

    generated_at = datetime.now().isoformat(timespec="seconds")
    try:
        git_rev = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=REPO, text=True).strip()
        if subprocess.run(["git", "diff", "--quiet"], cwd=REPO).returncode != 0:
            git_rev += "-dirty"
    except Exception:
        git_rev = "unknown"

    runs = [(s, n, args.theta) for s in sigmas for n in n_list]
    runs += [(s, args.n_ref, th) for s in sigmas for th in thetas if th != args.theta]
    if args.n_ref not in n_list:
        runs += [(s, args.n_ref, args.theta) for s in sigmas]

    rows, w_true_cache = {}, {}
    for sigma, n, theta in runs:
        if (sigma, theta) not in w_true_cache:
            w_true_cache[(sigma, theta)] = width_true_at_theta(sigma, theta)
        w_true = w_true_cache[(sigma, theta)]
        mean, std, n_valid, _ = simulate(rng, sigma, n, args.b_bits,
                                         theta, args.dphi, args.trials)
        rows[(sigma, n, theta)] = {
            "sigma_ps": sigma, "n_reads": n, "b_bits": args.b_bits,
            "theta": theta, "dphi_ps": args.dphi, "trials": args.trials,
            "n_valid": n_valid, "width_true_ps": round(w_true, 2),
            "width_mean_ps": round(mean, 2),
            "width_bias_ps": round(mean - w_true, 2),
            "width_std_ps": round(std, 3),
            "sweep_time_s": round(sweep_time_s(n, n_steps, args.b_bits,
                                               args.f_sclk, args.t_read_ovh,
                                               args.t_phase_ovh), 2),
            "generated_at": generated_at, "git_rev": git_rev,
        }

    # 생성물은 build/ 하위 — 보고서 게재 시 docs/reports/로 수동 승격 (CONTRIBUTING 생성물 흐름)
    csv_path = REPO / "build" / "data" / "monte_carlo_sweep_params.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(next(iter(rows.values())).keys())
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows.values())

    def time_of_n(n):
        return sweep_time_s(np.asarray(n, dtype=float), n_steps, args.b_bits,
                            args.f_sclk, args.t_read_ovh, args.t_phase_ovh)

    subtitle = (f"(B={args.b_bits} bit/read, θ={args.theta:g}, Δφ={args.dphi:g} ps, "
                f"{args.trials} trials; ring = smallest N meeting rule)")
    png_path = make_plot(rows, sigmas, n_list, args.theta, args.dphi, time_of_n,
                         subtitle, args.n_ref,
                         REPO / "build" / "plots" / "monte_carlo_n_selection.png")
    theta_png = make_theta_plot(rows, sigmas, thetas, args.n_ref, args.theta, args.dphi,
                                REPO / "build" / "plots" / "monte_carlo_theta_selection.png")

    print(f"sweep span = UI = {ui_ps / 1000:.1f} ns @ {args.f_sclk / 1e6:g} MHz "
          f"-> {n_steps} steps of {args.dphi:g} ps")
    print(f"\n{'sigma_j':>8} {'N':>6} {'std(ps)':>9} {'bias(ps)':>9} {'sweep(s)':>9}")
    for sigma in sigmas:
        for n in n_list:
            r = rows[(sigma, n, args.theta)]
            mark = " <- rule" if r["width_std_ps"] <= rule and all(
                rows[(sigma, m, args.theta)]["width_std_ps"] > rule
                for m in n_list if m < n) else ""
            print(f"{sigma:>8g} {n:>6d} {r['width_std_ps']:>9.2f} "
                  f"{r['width_bias_ps']:>9.2f} {r['sweep_time_s']:>9.2f}{mark}")
    print(f"\n{'sigma_j':>8} {'theta':>9} {'std(ps)':>9} {'bias(ps)':>9}   (N={args.n_ref})")
    for sigma in sigmas:
        for th in thetas:
            r = rows[(sigma, args.n_ref, th)]
            print(f"{sigma:>8g} {th:>9g} {r['width_std_ps']:>9.2f} {r['width_bias_ps']:>9.2f}")
    print(f"\nrule: std <= dphi/2 = {rule:.1f} ps")
    print(f"csv : {csv_path.relative_to(REPO)}")
    print(f"png : {png_path.relative_to(REPO)}")
    print(f"png : {theta_png.relative_to(REPO)}")


if __name__ == "__main__":
    main()
