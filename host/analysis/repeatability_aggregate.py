# repeatability_aggregate.py — 반복 스윕 폭 집계 (런북 3 D6, 게재 4번)
#
# 사용: .venv/bin/python host/analysis/repeatability_aggregate.py <csv> <csv> ...
# 각 CSV의 width@θ(3종)를 bathtub_analysis와 동일 알고리즘으로 구해
# 평균±표준편차를 출력하고, 대표 곡선(첫 CSV) 1장에 에러바 요약을 표기한다.
# 산출: build/plots/bathtub_<target>_repeat<n>.png + 요약 stdout(그대로 로그·md에 인용)

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bathtub_analysis import (THETAS, load_sweep, circular_recenter, find_center,
                              edge_estimate, make_plot)


def widths_of(path):
    phis, n, b, errs, rwe, sq = load_sweep(path)
    ber = errs / (n * b)
    roll, (ber, errs, phis_idx) = circular_recenter(
        ber, [ber, errs, np.arange(len(ber))])
    phis = np.arange(len(ber)) * (phis[1] - phis[0])
    center = find_center(ber)
    floor_sub = 0.5 / (n * b)
    out = {}
    for th in THETAS:
        l = edge_estimate(ber[:, None], phis, center, th, floor_sub, "left")[0]
        r = edge_estimate(ber[:, None], phis, center, th, floor_sub, "right")[0]
        out[th] = r - l
    return phis, ber, n * b, out


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    if len(paths) < 2:
        raise SystemExit("usage: repeatability_aggregate.py <csv> <csv> ... (2개 이상)")

    per_run = []
    rep = None
    for p in paths:
        phis, ber, nb, w = widths_of(p)
        per_run.append(w)
        if rep is None:
            rep = (phis, ber, nb, p)
        print(f"{p.name}: " + "  ".join(f"w@{t:g}={w[t]:.1f}ps" for t in THETAS))

    print("\n== 집계 (n=%d) ==" % len(paths))
    summary = {}
    for t in THETAS:
        ws = np.array([w[t] for w in per_run])
        summary[t] = (ws.mean(), ws.std(ddof=1))
        print(f"  width@{t:g}: {ws.mean():.1f} ± {ws.std(ddof=1):.2f} ps"
              f"  (min {ws.min():.1f} / max {ws.max():.1f})")

    phis, ber, nb, p0 = rep
    center = find_center(ber)
    fl = 0.5 / nb
    edges = (edge_estimate(ber[:, None], phis, center, 1e-2, fl, "left")[0],
             edge_estimate(ber[:, None], phis, center, 1e-2, fl, "right")[0])
    m, s = summary[1e-2]
    target = p0.stem.split("_")[1]
    out = Path("build/plots") / f"bathtub_{target}_repeat{len(paths)}.png"
    # 제목은 ASCII로 — 게재 그림 폰트(DejaVu)에 한글 글리프 없음
    make_plot(phis, ber, nb, {}, out,
              f"Repeatability: {target} x{len(paths)}  "
              f"width@1e-2 = {m:.0f} +/- {s:.2f} ps  (rep: {p0.stem.split('_')[-1]})",
              edges=edges)
    print(f"\nplot: {out}")


if __name__ == "__main__":
    main()
