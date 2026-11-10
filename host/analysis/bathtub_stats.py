# bathtub_stats.py — v1 25MHz 스윕 전부의 오류 블록 정렬 · 벽 모양 특징 · 칩별/체크포인트별 집계 · 마모 추세 (로그 55 피드백 2·4·5)
#
# 사용: uv run python host/analysis/bathtub_stats.py
#
# 입력: data/sweep_<chip>[_<UID>]_<UTC>.csv — 25MHz(2520 스텝) 런만. _reads · _invalid · loopback 은 건너뛴다
#       docs/results/data/wear/wear_endurance_<chip>_*.csv — mhz==25 행의 sweep_batch 로 런에 P/E cycle 을 붙인다.
#         sweep_batch 는 세션 로그 stamp 다 (wear_checkpoint_csv.py) — data/session_<chip>_<batch>.log 의
#         「VALID sweep_….csv」 가 그 스윕. 세션 로그가 없으면 스윕 파일 stamp 와 바로 맞춘다 (9월 표의 옛 방식)
# 출력: build/bathtub_stats/ — runs.csv · per_chip.csv · per_checkpoint.csv · 그림 PNG (칩 전체 추세는 뺐다 — 세션 안 추세는 bathtub_session_trend.py)
#
# 오류 블록 = 원형으로 이어진 bit_errors>0 스텝 덩어리 (위상 원점은 런마다 임의라 2519→0 을 넘을 수 있다).
# 블록이 한 개가 아니면 이상 런으로 빼고 화면에 알린다.
#   천장 = bit_errors >= 0.99 × 블록 최댓값 인 스텝. 벽 = 천장 바깥의 0 < BER < 0.99 × 천장 BER 스텝 (왼쪽 L · 오른쪽 R)
#   벽 거리 = BER 1e-4 교차와 1e-1 교차 사이 ps. 바깥(0 오류)에서 안쪽으로 걸어 처음 문턱을 넘는 두 이웃 스텝 사이를
#            log-선형 보간한다. 아래 이웃이 0 오류면(바닥에서 바로 문턱 위로 뛰면) 비운다
#   비대칭 = L - R (벽 스텝 수 · 벽 거리 둘 다)
#   L · R 은 덩어리 기준이다 (L = 위상이 낮은 쪽). 바닥을 가운데 둔 욕조 그림에서는 좌우가 뒤집힌다
# 정렬 = 블록 첫·끝 스텝의 중점을 0 ps 로 두고 ±31 스텝(63 스텝 = 1000 ps) 창. 그림에만 쓴다
# 추세 = 체크포인트(서로 다른 cycle) 5개 이상인 칩에서 런 단위 Spearman. p 는 순열 검정 (scipy 가 의존성에 없다)

import argparse
import csv
import glob
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from monte_carlo_sweep_params import BASELINE, INK, INK2, MUTED, RAMP, SURFACE, _style_axes

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "data"
WEAR = REPO / "docs" / "results" / "data" / "wear"
OUT = REPO / "build" / "bathtub_stats"

F_SCLK = 25_000_000
N_STEPS = 2520            # 25MHz UI 40,000ps / 15.873ps
HALF = 31                 # 정렬 창 ±31 스텝 = 1000ps
K_GAP = 5                 # 덩어리 안 0 틈이 이보다 짧으면 같은 덩어리 (로그 55 [D55-4] K)
CEIL_FRAC = 0.99
SHELF_LO, SHELF_HI = 0.3, 0.7   # 절반 높이 턱 = 천장의 30-70% (bathtub_freq_compare.py 의 선반과 같은 문턱)
THR_LO, THR_HI = 1e-4, 1e-1
N_PERM = 10_000           # Spearman 순열 검정 횟수 (seed 0 고정)
SAMPLE = "sweep_chip01_20260708T164931Z.csv"   # 확대 그림 런

NAME = re.compile(r"sweep_(chip\d+)_(?:([0-9A-F]{16})_)?(\d{8}T\d{6}Z)\.csv$")
FEATURES = ["span_ps", "ceil_width_ps", "ceil_bit_errors", "wall_L_steps", "wall_R_steps",
            "wall_L_1e4to1e1_ps", "wall_R_1e4to1e1_ps", "asym_steps", "asym_1e4to1e1_ps"]


def batch_sweeps():
    """{(chip, sweep_batch): 스윕 파일명} — 세션 로그의 VALID 줄, 세션 로그가 없으면 스윕 파일 stamp."""
    sess = {}
    for p in glob.glob(str(DATA / "session_*.log")):
        v = re.search(r"\bVALID (sweep_\S+\.csv)", Path(p).read_text(encoding="utf-8", errors="replace"))
        if v:
            sess[(Path(p).name.split("_")[1], Path(p).stem.rsplit("_", 1)[1])] = v[1]
    direct = {(m[1], m[3]): m[0] for m in (NAME.match(Path(f).name) for f in glob.glob(str(DATA / "sweep_*.csv"))) if m}
    return {**direct, **sess}


def cycle_map():
    """wear_endurance 표 → {스윕 파일명: cycle}. 못 찾은 행은 화면에 알린다."""
    sweeps = batch_sweeps()
    cyc = {}
    for f in sorted(glob.glob(str(WEAR / "wear_endurance_*.csv"))):
        chip = re.search(r"wear_endurance_(chip\d+)_", f)[1]
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["mhz"].strip() != "25" or not r["cycle"].strip():
                    continue
                b = r["sweep_batch"].strip()
                sw = sweeps.get((chip, b))
                if not sw:
                    print(f"  [cycle] {Path(f).name} cycle={r['cycle']} sweep_batch='{b}' — 스윕 파일 없음, 건너뜀")
                    continue
                c = int(r["cycle"])
                if sw in cyc and cyc[sw] != c:
                    raise SystemExit(f"{sw}: cycle {cyc[sw]} 와 {c} 충돌")
                cyc[sw] = c
    return cyc


def crossing(ber, pos, thr):
    """바깥 → 안쪽 순서의 (ber, pos) 에서 처음 thr 을 넘는 지점을 log-선형 보간. 못 풀면 None."""
    for k in range(1, len(ber)):
        if ber[k] >= thr:
            if ber[k] == thr:
                return pos[k]
            if ber[k - 1] <= 0:
                return None
            t = (np.log(thr) - np.log(ber[k - 1])) / (np.log(ber[k]) - np.log(ber[k - 1]))
            return pos[k - 1] + t * (pos[k] - pos[k - 1])
    return None


def wall_dist(ber, pos, dphi):
    lo, hi = crossing(ber, pos, THR_LO), crossing(ber, pos, THR_HI)
    return None if lo is None or hi is None else abs(hi - lo) * dphi


def analyze(path):
    """스윕 CSV 한 개 → (상태, 특징 dict). 상태 = 'ok' 또는 건너뜀/이상 사유."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if any(float(r["f_sclk_hz"]) != F_SCLK for r in rows):
        return "skip: f_sclk != 25MHz", None
    if len(rows) != N_STEPS:
        return f"skip: steps {len(rows)} != {N_STEPS}", None
    rows.sort(key=lambda r: int(r["phase_step"]))
    assert [int(r["phase_step"]) for r in rows] == list(range(N_STEPS)), path
    nbits = {int(r["n_reads"]) * int(r["b_bits"]) for r in rows}
    assert len(nbits) == 1, f"{path}: 스텝마다 n_reads×b_bits 가 다르다 {nbits}"
    nb = nbits.pop()
    dphi = float(rows[0]["dphi_ps"])
    e = np.array([int(r["bit_errors"]) for r in rows])
    nz = e > 0
    if not nz.any() or nz.all():
        return "anomalous: 오류 블록 없음", None
    # 덩어리 = 가장 긴 원형 0 오류 구간(바닥)의 여집합. 안쪽 0 틈이 K 미만이면 같은 덩어리 (로그 55 [D55-4])
    zs = np.flatnonzero(~nz & np.roll(nz, 1))           # 0 구간 시작 (원형)
    runs = []
    for z0 in zs:
        k = 0
        while not nz[(z0 + k) % N_STEPS]:
            k += 1
        runs.append((k, int(z0)))
    runs.sort(reverse=True)
    if len(runs) > 1 and runs[1][0] >= K_GAP:
        return f"anomalous: 블록 2개 이상 (안쪽 0 틈 {runs[1][0]}스텝)", None
    first, n = (runs[0][1] + runs[0][0]) % N_STEPS, N_STEPS - runs[0][0]
    idx = (first + np.arange(n)) % N_STEPS               # 블록을 펼친 좌표 0..n-1
    b = e[idx]
    ber = b / nb
    mx = int(b.max())
    ceil = np.flatnonzero(b >= CEIL_FRAC * mx)
    c0, c1 = int(ceil[0]), int(ceil[-1])
    ceil_ber = mx / nb
    wall = (ber > 0) & (ber < CEIL_FRAC * ceil_ber)
    # 벽 거리: 바깥 0 오류 스텝부터 첫 천장 스텝까지 (오른쪽은 거꾸로)
    lb = np.concatenate([[0.0], ber[:c0 + 1]])
    lp = np.arange(-1, c0 + 1)
    rb = np.concatenate([[0.0], ber[c1:][::-1]])
    rp = np.arange(n, c1 - 1, -1)
    wl, wr = int(wall[:c0].sum()), int(wall[c1 + 1:].sum())
    shelf = (ber > SHELF_LO * ceil_ber) & (ber < SHELF_HI * ceil_ber)
    dl, dr = wall_dist(lb, lp, dphi), wall_dist(rb, rp, dphi)
    # 정렬 창 — 중점(반 스텝일 수 있음)이 0ps
    mid = (n - 1) / 2
    k = np.arange(int(np.floor(mid)) - HALF, int(np.floor(mid)) + HALF + 1)
    f = {"n_bits_per_step": nb, "first_nz_step": first, "last_nz_step": int(idx[-1]),
         "span_ps": n * dphi, "ceil_width_ps": len(ceil) * dphi, "ceil_bit_errors": mx,
         "wall_L_steps": wl, "wall_R_steps": wr, "wall_L_1e4to1e1_ps": dl, "wall_R_1e4to1e1_ps": dr,
         "asym_steps": wl - wr, "asym_1e4to1e1_ps": None if dl is None or dr is None else dl - dr,
         "win_x": (k - mid) * dphi, "win_ber": e[(first + k) % N_STEPS] / nb, "trunc": n > 2 * HALF + 1,
         # 아래는 표에 안 나간다 — bathtub_p1_figures.py · bathtub_session_trend.py 가 쓴다
         "e": e, "dphi": dphi, "n_block": n,
         "shelf_L_steps": int(shelf[:c0].sum()), "shelf_R_steps": int(shelf[c1 + 1:].sum())}
    return "ok", f


def fmt(v):
    if v is None:
        return ""
    return f"{v:.3f}" if isinstance(v, float) else v


def stats(runs):
    """런 목록 → {feat_n, feat_mean, feat_sd, feat_min, feat_max}. 빈 값은 빼고 센다."""
    out = {}
    for ft in FEATURES:
        v = np.array([r[ft] for r in runs if r[ft] is not None], dtype=float)
        out[f"{ft}_n"] = len(v)
        out[f"{ft}_mean"] = v.mean() if len(v) else None
        out[f"{ft}_sd"] = v.std(ddof=1) if len(v) > 1 else None
        out[f"{ft}_min"] = v.min() if len(v) else None
        out[f"{ft}_max"] = v.max() if len(v) else None
    return out


def rank(a):
    """평균 순위 (동순위는 평균)."""
    o = np.argsort(a, kind="mergesort")
    r = np.empty(len(a))
    r[o] = np.arange(1, len(a) + 1)
    for u in np.unique(a):
        m = a == u
        r[m] = r[m].mean()
    return r


def spearman(x, y, rng):
    rx, ry = rank(np.asarray(x, float)), rank(np.asarray(y, float))
    if rx.std() == 0 or ry.std() == 0:
        return None, None
    rho = np.corrcoef(rx, ry)[0, 1]
    perm = np.array([np.corrcoef(rx, rng.permutation(ry))[0, 1] for _ in range(N_PERM)])
    p = (np.sum(np.abs(perm) >= abs(rho) - 1e-12) + 1) / (N_PERM + 1)
    return float(rho), float(p)


def write_csv(path, fields, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow({k: fmt(r.get(k)) for k in fields})


def plot_zoom(r, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    x, ber, fl = r["win_x"], r["win_ber"], 1 / r["n_bits_per_step"]
    z = ber == 0
    fig, axs = plt.subplots(1, 2, figsize=(11, 4.2))
    for ax in axs:
        _style_axes(fig, ax)
        ax.set_yscale("log")
        ax.set_ylim(fl / 2, 1)
        ax.set_ylabel("BER", color=INK2)
    a = axs[0]
    a.plot(x[~z], ber[~z], "-o", color=RAMP[1], lw=2, ms=4, label="BER")
    a.plot(x[z], np.full(z.sum(), fl), "x", color=MUTED, ms=5, label=f"0 errors (바닥 1/{r['n_bits_per_step']:,})")
    a.set_xlabel("블록 중점 기준 위상 (ps)", color=INK2)
    a.set_title(f"{r['chip']} {r['utc']} — 오류 블록 1000ps 창", color=INK, fontsize=10)
    a.legend(frameon=False, fontsize=8.5, loc="upper left")
    a = axs[1]
    left, right = x <= 0, x >= 0
    for sel, sgn, col, mk, lab in ((left, 1, RAMP[1], "o", "왼쪽 벽"), (right, -1, INK2, "s", "오른쪽 벽 (좌우 뒤집음)")):
        xs, bs = sgn * x[sel], ber[sel]
        nzs = bs > 0
        a.plot(xs[nzs], bs[nzs], "-" + mk, color=col, lw=2, ms=4, mfc="none" if sgn < 0 else col, label=lab)
        a.plot(xs[~nzs], np.full((~nzs).sum(), fl), "x", color=col, ms=5)
    a.plot([], [], "x", color=MUTED, label="0 errors (바닥)")
    a.set_xlim(x.min() - 10, 10)
    a.set_xlabel("블록 중점 기준 위상 (ps, 오른쪽 벽은 -x)", color=INK2)
    a.set_title("좌우 벽 겹침", color=INK, fontsize=10)
    a.legend(frameon=False, fontsize=8.5, loc="upper left")
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def plot_per_chip_mean(by_chip, out_png):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    chips = [c for c in sorted(by_chip) if len(by_chip[c]) >= 5]
    nc = 5
    nr = -(-len(chips) // nc)
    fig, axs = plt.subplots(nr, nc, figsize=(3.2 * nc, 2.6 * nr), sharex=True, sharey=True, squeeze=False)
    for ax in axs.flat[len(chips):]:
        ax.set_visible(False)
    for ax, c in zip(axs.flat, chips):
        _style_axes(fig, ax)
        rs = by_chip[c]
        for r in rs:
            y = np.where(r["win_ber"] > 0, r["win_ber"], np.nan)
            ax.plot(r["win_x"], y, color=RAMP[0], lw=0.6, alpha=0.35)
        xm = np.mean([r["win_x"] for r in rs], axis=0)
        ym = np.mean([r["win_ber"] for r in rs], axis=0)
        ax.plot(xm, np.where(ym > 0, ym, np.nan), color=RAMP[3], lw=2)
        ax.set_yscale("log")
        ax.set_ylim(1e-6, 1)
        ax.set_title(f"{c} (n={len(rs)})", color=INK, fontsize=9)
    for ax in axs[-1]:
        ax.set_xlabel("블록 중점 기준 (ps)", color=INK2, fontsize=8)
    for ax in axs[:, 0]:
        ax.set_ylabel("BER", color=INK2, fontsize=8)
    fig.suptitle("칩별 정렬 욕조 벽 — 옅은 선 = 런, 진한 선 = 평균 (0 오류 스텝은 안 그림)", color=INK, fontsize=10)
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main():
    argparse.ArgumentParser(description="v1 25MHz 스윕 전부 → 오류 블록 정렬 · 벽 특징 · 칩별/체크포인트별 집계 · 마모 추세 (build/bathtub_stats/)").parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    cyc = cycle_map()
    runs, why = [], defaultdict(list)
    for p in sorted(glob.glob(str(DATA / "sweep_*.csv"))):
        name = Path(p).name
        m = NAME.match(name)
        if not m:
            if not (name.endswith("_reads.csv") or "_invalid" in name or "loopback" in name):
                print(f"  [이름] {name} — 형식 밖, 건너뜀")
            continue
        st, f = analyze(p)
        if st != "ok":
            why[st].append(name)
            continue
        f.update(chip=m[1], uid=m[2] or "", utc=m[3], cycle=cyc.get(name), file=name)
        runs.append(f)

    print(f"사용 {len(runs)} 런 (cycle 붙음 {sum(r['cycle'] is not None for r in runs)})")
    for st, names in sorted(why.items()):
        print(f"{st}: {len(names)}")
        if st.startswith("anomalous"):
            for n in names:
                print(f"    {n}")
    long = sorted({r["chip"] for r in runs if r["trunc"]})
    print(f"창(63 스텝)보다 긴 블록: {sum(r['trunc'] for r in runs)} 런 ({' '.join(long)}) — 그림의 1000ps 창에 벽이 잘린다")
    print(f"매핑됐는데 사용 런에 없는 스윕: {sorted(set(cyc) - {r['file'] for r in runs})}")

    head = ["chip", "uid", "utc", "cycle", "file", "n_bits_per_step", "first_nz_step", "last_nz_step"] + FEATURES
    write_csv(OUT / "runs.csv", head, runs)

    by_chip = defaultdict(list)
    by_chip_cyc = defaultdict(lambda: defaultdict(list))
    for r in runs:
        by_chip[r["chip"]].append(r)
        if r["cycle"] is not None:
            by_chip_cyc[r["chip"]][r["cycle"]].append(r)
    agg = [f"{ft}_{s}" for ft in FEATURES for s in ("n", "mean", "sd", "min", "max")]
    write_csv(OUT / "per_chip.csv", ["chip", "n_runs"] + agg,
              [{"chip": c, "n_runs": len(by_chip[c]), **stats(by_chip[c])} for c in sorted(by_chip)])
    write_csv(OUT / "per_checkpoint.csv", ["chip", "cycle", "n_runs"] + agg,
              [{"chip": c, "cycle": cy, "n_runs": len(rs), **stats(rs)}
               for c in sorted(by_chip_cyc) for cy, rs in sorted(by_chip_cyc[c].items())])

    # 칩 전체 추세(trend.csv)는 뺐다 — 재장착 · 보드 이동 단차를 마모로 읽었다(로그 55 §9 R3). 세션 안 추세는 bathtub_session_trend.py

    sample = [r for r in runs if r["file"] == SAMPLE]
    if sample:
        plot_zoom(sample[0], OUT / f"zoom_{SAMPLE[len('sweep_'):-len('.csv')]}.png")
    plot_per_chip_mean(by_chip, OUT / "per_chip_mean.png")
    print(f"출력: {OUT.relative_to(REPO)}/ — 칩 {len(by_chip)} · 체크포인트 칩 {len(by_chip_cyc)}")


if __name__ == "__main__":
    main()
