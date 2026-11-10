#!/usr/bin/env python3
"""run_a2.py — 수정안 #4 인수 기준 A2 (에지 계수기 시뮬레이션)를 돌리고 원값 표를 낸다.

실행 (저장소 루트에서, 보드 불필요 · iverilog 만 쓴다):
    python3 sim/a2/run_a2.py            # 컴파일 → 조건별 vvp(병렬) → 분석 → 표
    python3 sim/a2/run_a2.py --reuse    # build/sim_a2/ 의 CSV 를 다시 분석만
산출: build/sim_a2/<조건>_<스윕>_*.csv (TB 원값) · <조건>_wall_phase.csv (위상별 집계)

무엇을 하나 (근거: docs/interface/amendments/4.edge_counter_bathtub_v2.md §4 A2 · docs/spec/s6.bathtub_v2.md §5):
  tb_edge_a2.v 가 flash_top_spi 경로로 위상을 쓸며 읽기마다 e_i 와 정렬별 여섯 값을 낸다.
  여기서는 S-6 §5 의 해석을 그대로 적용한다 —
    1. 읽기마다 이웃 짝 (c−1, c) 중 e_(c−1) + e_c 가 그 쪽의 전이 수인 짝을 고른다
    2. 짝의 「지금 비트」 정렬 c 에서 정답 0 오류 = 셔터보다 먼저 온 상승, 정답 1 오류 = 먼저 온 하강
    3. 위상마다 먼저 온 비율 = 에지별 누적분포 → 평균 · 폭
  그리고 TB 가 아는 정답(전이마다 「지연 < 위상」)과 읽기 단위로 대조한다.

A2 의 허용 오차는 아직 정하지 않았다 (S-6 §7) — 되찾은 평균 · σ 는 --tol-ps 를 줄 때만 검사하고, 안 주면 보고만 한다.
쪽 전이 수의 「창 끝 규약」 도 A2 에서 고정할 대상이라, 합 − (쪽 안 전이 수) 의 분포를 그대로 낸다.
종료 코드: 내장 검사(TB · R8 ①-⑥ · TIMEOUT · 가짜 칩 전이 수 · 극성 · 짝과 정답 대조 · --tol-ps)가 하나라도 어긋나면 1.
"""

import argparse
import csv
import math
import os
import subprocess
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from statistics import NormalDist

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "build" / "sim_a2"
VVP = OUT / "tb_edge_a2.vvp"
B = 2048
UI_FS = 40_000_000
STEP_FS = 15_872            # 훑기 간격 — MMCM 한 칸 15.873ps 에 가장 가까운 짝수 fs
ND = NormalDist()
FAILS = []                  # 어긋난 내장 검사 — 끝에 모아 내고 종료 코드 1

# 조건: 전이 평균 도착(fs, 런치 clk_core 에지 기준) · 지터 σ(fs) · lead · 유휴 값
# σ 는 에지 종류에 붙는다 (상승 8ps · 하강 20ps) — 평균만 뒤집어 「상승이 이른 칩 · 하강이 이른 칩」
#
# t0 이동(정렬 번호가 한 칸 옮겨 가는 위상)은 실물에서 pay 의 CDC 경로 지연 δ 가 정한다. RTL
# 시뮬레이션은 δ = 0 이라 이동이 늘 위상 0 이다. DUT 가 보는 것은 (도착 − δ) · (위상 − δ) 뿐이므로
# δ 를 넣는 대신 도착 시각을 옮겨 「덩어리가 t0 이동의 어느 쪽에 있는가」 를 바꾼다 (tb 머리말 lead):
#   덩어리가 이동 오른쪽(δ < 도착)   — 도착 8.0 · 8.5ns, lead 0
#   이동이 덩어리 안(δ 가 두 에지 사이) — 도착 39.75 · 40.25ns, lead 1 (= 이동 기준 −0.25 · +0.25ns)
#   덩어리가 이동 왼쪽(도착 < δ)     — 도착 36.0 · 36.5ns, lead 1 (= 이동 기준 −4.0 · −3.5ns)
def chip(early, rise_ns, fall_ns, **kw):
    """early = 'rise' 면 rise_ns 가 이른 쪽. 두 값은 (이른, 늦은) 도착."""
    a, b = (rise_ns, fall_ns)
    r, f = (a, b) if early == "rise" else (b, a)
    return dict(rise_fs=round(r * 1e6), fall_fs=round(f * 1e6), sig_r_fs=8_000, sig_f_fs=20_000, **kw)


def wall(lo_ns):
    return dict(ph0_fs=round(lo_ns * 1e6), step_fs=2_000, nph=381, n=16)   # 0.76ns 구간, 2ps 간격, 16읽기


SCAN = dict(ph0_fs=0, step_fs=STEP_FS, nph=2520, n=1)             # 훑기: 전 UI, N = 1 START
CASES = {
    # 이름: (조건, {스윕: 파라미터})
    "rise_first":        (chip("rise", 8.0, 8.5), {"scan": SCAN, "wall": wall(7.9)}),
    "fall_first":        (chip("fall", 8.0, 8.5), {"scan": SCAN, "wall": wall(7.9)}),
    "rise_first_t0blk":  (chip("rise", 39.75, 40.25, lead=1), {"scan": SCAN, "wall": wall(39.65)}),
    "fall_first_t0blk":  (chip("fall", 39.75, 40.25, lead=1), {"wall": wall(39.65)}),
    "rise_first_t0right": (chip("rise", 36.0, 36.5, lead=1), {"scan": SCAN, "wall": wall(35.9)}),
    "fall_first_t0right": (chip("fall", 36.0, 36.5, lead=1), {"wall": wall(35.9)}),
    # 읽기 사이에 선이 1 로 남는다고 가정 (쪽 머리 전이 없음)
    "fall_first_idlehi": (chip("fall", 8.0, 8.5, idle_hi=1), {"wall": wall(7.9)}),
    # MISO 0 고정 — 극성 검사
    "dead":              (chip("rise", 8.0, 8.5, dead=1), {"dead": dict(ph0_fs=0, step_fs=624_000, nph=64, n=4)}),
}
INT_COLS = ("ph_fs start read_idx page e_i e_c0 e_c1 e_c2 e1_c0 e1_c1 e1_c2 err_bits err_reads timeout "
            "t_r_int t_f_int t_ra0 t_fa0 t_ra1 t_fa1 t_head_dir t_head_a0 t_head_a1 "
            "t_end_dir t_end_a0 t_end_a1").split()


# ---------------- PRBS (flash_prbs15 와 독립 구현) ----------------
def prbs_bits(page, n):
    lfsr = (1 << 14) | (page & 0x3FFF)
    out = []
    for _ in range(n):
        out.append((lfsr >> 14) & 1)
        lfsr = ((lfsr << 1) & 0x7FFF) | (((lfsr >> 14) ^ (lfsr >> 13)) & 1)
    return out


_PAGE = {}


def page_stats(page):
    """쪽 안(비트 0..B−1 사이) 전이 수와 쪽 끝 전이(비트 B−1 → 다음 쪽 첫 비트 1)."""
    if page not in _PAGE:
        b = prbs_bits(page, B)
        r = sum(1 for i in range(B - 1) if b[i] == 0 and b[i + 1] == 1)
        f = sum(1 for i in range(B - 1) if b[i] == 1 and b[i + 1] == 0)
        nxt = prbs_bits(page + 1, 1)[0]
        end_dir = 0 if b[-1] == nxt else (1 if nxt else 2)
        _PAGE[page] = dict(r_int=r, f_int=f, end_dir=end_dir, first=b[0], last=b[-1])
    return _PAGE[page]


# ---------------- 실행 ----------------
def build():
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = [str(REPO / "sim/a2/tb_edge_a2.v"), str(REPO / "sim/smoke/unisim_stub.v")] + \
           [str(p) for p in sorted((REPO / "fpga/rtl/flash").glob("*.v"))]
    subprocess.run(["iverilog", "-g2005", "-o", str(VVP), *srcs], check=True)


def jobs():
    """(조건, 스윕, 조각 번호, plusarg dict, csv 경로). 스윕은 위상 조각으로 나눠 병렬로 돌린다."""
    out = []
    seed = 1000
    for name, (cond, sweeps) in CASES.items():
        for sw, s in sweeps.items():
            chunk = 210 if sw == "scan" else 32
            for j, i0 in enumerate(range(0, s["nph"], chunk)):
                seed += 1
                args = dict(cond, ph0_fs=s["ph0_fs"] + i0 * s["step_fs"], step_fs=s["step_fs"],
                            nph=min(chunk, s["nph"] - i0), n=s["n"], seed=seed)
                out.append((name, sw, j, args, OUT / f"{name}_{sw}_{j:02d}.csv"))
    return out


def run_job(job):
    name, sw, j, args, path = job
    cmd = ["vvp", str(VVP), f"+out={path}"] + [f"+{k}={v}" for k, v in args.items()]
    r = subprocess.run(cmd, capture_output=True, text=True)
    line = next((ln for ln in r.stdout.splitlines() if ln.startswith("A2 TB:")), "A2 TB: (요약 줄 없음)")
    ok = r.returncode == 0 and "PASS: all checks passed" in r.stdout
    return name, sw, j, ok, line


def load(name, sw, ph0_fs):
    """조각 CSV 를 모은다. x_fs = 스윕 시작 위상부터 이어 붙인 위상 (40ns 를 넘어 도는 스윕용)."""
    rows = []
    for p in sorted(OUT.glob(f"{name}_{sw}_[0-9][0-9].csv")):
        with p.open() as f:
            for d in csv.DictReader(f):
                r = {k: int(d[k]) for k in INT_COLS}
                r["x_fs"] = r["ph_fs"] + (UI_FS if r["ph_fs"] < ph0_fs else 0)
                rows.append(r)
    return rows


# ---------------- 읽기 하나의 해석 ----------------
def r8_viol(r):
    """R8 ④⑤⑥ 위반 수 (①②③ 은 START 단위 — tb 와 check_starts 가 본다)."""
    e = (r["e_c0"], r["e_c1"], r["e_c2"])
    o = (r["e1_c0"], r["e1_c1"], r["e1_c2"])
    v = 0
    v += min(e) != r["e_i"]                                          # ④
    v += sum(o[c] > e[c] for c in range(3))                          # ⑤
    for c in range(3):
        for c2 in range(c + 1, 3):
            v += abs((e[c] - 2 * o[c]) - (e[c2] - 2 * o[c2])) > c2 - c   # ⑥
    return v


def pair_offsets(r):
    """짝 (0,1) · (1,2) 의 합 − 쪽 안 전이 수. 키는 「지금 비트」 정렬 번호 c."""
    ps = page_stats(r["page"])
    t_int = ps["r_int"] + ps["f_int"]
    return {1: r["e_c0"] + r["e_c1"] - t_int, 2: r["e_c1"] + r["e_c2"] - t_int}


def arrived(r, j):
    """「런치 + 위상 + 40ns × j」 셔터까지 온 전이 — (쪽 안 상승, 쪽 안 하강, 쪽 끝, 쪽 머리)."""
    ps = page_stats(r["page"])
    if j <= -1:
        return 0, 0, 0, 0
    if j == 0:
        return r["t_ra0"], r["t_fa0"], r["t_end_a0"], r["t_head_a0"]
    if j == 1:
        return r["t_ra1"], r["t_fa1"], r["t_end_a1"], r["t_head_a1"]
    return ps["r_int"], ps["f_int"], int(r["t_end_dir"] != 0), int(r["t_head_dir"] != 0)


def truth_expect(r, c, lead):
    """TB 가 아는 정답으로 짝 (c−1, c) 가 내야 할 네 값 — (지금·정답0, 지금·정답1, 다음·정답0, 다음·정답1).

    지금 비트 정렬 c 가 비트 m 으로 들어가는 전이를 보는 셔터는 「그 전이의 런치 + 위상 + 40ns × j」,
    j = c − 2 + lead 다 (flash_rx 의 창과 flash_spi_shim 의 프리앰블 4비트에서 나온다).
    짝이 이웃 비트끼리의 맞댐이려면 그 셔터에 찍힌 값이 「전이 앞 비트 · 뒤 비트」 둘 중 하나여야 한다 —
    한 셔터 뒤(j+1)까지는 전부 와 있고, 한 셔터 앞(j−1)까지는 하나도 안 와 있어야 한다. 아니면 None.
    """
    ps = page_stats(r["page"])
    R, F = ps["r_int"], ps["f_int"]
    end_r, end_f = r["t_end_dir"] == 1, r["t_end_dir"] == 2
    head_r, head_f = r["t_head_dir"] == 1, r["t_head_dir"] == 2
    j = c - 2 + lead
    if arrived(r, j + 1) != (R, F, int(r["t_end_dir"] != 0), int(r["t_head_dir"] != 0)):
        return None
    if arrived(r, j - 1) != (0, 0, 0, 0):
        return None
    ra, fa, end_arr, head_arr = arrived(r, j)
    # 다음 비트 정렬 c−1 의 창 첫 샘플: c−1 = 0 이면 합성 프리앰블(= 비트 0 과 같은 1)이라 쪽 머리가 가려진다
    head_in = (c - 1) == 1
    return (ra + (end_r and end_arr),                           # 지금 · 정답 0 = 먼저 온 상승 (쪽 끝 포함)
            fa + (end_f and end_arr),                           # 지금 · 정답 1 = 먼저 온 하강
            (F - fa) + (head_in and head_f and not head_arr),   # 다음 · 정답 0 = 아직 안 온 하강
            (R - ra) + (head_in and head_r and not head_arr))   # 다음 · 정답 1 = 아직 안 온 상승


def observed(r, c):
    e, o = (r["e_c0"], r["e_c1"], r["e_c2"]), (r["e1_c0"], r["e1_c1"], r["e1_c2"])
    return (e[c] - o[c], o[c], e[c - 1] - o[c - 1], o[c - 1])


def analyse(r, lead):
    off = pair_offsets(r)
    truth_ok = {c: (truth_expect(r, c, lead) == observed(r, c)) for c in (1, 2)}
    return dict(off=off,
                lit={c for c in (1, 2) if off[c] in (0, 1)},       # 명세 문언: 합 = 전이 수 (+ 쪽 끝 0-1)
                ext={c for c in (1, 2) if off[c] in (0, 1, 2)},    # 쪽 머리 몫까지 허용
                truth_ok=truth_ok)


def pick_pairs(rows, ana):
    """읽기마다 짝 하나. 맞는 짝이 하나면 그것, 둘이면(바닥) 스윕에서 가장 가까운 「하나뿐인」 위상의 짝.

    반환: 지금 비트 정렬 번호 목록 (못 고르면 None), 둘 중에서 고른 읽기 수.
    """
    uniq = [next(iter(a["ext"])) if len(a["ext"]) == 1 else None for a in ana]
    ph = [r["x_fs"] for r in rows]
    known = [(ph[i], uniq[i]) for i in range(len(rows)) if uniq[i] is not None]
    out, n_tb = [], 0
    for i, a in enumerate(ana):
        if uniq[i] is not None:
            out.append(uniq[i])
        elif len(a["ext"]) == 2 and known:
            c = min(known, key=lambda kv: abs(kv[0] - ph[i]))[1]
            out.append(c)
            n_tb += 1
        else:
            out.append(None)
    return out, n_tb


# ---------------- 누적분포 → 평균 · 폭 ----------------
def fit_moment(xs, ks, ns):
    """누적분포의 차분(pdf)으로 평균 · 표준편차. xs 는 오름차순 위상(ps)."""
    F = [k / n for k, n in zip(ks, ns)]
    m0 = m1 = m2 = 0.0
    for i in range(len(xs) - 1):
        d, mid = F[i + 1] - F[i], 0.5 * (xs[i] + xs[i + 1])
        m0 += d
        m1 += d * mid
        m2 += d * mid * mid
    if m0 <= 0:
        return float("nan"), float("nan"), F[0], F[-1]
    mu = m1 / m0
    return mu, math.sqrt(max(m2 / m0 - mu * mu, 0.0)), F[0], F[-1]


def fit_probit(xs, ks, ns, iters=30):
    """정규 누적분포 최우 맞춤 (프로빗 회귀, IRLS). 반환 (평균, σ)."""
    x0 = sum(xs) / len(xs)
    pts = [(x - x0, k, n) for x, k, n in zip(xs, ks, ns) if n > 0]
    inner = [(x, ND.inv_cdf(k / n)) for x, k, n in pts if 0 < k < n]
    if len(inner) < 2:
        return float("nan"), float("nan")
    # 시작값: 안쪽 점의 프로빗 직선
    mx = sum(x for x, _ in inner) / len(inner)
    mz = sum(z for _, z in inner) / len(inner)
    sxx = sum((x - mx) ** 2 for x, _ in inner)
    b = sum((x - mx) * (z - mz) for x, z in inner) / sxx
    a = mz - b * mx
    for _ in range(iters):
        g0 = g1 = h00 = h01 = h11 = 0.0
        for x, k, n in pts:
            eta = max(min(a + b * x, 8.0), -8.0)
            p = min(max(ND.cdf(eta), 1e-12), 1 - 1e-12)
            d = ND.pdf(eta)
            w = n * d * d / (p * (1 - p))
            s = (k - n * p) * d / (p * (1 - p))
            g0 += s
            g1 += s * x
            h00 += w
            h01 += w * x
            h11 += w * x * x
        det = h00 * h11 - h01 * h01
        if det <= 0:
            break
        da, db = (h11 * g0 - h01 * g1) / det, (h00 * g1 - h01 * g0) / det
        a, b = a + da, b + db
        if abs(da) + abs(db) < 1e-12:
            break
    return x0 - a / b, 1.0 / b


# ---------------- 표 ----------------
def region_of(ph_fs, cond):
    """벽 스윕의 (이어 붙인) 위상을 주입값 기준 구간으로 — 표를 줄이기 위한 묶음일 뿐, 해석에는 쓰지 않는다."""
    edges = sorted([(cond["rise_fs"], cond["sig_r_fs"], "상승"), (cond["fall_fs"], cond["sig_f_fs"], "하강")])
    (m1, s1, n1), (m2, s2, n2) = edges
    if ph_fs < m1 - 5 * s1:
        return "0 왼쪽 바닥"
    if ph_fs <= m1 + 5 * s1:
        return f"1 왼쪽 벽({n1})"
    if ph_fs < m2 - 5 * s2:
        return "2 천장"
    if ph_fs <= m2 + 5 * s2:
        return f"3 오른쪽 벽({n2})"
    return "4 오른쪽 바닥"


def check_starts(rows):
    """R8 ①②③ — START(위상 점)마다 Σe_i == ERR_BITS, count(e_i>0) == ERR_READS, e_i ≤ B."""
    by = defaultdict(list)
    for r in rows:
        by[(r["ph_fs"], r["start"])].append(r)
    v = 0
    for rs in by.values():
        v += sum(r["e_i"] for r in rs) != rs[0]["err_bits"]
        v += sum(r["e_i"] > 0 for r in rs) != rs[0]["err_reads"]
        v += sum(r["e_i"] > B for r in rs)
    return v, len(by)


def report_common(name, sw, rows, cond):
    ana = [analyse(r, cond.get("lead", 0)) for r in rows]
    v123, n_st = check_starts(rows)
    v456 = sum(r8_viol(r) for r in rows)
    tmo = sum(r["timeout"] for r in rows)
    model = sum((r["t_r_int"], r["t_f_int"], r["t_end_dir"]) !=
                (page_stats(r["page"])["r_int"], page_stats(r["page"])["f_int"], page_stats(r["page"])["end_dir"])
                for r in rows)
    print(f"\n### {name} · {sw} — START {n_st} · 읽기 {len(rows)}")
    print(f"- 조건: 상승 도착 {cond['rise_fs'] / 1e6:.3f}ns σ {cond['sig_r_fs'] / 1e3:.0f}ps · "
          f"하강 도착 {cond['fall_fs'] / 1e6:.3f}ns σ {cond['sig_f_fs'] / 1e3:.0f}ps · lead {cond.get('lead', 0)} · "
          f"유휴 값 {cond.get('idle_hi', 0)}")
    print(f"- R8 ①②③ 위반 {v123} · ④⑤⑥ 위반 {v456} · TIMEOUT {tmo} · "
          f"가짜 칩 전이 수 ≠ 스크립트 PRBS 전이 수 {model}")
    n_lit = Counter(len(a["lit"]) for a in ana)
    n_ext = Counter(len(a["ext"]) for a in ana)
    print(f"- 맞는 짝 수 (합 − 쪽 안 전이 수 ∈ {{0,1}}): 0개 {n_lit[0]} · 1개 {n_lit[1]} · 2개 {n_lit[2]}")
    print(f"- 맞는 짝 수 (∈ {{0,1,2}}):                0개 {n_ext[0]} · 1개 {n_ext[1]} · 2개 {n_ext[2]}")
    # 합으로 고른 짝이 정답과 네 값 모두 일치하는가
    sel_ok = sum(all(a["truth_ok"][c] for c in a["ext"]) and len(a["ext"]) > 0 for a in ana)
    truth_not_sel = sum(any(a["truth_ok"][c] and c not in a["ext"] for c in (1, 2)) for a in ana)
    print(f"- 합으로 맞은 짝이 전부 정답(네 값)과 일치한 읽기 {sel_ok}/{len(rows)} · "
          f"정답과 일치하는데 합 규칙이 못 고른 짝이 있는 읽기 {truth_not_sel}")
    for what, n in (("R8 ①②③", v123), ("R8 ④⑤⑥", v456), ("TIMEOUT", tmo), ("가짜 칩 전이 수 ≠ PRBS", model),
                    ("정답과 일치하는데 합 규칙이 못 고른 짝", truth_not_sel)):
        if n:
            FAILS.append(f"{name} · {sw}: {what} {n}")
    return ana


def report_scan(name, rows, cond):
    ana = report_common(name, "scan", rows, cond)
    # 위상축 구간표: (오류 0 정렬, 맞는 짝, 합 − 전이 수) 가 같은 이웃 위상을 묶는다
    print("\n| 위상 (ns) | 스텝 | 오류 0 정렬 | 맞는 짝 (다음, 지금) | 정답과 네 값이 일치하는 짝 | "
          "합 − 쪽 안 전이 수 (짝 0·1 / 1·2) | e_i |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    order = sorted(range(len(rows)), key=lambda i: rows[i]["ph_fs"])
    seg = None
    segs = []
    for i in order:
        r, a = rows[i], ana[i]
        clean = tuple(c for c in range(3) if (r["e_c0"], r["e_c1"], r["e_c2"])[c] == 0)
        wall = r["e_i"] > 0
        key = (clean, tuple(sorted(a["ext"])), tuple(c for c in (1, 2) if a["truth_ok"][c]), wall)
        if seg and seg["key"] == key:
            seg["hi"] = r["ph_fs"]
            seg["n"] += 1
            seg["off"].add((a["off"][1], a["off"][2]))
            seg["ei"] = (min(seg["ei"][0], r["e_i"]), max(seg["ei"][1], r["e_i"]))
        else:
            seg = dict(key=key, lo=r["ph_fs"], hi=r["ph_fs"], n=1, off={(a["off"][1], a["off"][2])},
                       ei=(r["e_i"], r["e_i"]))
            segs.append(seg)
    for s in segs:
        clean, ext, tok, _ = s["key"]

        def fmt(j):
            vals = sorted({o[j] for o in s["off"]})
            return (",".join(map(str, vals)) if len(vals) <= 4 else f"{vals[0]}..{vals[-1]}")
        print(f"| {s['lo'] / 1e6:.3f} - {s['hi'] / 1e6:.3f} | {s['n']} | "
              f"{','.join(map(str, clean)) or '없음'} | "
              f"{' · '.join(f'({c - 1},{c})' for c in ext) or '없음'} | "
              f"{' · '.join(f'({c - 1},{c})' for c in tok) or '없음'} | {fmt(0)} / {fmt(1)} | "
              f"{s['ei'][0]}-{s['ei'][1]} |")


def report_wall(name, rows, cond, tol):
    ana = report_common(name, "wall", rows, cond)
    sel, n_tb = pick_pairs(rows, ana)
    none = sum(c is None for c in sel)
    sel_truth = sum(c is not None and a["truth_ok"][c] for c, a in zip(sel, ana))
    print(f"- 짝 고르기: 하나뿐 {len(rows) - n_tb - none} · 둘 중 이웃 위상으로 고름 {n_tb} · 못 고름 {none} · "
          f"고른 짝이 정답(네 값)과 일치 {sel_truth}/{len(rows)}")
    if sel_truth != len(rows):
        FAILS.append(f"{name} · wall: 고른 짝이 정답과 다른 읽기 {len(rows) - sel_truth}")

    # 위상별 집계
    by = defaultdict(lambda: dict(n=0, kr=0, nr=0, kf=0, nf=0, tie=0, tie1=0, now=Counter(), tr=0, tf=0))
    for r, a, c in zip(rows, ana, sel):
        if c is None:
            continue
        ps = page_stats(r["page"])
        now0, now1, _, _ = observed(r, c)
        d = by[r["x_fs"]]
        d["n"] += 1
        d["kr"] += now0
        d["nr"] += ps["r_int"] + (ps["end_dir"] == 1)
        d["kf"] += now1
        d["nf"] += ps["f_int"] + (ps["end_dir"] == 2)
        e = (r["e_c0"], r["e_c1"], r["e_c2"])
        d["tie"] += e[c] == e[c - 1]
        d["tie1"] += abs(e[c] - e[c - 1]) <= 1
        d["now"][c] += 1
        # 정답 누적분포 (TB 가 아는 「그 셔터까지 온 전이」, 지금 비트 창과 같은 집합: 쪽 안 + 쪽 끝)
        ra, fa, end_arr, _ = arrived(r, c - 2 + cond.get("lead", 0))
        d["tr"] += ra + (r["t_end_dir"] == 1 and end_arr)
        d["tf"] += fa + (r["t_end_dir"] == 2 and end_arr)
    phs = sorted(by)
    with (OUT / f"{name}_wall_phase.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow("ph_ps reads rise_arrived rise_total fall_arrived fall_total tie tie_within1 now_c1 now_c2 "
                   "truth_rise_arrived truth_fall_arrived".split())
        for p in phs:
            d = by[p]
            w.writerow([p / 1000, d["n"], d["kr"], d["nr"], d["kf"], d["nf"], d["tie"], d["tie1"],
                        d["now"][1], d["now"][2], d["tr"], d["tf"]])

    xs = [p / 1000 for p in phs]                        # ps
    print("\n| 에지 | 주입 평균 (ps) | 주입 σ (ps) | 되찾은 평균 — 최우 (ps) | 되찾은 σ — 최우 (ps) | "
          "평균 — 차분 (ps) | σ — 차분 (ps) | 누적분포 양 끝 | 평균 차 (ps) | σ 차 (ps) | 정답 누적분포와 다른 위상 수 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for label, kk, nn, tk, mu_fs, sg_fs in (("상승", "kr", "nr", "tr", cond["rise_fs"], cond["sig_r_fs"]),
                                             ("하강", "kf", "nf", "tf", cond["fall_fs"], cond["sig_f_fs"])):
        ks, ns = [by[p][kk] for p in phs], [by[p][nn] for p in phs]
        mu, sg = fit_probit(xs, ks, ns)
        mm, ms, f0, f1 = fit_moment(xs, ks, ns)
        diff_truth = sum(by[p][kk] != by[p][tk] for p in phs)
        print(f"| {label} | {mu_fs / 1000:.3f} | {sg_fs / 1000:.3f} | {mu:.3f} | {sg:.3f} | {mm:.3f} | {ms:.3f} | "
              f"{f0:.4f} → {f1:.4f} | {mu - mu_fs / 1000:+.3f} | {sg - sg_fs / 1000:+.3f} | {diff_truth}/{len(phs)} |")
        if diff_truth:
            FAILS.append(f"{name} · wall: {label} 정답 누적분포와 다른 위상 {diff_truth}/{len(phs)}")
        err = max(abs(mu - mu_fs / 1000), abs(sg - sg_fs / 1000))
        if tol is not None and not err <= tol:                    # NaN 도 어긋남
            FAILS.append(f"{name} · wall: {label} 되찾은 평균 · σ 오차 {err:.3f}ps > --tol-ps {tol}")

    print("\n| 구간 (주입값 ±5σ 로 나눔) | 위상 수 | 읽기 | 두 정렬이 비긴 읽기 | 차 ≤ 1 인 읽기 | 지금 비트 = 정렬 1 | 지금 비트 = 정렬 2 | "
          "합 − 쪽 안 전이 수 (고른 짝) | min 이 지금 비트 쪽 · 다음 비트 쪽 · 동률 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    reg = defaultdict(lambda: dict(ph=set(), n=0, tie=0, tie1=0, now=Counter(), off=Counter(), who=Counter()))
    for r, a, c in zip(rows, ana, sel):
        if c is None:
            continue
        g = reg[region_of(r["x_fs"], cond)]
        e = (r["e_c0"], r["e_c1"], r["e_c2"])
        g["ph"].add(r["x_fs"])
        g["n"] += 1
        g["tie"] += e[c] == e[c - 1]
        g["tie1"] += abs(e[c] - e[c - 1]) <= 1
        g["now"][c] += 1
        g["off"][a["off"][c]] += 1
        g["who"]["지금" if e[c] < e[c - 1] else "다음" if e[c - 1] < e[c] else "동률"] += 1
    for k in sorted(reg):
        g = reg[k]
        off = " · ".join(f"{o:+d}: {n}" for o, n in sorted(g["off"].items()))
        print(f"| {k[2:]} | {len(g['ph'])} | {g['n']} | {g['tie']} ({100 * g['tie'] / g['n']:.1f}%) | "
              f"{g['tie1']} ({100 * g['tie1'] / g['n']:.1f}%) | {g['now'][1]} | {g['now'][2]} | {off} | "
              f"{g['who']['지금']} · {g['who']['다음']} · {g['who']['동률']} |")

    # 천장의 읽기별 원값 (쪽 0-15 한 묶음) — 수정안 #4 A4 의 25MHz 방향 대조가 기대는 유도
    ceil = [(r, c) for r, a, c in zip(rows, ana, sel)
            if c is not None and region_of(r["x_fs"], cond).startswith("2")]
    if ceil:
        mid = sorted({r["x_fs"] for r, _ in ceil})
        mid = mid[len(mid) // 2]
        rs = [(r, c) for r, c in ceil if r["x_fs"] == mid]
        sr = sum(page_stats(r["page"])["r_int"] for r, _ in rs)
        sf = sum(page_stats(r["page"])["f_int"] for r, _ in rs)
        s_ei = sum(r["e_i"] for r, _ in rs)
        s_now = sum((r["e_c0"], r["e_c1"], r["e_c2"])[c] for r, c in rs)
        s_nxt = sum((r["e_c0"], r["e_c1"], r["e_c2"])[c - 1] for r, c in rs)
        s_now1 = sum((r["e1_c0"], r["e1_c1"], r["e1_c2"])[c] for r, c in rs)
        s_nxt1 = sum((r["e1_c0"], r["e1_c1"], r["e1_c2"])[c - 1] for r, c in rs)
        print(f"\n- 천장 한가운데 위상 {mid / 1e6:.3f}ns 의 {len(rs)}읽기 합: Σe_i(min) = {s_ei} · "
              f"쪽 안 상승 수 합 {sr} · 하강 수 합 {sf} · 지금 비트 Σe = {s_now} (정답 1 쪽 {s_now1}) · "
              f"다음 비트 Σe = {s_nxt} (정답 1 쪽 {s_nxt1})")


def report_dead(name, rows):
    v123, n_st = check_starts(rows)
    v456 = sum(r8_viol(r) for r in rows)
    pol = sum((r["e1_c0"], r["e1_c1"], r["e1_c2"]) != (r["e_c0"], r["e_c1"], r["e_c2"]) for r in rows)
    ones = sum(sum(prbs_bits(r["page"], B)) != r["e_c1"] for r in rows)
    print(f"\n### {name} — MISO 0 고정 · START {n_st} · 읽기 {len(rows)}")
    print(f"- R8 ①②③ 위반 {v123} · ④⑤⑥ 위반 {v456} · TIMEOUT {sum(r['timeout'] for r in rows)}")
    print(f"- 극성: (e1_c0, e1_c1, e1_c2) ≠ (e_c0, e_c1, e_c2) 인 읽기 {pol}/{len(rows)}")
    print(f"- e_c1 ≠ 그 쪽 PRBS 의 1 개수인 읽기 {ones}/{len(rows)}")
    for what, n in (("R8 ①②③", v123), ("R8 ④⑤⑥", v456), ("TIMEOUT", sum(r["timeout"] for r in rows)),
                    ("극성", pol), ("e_c1 ≠ PRBS 1 개수", ones)):
        if n:
            FAILS.append(f"{name}: {what} {n}")
    ex = rows[0]
    print(f"- 예 (쪽 {ex['page']}): e_c = ({ex['e_c0']}, {ex['e_c1']}, {ex['e_c2']}) · "
          f"e1_c = ({ex['e1_c0']}, {ex['e1_c1']}, {ex['e1_c2']}) · e_i = {ex['e_i']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reuse", action="store_true", help="vvp 를 다시 돌리지 않고 있는 CSV 로 분석만")
    ap.add_argument("--tol-ps", type=float, help="되찾은 평균 · σ (최우) 의 허용 오차 ps — 안 주면 보고만")
    args = ap.parse_args()

    if not args.reuse:
        build()
        js = jobs()
        print(f"== A2: vvp {len(js)}개 실행 (조건 {len(CASES)})", flush=True)
        with ThreadPoolExecutor(max_workers=max(1, (os.cpu_count() or 2) - 2)) as ex:
            res = list(ex.map(run_job, js))
        bad = [x for x in res if not x[3]]
        tot = Counter()
        for name, sw, j, ok, line in res:
            for kv in line.split()[2:]:
                k, _, v = kv.partition("=")
                tot[k] += int(v)
        print("== TB 합계 (R8 은 TB 가 읽기마다 검사): " + " ".join(f"{k}={v}" for k, v in tot.items()))
        for name, sw, j, ok, line in bad:
            print(f"FAIL {name}_{sw}_{j:02d}: {line}")
        if bad:
            return 1

    print("\n## 수정안 #4 A2 — 원값 (되찾은 평균 · σ 는 " + (f"--tol-ps {args.tol_ps} 로 검사)" if args.tol_ps is not None
                                                          else "검사 없음 — 허용 오차 미정, S-6 §7)"))
    print("위상 = clk_sample 이 clk_core 보다 늦은 양. 전이 도착 시각은 런치 clk_core 에지 기준. "
          "t0 이동은 위상 0(= 40ns)에 있다 (시뮬레이션의 pay CDC 지연 0).")
    for name, (cond, sweeps) in CASES.items():
        for sw, par in sweeps.items():
            rows = load(name, sw, par["ph0_fs"])
            if not rows:
                print(f"\n### {name} · {sw} — CSV 없음")
                continue
            if sw == "scan":
                report_scan(name, rows, cond)
            elif sw == "wall":
                report_wall(name, rows, cond, args.tol_ps)
            else:
                report_dead(name, rows)
    print(f"\n## 내장 검사 — 어긋남 {len(FAILS)}")
    for f in FAILS:
        print(f"FAIL {f}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
