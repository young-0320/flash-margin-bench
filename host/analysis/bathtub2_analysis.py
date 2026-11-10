# bathtub2_analysis.py — 욕조 v2(bathtub2_*) 분석: 끊긴 축 그림(P1) · 에지별 누적분포 · pdf · DCD (S-6 §5)
#
# 사용: uv run python host/analysis/bathtub2_analysis.py [bathtub2_….csv …]
#       파일을 안 주면 data/ 아래(하위 폴더 포함) bathtub2_*.csv 전부. _reads · _invalid 는 건너뛴다
#
# 입력: bathtub2_<target>[_<UID>]_<UTC>.csv + 짝 _reads.csv (수정안 #4 §2.5). v1 파일(sweep_*)은 받지 않는다 —
#       v1 분석기도 v2 파일을 안 읽는다(접두사 · n_reads 섞임). flags 에 reads_gap 이 붙은 스텝은 메인 행만 쓰고 읽기별 값은 안 쓴다
# 출력: build/bathtub/v2/
#   <stem>_steps.csv    스텝마다 — 그림에 쓴 행(pass) · BER · 0 오류면 BER 상한 · 에지별 「먼저 온 비율」 · 짝 못 찾은 읽기
#   <stem>_p1.png       끊긴 축 욕조 (v1 bathtub_p1_figures.py 와 같은 방향 · W = 1,000ps)
#   <stem>_edges.png    에지별 누적분포 · pdf
#   bathtub2_edges.csv  파일마다 — 에지별 평균 · 폭, DCD, 짝 못 찾은 읽기 수
#
# 에지 해석 — 「승자」 를 쓰지 않는다 ([D55-19] · 개념 16):
#   읽기마다 이웃 짝 (c − 1, c) 의 어긋남 = e_(c−1) + e_c − (쪽 안 전이 수). 0 · 1 · 2 면 그 짝이 맞는다
#   (쪽 끝 전이는 먼저 왔을 때 「지금 비트」 창에 들어 +1, 쪽 머리 상승은 아직 안 왔을 때 「다음 비트」 창에 들어 +1 —
#   실제 RTL 출력은 2 까지 간다). 이웃 위상은 찾지 않고 읽기 하나로 정한다:
#     옆 짝 = 훑기 덩어리 중심(같은 파일의 scan 행, 원형 거리)의 왼쪽(중심 스텝 포함)이면 「지금 비트」 = 1 (짝 (0,1)), 오른쪽이면 2 (짝 (1,2)).
#     바닥 쪽 꼬리에서는 두 짝이 다 맞는다 — 한 칸 어긋난 정렬은 오류가 정확히 전이 수라서. 그때 옆 짝이 맞다
#     (덩어리 왼쪽은 에지가 아직 안 온 쪽, 오른쪽은 다 온 쪽 — 「지금 비트」 가 1 이든 2 든 맞는 쪽이 옆 짝과 같다)
#     옆 짝이 맞으면(혼자든 둘 다든) 옆 짝. 옆 아닌 짝만 맞으면 옆 짝의 |어긋남| > FAR 일 때만 받고, 아니면 짝 없음.
#     둘 다 안 맞으면 짝 없음. 짝 없는 읽기는 쓰지 않고 결과별로 센다 (reads_near · reads_none)
#   짝의 「지금 비트」 정렬 c 에서 정답 0 오류 e_c − e1_c = 셔터보다 먼저 온 상승, 정답 1 오류 e1_c = 먼저 온 하강.
#   쪽 = base_sector × 16 + read_idx. 상승 수 = 쪽 안 상승 + 쪽 끝 상승(쪽 마지막 비트 0 → 다음 쪽 첫 비트 1),
#   하강 수 = 쪽 안 하강. 위상마다 비율 = Σ 먼저 온 수 ÷ Σ 그 에지 수 → 에지별 누적분포(CDF)
#   CDF 는 벽 집중 구간(ceil · wall 행 — 덩어리와 바깥 걷기, 이어진 스텝)에서만 만든다. scan 행(N = 1)은 쓰지 않는다
#   pdf = 이웃 스텝 사이 CDF 증가분을 그 중점에 둔 것. 평균 = pdf 의 1차 모멘트, 폭 = pdf 의 표준편차(ps).
#     폭에는 스텝(15.87ps) 양자화 몫(제곱으로 약 h²/12)이 들어 있다 — 보정하지 않는다
#   DCD = 하강 평균 − 상승 평균
#   위상 x = 훑기 덩어리 중점(첫 · 끝 스텝의 중점) 기준 ps — v1 P1 그림과 같은 원점
# BER 상한: 오류 0 스텝은 BER < 3 ÷ (n_reads × b_bits) (95%) — 그 높이에 ▽ 로 찍는다 (S-6 §5)
# 해석은 A2(시뮬레이션) · A4 · A5(실칩 대조)를 통과한 뒤에만 쓴다 (S-6 §5-5) — 이 스크립트는 계산만 한다

import argparse
import csv
import glob
import io
from pathlib import Path

import numpy as np

from bathtub_freq_compare import REPO, block
from bathtub_isi_shelf import prbs_pages
from bathtub_p1_figures import W_PS, panels, split
from monte_carlo_sweep_params import BASELINE, INK, INK2, MUTED, RAMP, SURFACE, _style_axes

OUT = REPO / "build" / "bathtub" / "v2"
PASSES = ("scan", "ceil", "wall", "rescan")
CODE = {"s": 0, "c": 1, "w": 2, "r": 3}
DEEP = ("ceil", "wall")
PAIR_OFF = 2              # 짝이 맞는 어긋남 0 - PAIR_OFF (쪽 끝 · 쪽 머리 몫)
FAR = 16                  # 옆 아닌 짝만 맞을 때 받으려면 옆 짝의 |어긋남| 이 이보다 커야 한다
OUTCOMES = ("one", "both", "far", "near", "none")   # 짝 고르기 결과 — 앞의 셋만 쓴다
CHUNK = 1_000_000         # _reads.csv 를 이만큼씩 읽는다 — 초심부는 스윕당 약 4,000만 행
WARN = "#c0392b"


def prbs_page(page, b=2048):
    """쪽 하나의 PRBS 비트 — flash_prbs15.v (bathtub_isi_shelf.prbs_pages 와 같은 생성기, 시드 {1, page[13:0]})."""
    out = np.empty(b, np.uint8)
    lfsr = 0x4000 | (page & 0x3FFF)
    for i in range(b):
        out[i] = lfsr >> 14
        lfsr = ((lfsr << 1) | ((lfsr >> 14) ^ (lfsr >> 13)) & 1) & 0x7FFF
    return out


def page_counts(page, b=2048):
    """(쪽 안 전이 수, 상승 수(쪽 끝 포함), 하강 수). 다음 쪽 첫 비트는 늘 1 이다 (시드 최상위 비트)."""
    x = prbs_page(page, b)
    up = int(((x[:-1] == 0) & (x[1:] == 1)).sum())
    dn = int(((x[:-1] == 1) & (x[1:] == 0)).sum())
    return up + dn, up + int(x[-1] == 0), dn


def selfcheck():
    """쪽 생성기를 v1 분석기(bathtub_isi_shelf)의 것과 맞대고, 알려진 수(쪽 0-111 하강 56,572)로 검산한다."""
    ref = prbs_pages(4, 2048)
    if any((prbs_page(p) != ref[p]).any() for p in range(4)):
        raise SystemExit("PRBS 생성기가 bathtub_isi_shelf.prbs_pages 와 다르다")
    falls = sum(page_counts(p)[2] for p in range(112))
    if falls != 56572:
        raise SystemExit(f"PRBS 검산 실패: 쪽 0-111 하강 {falls} != 56,572")


def read_main(path):
    p = Path(path)
    if not p.name.startswith("bathtub2_"):
        raise SystemExit(f"{p.name}: bathtub2_* 만 받는다 (v1 파일은 bathtub_analysis.py)")
    with open(p, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows or "pass" not in rows[0]:
        raise SystemExit(f"{p.name}: pass 열이 없다 — 욕조 v2 메인 CSV 가 아니다")
    return rows


def pick_pair(e, T, right):
    """읽기마다 「지금 비트」 정렬 c (1 · 2, 못 고르면 0) 와 결과 번호 (OUTCOMES 순서).
    e = (n, 3) 정렬별 총 오류, T = 쪽 안 전이 수, right = 덩어리 중심 오른쪽이면 True (옆 짝 = (1, 2))."""
    o1 = e[:, 0] + e[:, 1] - T                                   # 짝 (0, 1) — 「지금 비트」 = 1
    o2 = e[:, 1] + e[:, 2] - T                                   # 짝 (1, 2) — 「지금 비트」 = 2
    ok1 = (o1 >= 0) & (o1 <= PAIR_OFF)
    ok2 = (o2 >= 0) & (o2 <= PAIR_OFF)
    side, other = np.where(right, ok2, ok1), np.where(right, ok1, ok2)
    far = np.abs(np.where(right, o2, o1)) > FAR
    out = np.select([side & ~other, side & other, other & far, other], [0, 1, 2, 3], 4)
    c_side = np.where(right, 2, 1)
    c = np.select([out <= 1, out == 2], [c_side, 3 - c_side], 0)
    return c, out


def read_stats(reads_path, base_sector, n_steps, skip, center):
    """_reads.csv → (pass 번호 × n_steps + step) 행마다 [읽기, 먼저 온 상승, 상승 수, 먼저 온 하강, 하강 수, 결과별 읽기 5].
    skip = reads_gap 인 (pass 번호, step) — 그 읽기는 세지 않는다. center = 훑기 덩어리 중심 스텝 (옆 짝)."""
    acc = np.zeros((len(PASSES) * n_steps, 5 + len(OUTCOMES)), np.int64)
    cnt = np.zeros((0, 3), np.int64)                  # read_idx → (쪽 안 전이, 상승, 하강)
    tr = str.maketrans({"s": "0", "c": "1", "w": "2", "r": "3"})
    skip_keys = np.array(sorted(c * n_steps + s for c, s in skip), np.int64)
    with open(reads_path, encoding="utf-8") as fh:
        fh.readline()
        while True:
            lines = [ln for _, ln in zip(range(CHUNK), fh)]
            if not lines:
                break
            a = np.loadtxt(io.StringIO("".join(lines).translate(tr)), delimiter=",", dtype=np.int64, ndmin=2)
            key = a[:, 1] * n_steps + a[:, 0]
            keep = ~np.isin(key, skip_keys)
            a, key = a[keep], key[keep]
            if not len(a):
                continue
            idx = a[:, 2]
            if idx.max() >= len(cnt):
                cnt = np.array([page_counts(base_sector * 16 + i) for i in range(idx.max() + 1)], np.int64)
            T, R, F = cnt[idx, 0], cnt[idx, 1], cnt[idx, 2]
            e, e1 = a[:, 4:7], a[:, 7:10]
            right = (a[:, 0] - center + n_steps / 2) % n_steps - n_steps / 2 > 0
            c, out = pick_pair(e, T, right)
            one = c > 0
            rows = np.arange(len(a))
            cc = np.maximum(c, 1)
            up = np.where(one, e[rows, cc] - e1[rows, cc], 0)
            dn = np.where(one, e1[rows, cc], 0)
            vals = np.column_stack([np.ones(len(a), np.int64), up, np.where(one, R, 0), dn, np.where(one, F, 0),
                                    out[:, None] == np.arange(len(OUTCOMES))]).astype(np.int64)
            np.add.at(acc, key, vals)
    return acc


def step_table(rows, acc, n_steps):
    """메인 행 → 스텝 표 (그림 · CDF 용). 벽 집중 행(ceil · wall)이 있으면 그것, 없으면 scan 행."""
    bs = int(rows[0]["base_sector"])
    by = {(r["pass"], int(r["phase_step"])): r for r in rows}
    out = []
    for s in range(n_steps):
        r = next((by[(p, s)] for p in DEEP if (p, s) in by), None) or by.get(("scan", s))
        if r is None:
            continue
        n, b, e = int(r["n_reads"]), int(r["b_bits"]), int(r["bit_errors"])
        a = acc[PASSES.index(r["pass"]) * n_steps + s]
        gap = "reads_gap" in r["flags"].split(";")
        out.append({"phase_step": s, "pass": r["pass"], "n_reads": n, "bit_errors": e, "ber": e / (n * b),
                    "ber_upper": 3 / (n * b) if e == 0 else "", "reads_gap": int(gap),
                    "reads_paired": int(a[5:8].sum()), **{f"reads_{k}": int(a[5 + i]) for i, k in enumerate(OUTCOMES)},
                    "frac_rise": a[1] / a[2] if a[2] else "", "frac_fall": a[3] / a[4] if a[4] else ""})
    return bs, out


def edge_moments(x, F):
    """CDF 점 (x, F) → (평균, 폭, pdf 중점, pdf 높이). 이웃 점 사이 증가분을 중점에 둔다."""
    ok = ~np.isnan(F)
    x, F = x[ok], F[ok]
    if len(x) < 2:
        return np.nan, np.nan, np.zeros(0), np.zeros(0)
    mid, dF = (x[1:] + x[:-1]) / 2, np.diff(F)
    tot = dF.sum()
    mu = (mid * dF).sum() / tot
    return mu, np.sqrt(((mid - mu) ** 2 * dF).sum() / tot), mid, dF / np.diff(x)


def analyze(path):
    rows = read_main(path)
    n_steps = round(63e9 / float(rows[0]["f_sclk_hz"]))              # UI ÷ Δφ (Δφ = 10⁶/63 fs, VCO 고정) — 25MHz 2,520
    dphi = float(rows[0]["dphi_ps"])
    scan = np.zeros(n_steps, np.int64)
    for r in rows:
        if r["pass"] == "scan":
            scan[int(r["phase_step"])] = int(r["bit_errors"])
    if sum(r["pass"] == "scan" for r in rows) != n_steps:
        raise SystemExit(f"{Path(path).name}: scan 행이 {n_steps} 개가 아니다 (결측 금지 — 수정안 #4 §2.5)")
    first, length = block(scan)
    center = first + (length - 1) / 2
    skip = {(PASSES.index(r["pass"]), int(r["phase_step"])) for r in rows if "reads_gap" in r["flags"].split(";")}
    bs = int(rows[0]["base_sector"])
    acc = read_stats(str(path)[:-4] + "_reads.csv", bs, n_steps, skip, center)
    _, st = step_table(rows, acc, n_steps)
    for t in st:
        t["x_ps"] = ((t["phase_step"] - center + n_steps / 2) % n_steps - n_steps / 2) * dphi
    st.sort(key=lambda t: t["x_ps"])
    deep = [t for t in st if t["pass"] in DEEP]
    xs = np.array([t["x_ps"] for t in deep])
    if len(xs) and not np.allclose(np.diff(xs), dphi):
        print(f"  [주의] {Path(path).name}: 벽 집중 스텝이 이어져 있지 않다 — CDF 사이가 빈다")
    fr = np.array([t["frac_rise"] if t["frac_rise"] != "" else np.nan for t in deep], float)
    ff = np.array([t["frac_fall"] if t["frac_fall"] != "" else np.nan for t in deep], float)
    mr, wr, xr, pr = edge_moments(xs, fr)
    mf, wf, xf, pf = edge_moments(xs, ff)
    r0 = rows[0]
    summ = {"file": Path(path).name, "target": r0.get("target", ""), "uid": r0.get("uid", ""), "mode": r0["mode"],
            "flags": r0["flags"].replace("reads_gap", "").strip(";"), "f_sclk_hz": int(r0["f_sclk_hz"]), "base_sector": bs,
            "block_first": first, "block_steps": length, "floor_ps": (n_steps - length) * dphi,
            "deep_steps": len(deep), "gap_steps": len(skip),
            "reads_paired": int(sum(t["reads_paired"] for t in deep)),
            **{f"reads_{k}": int(sum(t[f"reads_{k}"] for t in deep)) for k in OUTCOMES},
            "mu_rise_ps": mr, "width_rise_ps": wr, "mu_fall_ps": mf, "width_fall_ps": wf, "dcd_ps": mf - mr}
    curves = {"x": xs, "fr": fr, "ff": ff, "pdf_r": (xr, pr), "pdf_f": (xf, pf)}
    return summ, st, curves, (n_steps, dphi, length)


def plot_p1(plt, name, st, geom, out_png):
    n_steps, dphi, length = geom
    ui = n_steps * dphi
    fig, al, ar = panels(plt, f"{name} — 욕조 v2 (끊긴 축, 한쪽 {W_PS:,.0f}ps)")
    x = np.array([t["x_ps"] for t in st])
    y = np.array([t["ber"] for t in st])
    up = np.array([t["ber_upper"] if t["ber_upper"] != "" else np.nan for t in st], float)
    deep = np.array([t["pass"] in DEEP for t in st])
    styles = ((deep, dict(color=RAMP[2], lw=2, marker="o", ms=3), "벽 집중 (천장 112 · 벽 N)"),
              (~deep, dict(color=MUTED, lw=0, marker=".", ms=4), "1회 훑기 — 깊이 다름"))
    for m, kw, lab in styles:
        nz = m & (y > 0)
        z = m & (y == 0)
        for ax, (px, py) in zip((al, ar), split(x[nz], y[nz], ui)):
            ax.plot(px, py, **kw)
        for ax, (px, py) in zip((al, ar), split(x[z], up[z], ui)):
            ax.plot(px, py, "v", color=kw["color"], ms=4, mfc="none")
        al.plot([], [], **kw, label=lab)
        al.plot([], [], "v", color=kw["color"], ms=4, mfc="none", label=f"{lab} — 0 errors, BER < 3/(N·B)")
    ymin = np.nanmin(np.r_[y[y > 0], up[~np.isnan(up)]])
    al.set_xlim(0, W_PS)
    ar.set_xlim(ui - W_PS, ui)
    al.set_ylim(ymin / 2, 1)
    leg = fig.legend(*al.get_legend_handles_labels(), frameon=False, fontsize=8, loc="lower center", ncol=2)
    for t in leg.get_texts():
        t.set_color(INK2)
    from matplotlib.patches import ConnectionPatch
    half = (length - 1) / 2 * dphi
    ya = ymin * 3
    xa, xb = min(half, W_PS), max(ui - half, ui - W_PS)
    fig.add_artist(ConnectionPatch(xyA=(xa, ya), coordsA=al.transData, xyB=(xb, ya), coordsB=ar.transData,
                                   arrowstyle="<->", color=INK2, lw=1.2))
    pa = fig.transFigure.inverted().transform(al.transData.transform((xa, ya)))
    pb = fig.transFigure.inverted().transform(ar.transData.transform((xb, ya)))
    fig.text((pa[0] + pb[0]) / 2, pa[1] + 0.015, f"바닥(훑기 오류 0) {(n_steps - length) * dphi:,.0f}ps", ha="center",
             va="bottom", color=INK, fontsize=9, bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec=BASELINE, lw=0.8))
    if len(x[deep]) and np.abs(x[deep]).max() > W_PS:
        fig.text(0.53, 0.5, f"잘림 — 벽 집중 구간이 W = {W_PS:,.0f}ps 를 넘는다 (최대 {np.abs(x[deep]).max():,.0f}ps)",
                 ha="center", va="center", color=INK, fontsize=9, bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=WARN, lw=1.5))
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_edges(plt, name, summ, cv, out_png):
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fig, (a1, a2) = plt.subplots(2, 1, sharex=True, figsize=(7.5, 6.4))
    for ax in (a1, a2):
        _style_axes(fig, ax)
    for key, pk, col, mk, lab, mu, w in (("fr", "pdf_r", RAMP[1], "o", "상승 (0 → 1)", summ["mu_rise_ps"], summ["width_rise_ps"]),
                                         ("ff", "pdf_f", INK2, "s", "하강 (1 → 0)", summ["mu_fall_ps"], summ["width_fall_ps"])):
        a1.plot(cv["x"], cv[key], "-" + mk, color=col, ms=3, lw=1.5, label=f"{lab} — 평균 {mu:,.1f}ps · 폭 {w:,.1f}ps")
        a2.plot(*cv[pk], "-" + mk, color=col, ms=3, lw=1.5, label=lab)
        for ax in (a1, a2):
            ax.axvline(mu, color=col, lw=0.8, ls="--")
    a1.set_ylabel("셔터보다 먼저 온 비율 (CDF)", color=INK2)
    a2.set_ylabel("pdf (1/ps)", color=INK2)
    a2.set_xlabel("위상 (ps) — 훑기 덩어리 중점 = 0", color=INK2)
    a1.set_title(f"{name} — 에지별 도착 분포 · DCD {summ['dcd_ps']:,.1f}ps", color=INK, fontsize=10)
    for ax in (a1, a2):
        leg = ax.legend(frameon=False, fontsize=8.5)
        for t in leg.get_texts():
            t.set_color(INK2)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def fmt(v):
    return f"{v:.6g}" if isinstance(v, float) else v


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: fmt(v) for k, v in r.items()} for r in rows)


def main(argv=None):
    ap = argparse.ArgumentParser(description="욕조 v2 분석 — 끊긴 축 · 에지별 CDF · pdf · DCD (build/bathtub/v2/)")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--outdir", type=Path, default=OUT)
    ap.add_argument("--no-plot", action="store_true", help="그림 없이 표만")
    args = ap.parse_args(argv)
    selfcheck()
    files = args.files or [Path(p) for p in sorted(glob.glob(str(REPO / "data" / "**" / "bathtub2_*.csv"), recursive=True))]
    files = [f for f in files if not f.name.endswith("_reads.csv")]
    args.outdir.mkdir(parents=True, exist_ok=True)
    if not args.no_plot:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    summs = []
    for f in files:
        if "_invalid" in f.name:
            print(f"  [건너뜀 — 무효 런] {f.name}")
            continue
        summ, st, cv, geom = analyze(f)
        stem = f.name[:-4]
        write_csv(args.outdir / f"{stem}_steps.csv", st)
        if not args.no_plot:
            plot_p1(plt, stem, st, geom, args.outdir / f"{stem}_p1.png")
            plot_edges(plt, stem, summ, cv, args.outdir / f"{stem}_edges.png")
        summs.append(summ)
        print(f"  {stem}: 상승 평균 {summ['mu_rise_ps']:,.1f}ps 폭 {summ['width_rise_ps']:,.1f}ps · 하강 평균 "
              f"{summ['mu_fall_ps']:,.1f}ps 폭 {summ['width_fall_ps']:,.1f}ps · DCD {summ['dcd_ps']:,.1f}ps · "
              f"짝 {summ['reads_paired']} (옆 하나 {summ['reads_one']} · 둘 → 옆 {summ['reads_both']} · 옆 아닌 하나 "
              f"{summ['reads_far']}) · 짝 없음 (옆 아닌 하나 · 옆 가까움 {summ['reads_near']} · 둘 다 안 맞음 {summ['reads_none']}) · "
              f"reads_gap {summ['gap_steps']} 스텝 · flags {summ['flags'] or '-'}")
    if summs:
        write_csv(args.outdir / "bathtub2_edges.csv", summs)
    print(f"출력: {args.outdir}/ — 파일 {len(summs)}")
    return summs


if __name__ == "__main__":
    main()
