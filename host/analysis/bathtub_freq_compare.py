#!/usr/bin/env python3
"""클럭 사다리(25 · 45 · 75MHz) 욕조 벽 비교 — 욕조 v2 의 주 주파수를 정하기 위한 재료 (로그 55).

사용: uv run python host/analysis/bathtub_freq_compare.py [--out build/bathtub_freq]

입력: data/sweep_chip*.csv 중 45 · 75MHz 런이 있는 칩의 전 런(25MHz 포함). _reads · _invalid 는 뺀다.
런마다 오류 덩어리(원형 연속 비영 스텝)를 찾고 좌우 벽을 바깥 → 안쪽 방향으로 펼쳐 잰다:
  - 벽 점 수: 0 < BER < 0.99 · 천장
  - 가우시안 적합: BER = C · Φ((x - μ)/σ) 을 probit 직선으로. 쓸 점 = 오류 5개 이상 · 천장의 95% 미만.
    점 3개 이상일 때만 R² 를 낸다 (2점 직선의 R² 는 언제나 1).
  - 벽 거리 1e-4 → 1e-1 (ps, 로그 선형 보간)
  - 눈 열림 비율 = 오류 0 스텝 / 전 스텝
  - 선반: 천장의 30-70% 인 스텝 수(양쪽 합). 45 · 75MHz 에서 천장의 절반 높이로 나타난다 — 상승 · 하강 에지 중 한쪽만 틀리는 구간
마모 전 · 뒤 짝: docs/results/data/wear/wear_endurance_*.csv 의 45 · 75MHz 행(cycle · sweep_batch) → data/session_<chip>_*_<batch>.log 의
  VALID 줄로 스윕 파일을 찾는다.
출력: runs.csv · summary.csv (칩 × 주파수 · 주파수 전체) · pairs.csv (마모 전 · 뒤) · walls_<chip>.png (주파수별 정렬 벽 겹침)
"""

import argparse
import csv
import glob
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams["font.family"] = "Noto Sans CJK JP"           # plot_wear_curves 와 같은 한글 글꼴

REPO = Path(__file__).resolve().parents[2]
ND = NormalDist()
MIN_CNT, CEIL_FRAC = 5, 0.95


def block(e):
    """덩어리 (첫 스텝, 길이) = 가장 긴 원형 0 오류 구간(바닥)의 여집합. 안쪽 0 틈은 크기와 무관하게 합친다 —
    v1 자료의 안쪽 틈은 최대 1스텝이다(로그 55 §6)."""
    n = len(e)
    z = e == 0
    best, cur, end = 0, 0, 0
    for i in range(2 * n):
        cur = cur + 1 if z[i % n] else 0
        if cur > best:
            best, end = cur, i
    best = min(best, n)
    first = (end + 1) % n
    return first, n - best


def wall_feats(ber, cnt, ceil, dphi):
    """바깥 → 안쪽 배열 하나의 벽 특징."""
    m_wall = (ber > 0) & (ber < 0.99 * ceil)
    m = (cnt >= MIN_CNT) & (ber < CEIL_FRAC * ceil)
    x = np.arange(len(ber)) * dphi
    out = {"pts": int(m_wall.sum()), "fit_pts": int(m.sum()), "sigma_ps": None, "r2": None, "d4to1_ps": None}
    if m.sum() >= 2:
        z = np.array([ND.inv_cdf(min(v / ceil, 1 - 1e-12)) for v in ber[m]])
        k, c = np.polyfit(x[m], z, 1)
        if k > 0:
            out["sigma_ps"] = 1 / k
            if m.sum() >= 3:
                pred = k * x[m] + c
                ss = ((z - z.mean()) ** 2).sum()
                out["r2"] = 1 - ((z - pred) ** 2).sum() / ss if ss > 0 else None
    lb = np.log10(np.where(ber > 0, ber, np.nan))
    def cross(t):
        for i in range(1, len(ber)):
            if ber[i - 1] < t <= ber[i] and ber[i - 1] > 0:
                return x[i - 1] + (np.log10(t) - lb[i - 1]) / (lb[i] - lb[i - 1]) * dphi
        return None
    a, b = cross(1e-4), cross(1e-1)
    if a is not None and b is not None:
        out["d4to1_ps"] = b - a
    return out


def analyze(path):
    rows = list(csv.DictReader(open(path, newline="", encoding="utf-8")))
    if len({r["n_reads"] for r in rows}) != 1:                # v2(훑기 · 벽 집중이 섞인 파일)는 이 비교 대상이 아니다
        return None
    e = np.array([int(r["bit_errors"]) for r in rows], float)
    nb = int(rows[0]["n_reads"]) * int(rows[0]["b_bits"])
    dphi = float(rows[0]["dphi_ps"])
    mhz = round(float(rows[0]["f_sclk_hz"]) / 1e6)
    if not e.any():
        return None
    n = len(e)
    first, length = block(e)
    idx = (first + np.arange(-12, length + 12)) % n       # 덩어리 + 바깥 12스텝씩
    seg_e = e[idx]
    ber = seg_e / nb
    ceil = ber.max()
    top = np.nonzero(ber >= 0.99 * ceil)[0]
    left = slice(0, top.min() + 1)
    L = wall_feats(ber[left], seg_e[left], ceil, dphi)
    R = wall_feats(ber[top.max():][::-1], seg_e[top.max():][::-1], ceil, dphi)
    mid = 12 + (length - 1) / 2
    shelf = int(((ber > 0.3 * ceil) & (ber < 0.7 * ceil)).sum())
    return {"file": Path(path).name, "chip": Path(path).name.split("_")[1], "mhz": mhz, "steps": n,
            "block_ps": length * dphi, "ceil_ps": len(top) * dphi, "shelf_ps": shelf * dphi, "eye_open": 1 - length / n,
            **{f"L_{k}": v for k, v in L.items()}, **{f"R_{k}": v for k, v in R.items()},
            "_x": (np.arange(len(ber)) - mid) * dphi, "_ber": ber}


def ladder_cycles():
    """스윕 파일명 → (cycle, note). 마모 표의 45 · 75MHz 행만."""
    out = {}
    for t in glob.glob(str(REPO / "docs" / "results" / "data" / "wear" / "wear_endurance_*.csv")):
        for r in csv.DictReader(open(t, newline="", encoding="utf-8")):
            if r["mhz"] == "25" or not r["sweep_batch"]:
                continue
            for log in glob.glob(str(REPO / "data" / f"session_*_{r['sweep_batch']}.log")):
                for line in open(log, encoding="utf-8"):
                    if " VALID sweep_" in line:
                        out[line.split(" VALID ")[1].split()[0]] = (int(r["cycle"]), r["note"][:40])
    return out


def med(v):
    v = [x for x in v if x is not None]
    return (float(np.median(v)), len(v)) if v else (None, 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(REPO / "build" / "bathtub_freq"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    files = [p for p in sorted(glob.glob(str(REPO / "data" / "sweep_chip*.csv"))) if not p.endswith(("_reads.csv", "_invalid.csv"))]
    runs = [r for r in (analyze(p) for p in files) if r]
    ladder = sorted({r["chip"] for r in runs if r["mhz"] != 25})
    runs = [r for r in runs if r["chip"] in ladder]
    keys = [k for k in runs[0] if not k.startswith("_")]
    with open(out / "runs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows({k: r[k] for k in keys} for r in runs)

    feats = ["block_ps", "ceil_ps", "shelf_ps", "eye_open", "L_pts", "R_pts", "L_sigma_ps", "R_sigma_ps", "L_r2", "R_r2", "L_d4to1_ps", "R_d4to1_ps"]
    groups = defaultdict(list)
    for r in runs:
        groups[(r["chip"], r["mhz"])].append(r)
        groups[("ALL", r["mhz"])].append(r)
    summ = []
    for (chip, mhz), rs in sorted(groups.items(), key=lambda t: (t[0][0] != "ALL", t[0])):
        row = {"chip": chip, "mhz": mhz, "n": len(rs)}
        for ft in feats:
            m, k = med([r[ft] for r in rs])
            row[ft] = "" if m is None else round(m, 4)
            row[ft + "_n"] = k
        summ.append(row)
    with open(out / "summary.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0]))
        w.writeheader()
        w.writerows(summ)

    cyc = ladder_cycles()
    pairs = []
    for r in runs:
        if r["file"] in cyc:
            c, note = cyc[r["file"]]
            pairs.append({"chip": r["chip"], "mhz": r["mhz"], "cycle": c, "note": note, "file": r["file"],
                          **{k: (round(r[k], 2) if isinstance(r[k], float) else r[k]) for k in
                             ("block_ps", "ceil_ps", "shelf_ps", "L_d4to1_ps", "R_d4to1_ps")}})
    pairs.sort(key=lambda p: (p["chip"], p["mhz"], p["cycle"], p["file"]))
    if pairs:
        with open(out / "pairs.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=list(pairs[0]))
            w.writeheader()
            w.writerows(pairs)
        print("마모 전 · 뒤 (클럭 사다리 행)")
        for p in pairs:
            print(f"  {p['chip']} {p['mhz']}MHz {p['cycle']:>6} 덩어리 {p['block_ps']} 천장 {p['ceil_ps']} 선반 {p['shelf_ps']}"
                  f" 벽 L {p['L_d4to1_ps']} R {p['R_d4to1_ps']} — {p['note']}")

    print("주파수 전체 (중앙값, 괄호 = 값이 있는 런 수)")
    for row in summ:
        if row["chip"] != "ALL":
            continue
        print(f"  {row['mhz']:>2}MHz n={row['n']:>3} 덩어리 {row['block_ps']}ps 천장 {row['ceil_ps']}ps 선반 {row['shelf_ps']}ps 눈 열림 {row['eye_open']}"
              f" | 벽 점 L {row['L_pts']} R {row['R_pts']} | σ L {row['L_sigma_ps']} R {row['R_sigma_ps']} ps"
              f" | R² L {row['L_r2']}({row['L_r2_n']}) R {row['R_r2']}({row['R_r2_n']})"
              f" | 1e-4→1e-1 L {row['L_d4to1_ps']}({row['L_d4to1_ps_n']}) R {row['R_d4to1_ps']}({row['R_d4to1_ps_n']}) ps")

    colors = {25: "#1f5aa6", 45: "#c76b00", 75: "#2a8a3e"}
    for chip in ladder:
        fig, ax = plt.subplots(figsize=(8, 4.5), dpi=140)
        for r in [r for r in runs if r["chip"] == chip]:
            ber = np.where(r["_ber"] > 0, r["_ber"], np.nan)
            ax.semilogy(r["_x"], ber, color=colors.get(r["mhz"], "gray"), alpha=0.35 if r["mhz"] == 25 else 0.9, lw=1)
        for mhz, c in colors.items():
            ax.plot([], [], color=c, label=f"{mhz} MHz")
        ax.set_xlabel("덩어리 중점 기준 (ps)")
        ax.set_ylabel("BER")
        ax.set_ylim(1e-6, 1)
        ax.set_title(f"{chip} — 클럭별 오류 덩어리 (0 오류 스텝은 안 그림)")
        ax.legend()
        fig.tight_layout()
        fig.savefig(out / f"walls_{chip}.png")
        plt.close(fig)
    print(f"출력: {out}/ — 사다리 칩 {len(ladder)}: {' · '.join(ladder)}")


if __name__ == "__main__":
    main()
