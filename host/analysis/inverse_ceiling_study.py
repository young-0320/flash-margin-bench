# inverse_ceiling_study.py — v4.3 상한 근처 점 추정 처리 후보(v4.3.0-v4.3.6)를 같은 LOCO 점에서 비교한다 (로그 52 [U52-8])
#
# 사용: uv run python host/analysis/inverse_ceiling_study.py [--reps 20] [--out build/inverse/ceiling/study.md]
#
# 후보 (모두 v4.3 6장 판 교정 · ρ 등록값 · 관측 rows P5 · 무리 경계 40ms 그대로, 다른 것은 아래 한 가지씩):
#   v4.3.0  기준 — 지지 1-100k · 평평한 사전 · 대표값 사후 중앙값 (현행)
#   v4.3.1  (라) 대표값 MAP
#   v4.3.2       대표값 사후 평균
#   v4.3.3  (다) 대표값 하한 분위수 q16 (「적어도」 — 68% 단측)
#   v4.3.4  (마) 상한 규칙 — P(x > 90k) ≥ 0.5 이면 대표값 95,000(「정격 끝 근처 90-100k」), 아니면 중앙값
#   v4.3.5  (가) 지지 1-200k · 평평한 사전 · 대표값 min(중앙값, 100k)
#   v4.3.6       지지 1-100k · 로그 균등 사전(척도 불변) · 대표값 중앙값
#
# 채점 (결과를 보기 전에 정했다 — 로그 52 §15):
#   ① 분포 — 로그 눈금 CRPS 의 평균(작을수록 좋음). CRPS 는 예측 분포 전체를 채점하는 적정 점수 규칙(proper scoring rule)이라
#      지지 · 사전을 바꾼 후보(v4.3.5 · 6)를 공정하게 가른다. 대표값만 바꾼 후보(1-4)는 분포가 v4.3.0 과 같아 CRPS 도 같다
#   ② 점 추정 — |ln(추정/정답)| 의 평균(배율 오차). 이 손실의 베이즈 최적 대표값은 사후 중앙값이므로 v4.3.0 이 이론상 기준점이다
#   ③ 보정 — 68% · 95% HPD 포함률(합격 띠 106점: 68% 63-81 · 95% 97-105)과 68% 폭. 대표값만 바꾼 후보는 구간이 v4.3.0 과 같다
#   ④ 구간별 치우침 — 정답 구간(≤3k · 3-20k · 20-50k · 50-100k)마다 추정/정답 중앙값. 상한 문제의 직접 지표
#   선택: ① 로 분포 후보를 고르고(95% 띠 합격이 조건), 그 분포 위에서 ② 가 가장 작은 대표값. ② 의 차가 0.01 안이면 ④ 의 최대 |ln 치우침| 이 작은 쪽

import argparse
import math
import random
import statistics as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wear_inverse as wi  # noqa: E402

BUCKETS = ((0, 3_000, "≤3k"), (3_000, 20_000, "3-20k"), (20_000, 50_000, "20-50k"), (50_000, 100_000, "50-100k"))


def cdf_items(post):
    acc, out = 0.0, []
    for b in sorted(post):
        acc += post[b]
        out.append((b, acc))
    return out


def quantile(post, q):
    for b, acc in cdf_items(post):
        if acc >= q:
            return b + 499.5
    return max(post) + 499.5


def crps_log(post, x):
    """로그 눈금 CRPS — ∫ (F(z) − 1{z ≥ ln x})² dz, 1k 구간을 계단 CDF 로."""
    items = cdf_items(post)
    lx, tot, prev_edge, prev_f = math.log(x), 0.0, math.log(1), 0.0
    for b, acc in items:
        edge = math.log(b + 999)
        lo, hi = prev_edge, edge
        if hi > lo:                                      # 이 구간 [lo, hi) 에서 F = prev_f
            if lx <= lo:
                tot += (prev_f - 1) ** 2 * (hi - lo)
            elif lx >= hi:
                tot += prev_f ** 2 * (hi - lo)
            else:
                tot += prev_f ** 2 * (lx - lo) + (prev_f - 1) ** 2 * (hi - lx)
        prev_edge, prev_f = edge, acc
    if lx > prev_edge:                                   # 지지 끝 너머 정답 (일어나지 않음 — 정답 ≤ 100k ≤ 지지)
        tot += (lx - prev_edge) * 0.0
    return tot


def estimates(post, support):
    med = quantile(post, 0.5)
    mp = max(post, key=post.get) + 499.5
    mean = sum((b + 499.5) * p for b, p in post.items())
    q16 = quantile(post, 0.16)
    p90 = sum(p for b, p in post.items() if b > 90_000)
    rule = 95_000.0 if p90 >= 0.5 else med
    return {"median": min(med, 100_000) if support > 100_000 else med, "map": mp, "mean": mean, "q16": q16, "rule": rule}


VARIANTS = (("v4.3.0", "중앙값 (기준)", 100_000, None, "median"),
            ("v4.3.1", "MAP", 100_000, None, "map"),
            ("v4.3.2", "사후 평균", 100_000, None, "mean"),
            ("v4.3.3", "하한 q16", 100_000, None, "q16"),
            ("v4.3.4", "상한 규칙 (P(x>90k)≥0.5 → 95k)", 100_000, None, "rule"),
            ("v4.3.5", "지지 200k · 중앙값(100k 에서 자름)", 200_000, None, "median"),
            ("v4.3.6", "로그 균등 사전 · 중앙값", 100_000, "log", "median"))


def run(reps, seed=0):
    curves, fresh = wi.load_curves(), wi.load_fresh()
    arows = {c: wi.ARows.load(c) for c in curves}
    runs = {}
    for support, prior in {(v[2], v[3]) for v in VARIANTS}:
        rows, _ = wi.loco_study(curves, fresh, "ratio", 40_000, None, "rows", 5, seed, reps, 0, arows,
                                support=support, prior=prior, keep_post=True)
        runs[(support, prior)] = rows
    return runs


def summarize(runs):
    res = []
    for name, label, support, prior, est in VARIANTS:
        rows = runs[(support, prior)]
        e = [estimates(r["post"], support)[est] for r in rows]
        x = [r["x"] for r in rows]
        ln = [abs(math.log(a / b)) for a, b in zip(e, x)]
        crps = [crps_log(r["post"], r["x"]) for r in rows]
        buckets = {}
        for (lo, hi, lab) in BUCKETS:
            idx = [i for i, xx in enumerate(x) if lo < xx <= hi]
            buckets[lab] = (st.median(e[i] / x[i] for i in idx), sum(ln[i] for i in idx) / len(idx))
        res.append({"name": name, "label": label, "n": len(rows), "pts": len({(r["chip"], r["x"]) for r in rows}),
                    "crps": sum(crps) / len(crps), "ln_mean": sum(ln) / len(ln), "ln_med": st.median(ln),
                    "in68": sum(r["in68"] for r in rows) / len(rows), "in95": sum(r["in95"] for r in rows) / len(rows),
                    "w68": st.median(sum(min(z, 100_000) - a + 1 for a, z in r["h68"] if a <= 100_000) for r in rows),
                    "bias": st.median(a / b for a, b in zip(e, x)), "buckets": buckets,
                    "worst": max(abs(math.log(v[0])) for v in buckets.values())})
    return res


def render(res):
    out = ["| 후보 | 내용 | CRPS(log) | 평균 \\|ln(추정/정답)\\| | 중앙 \\|ln\\| | 68% | 95% | 68% 폭 | 추정/정답 | 최대 구간 치우침 \\|ln\\| |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in res:
        out.append(f"| {r['name']} | {r['label']} | {r['crps']:.4f} | {r['ln_mean']:.3f} | {r['ln_med']:.3f} | {r['in68']:.1%} | {r['in95']:.1%} | "
                   f"{r['w68']:,.0f} | {r['bias']:.2f} | {r['worst']:.3f} |")
    out += ["", "| 후보 | " + " | ".join(f"{lab} 추정/정답 · 평균 |ln|" for _, _, lab in BUCKETS) + " |", "|---|" + "---|" * len(BUCKETS)]
    for r in res:
        out.append(f"| {r['name']} | " + " | ".join(f"{r['buckets'][lab][0]:.2f} · {r['buckets'][lab][1]:.3f}" for _, _, lab in BUCKETS) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reps", type=int, default=20)
    ap.add_argument("--out")
    a = ap.parse_args()
    md = render(summarize(run(a.reps)))
    print(md)
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(md + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
