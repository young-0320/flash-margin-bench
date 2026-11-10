# bathtub_session_trend.py — 욕조 벽 모양 대 P/E cycle 추세를 「한 마모 세션 안」 에서만 낸다 (로그 55 §9 리뷰 R3 · [U55-2])
#
# 사용: uv run python host/analysis/bathtub_session_trend.py
#
# bathtub_stats.py 의 trend.csv 는 칩의 전 체크포인트를 한 줄로 이어, 재장착 · 보드 이동 단차(chip02 110k · chip06 20k ·
# chip12 10k)를 마모 추세로 읽었다. 여기서는 스윕을 마모 세션(run_wear 세션 번호 = 한 장착)에 묶고 세션마다 따로 낸다.
#
# 입력: data/sweep_*.csv 25MHz 런 — 특징은 bathtub_stats.analyze 그대로 (L · R 은 덩어리 기준)
#       docs/results/data/wear/wear_endurance_<chip>_*.csv · wear_pilot_<chip>_*.csv — mhz 25 · wear_session 이 있는 행.
#         sweep_batch → 스윕 파일은 bathtub_stats.batch_sweeps (세션 로그의 VALID 줄)
#         wear_session 이 빈 행(x=0 신품 newchip · 마모 뒤 재측정 · 블라인드 개봉 prep)은 장착이 달라 뺀다
#       data/wear/<세션>/checkpoints.csv — 승격 표가 아직 없는 칩 (EXTRA — chip08 의 11/5 세션)
# 단위 = 체크포인트 평균 — 세션 · cycle 이 같은 런의 평균 (런이 아니다)
# 특징: 천장 폭 · 벽별 1e-4 → 1e-1 거리 · 벽 스텝 수 · 비대칭(L - R) · 절반 높이 턱 유무(천장의 30-70% 스텝이 있으면 1)
# 추세 = 값이 있는 체크포인트가 MIN_CP 개 이상인 세션에서 cycle 대 특징의 Spearman, p 는 순열 검정 (bathtub_stats.spearman).
#   MIN_CP = 5 — 순열 검정의 최소 p 가 2/5! = 0.017 이라 p < 0.05 가 나올 수 있는 가장 작은 n
# 요약 판정(기계적): 특징마다 p < 0.05 인 세션 수 k 가 우연(세션마다 5%)으로 설명되는지 이항 꼬리 P(X ≥ k) 로 본다.
#   P < 0.05 면 「세션 안에서 변한다」, 아니면 「변한다는 증거 없음」. 방향(ρ 부호)이 세션마다 갈리는지도 함께 적는다
# 출력: build/bathtub/v1/ — session_checkpoints.csv · session_trend.csv · session_trend_summary.txt

import argparse
import csv
import glob
import re
from collections import defaultdict
from math import comb
from pathlib import Path

import numpy as np

from bathtub_stats import DATA, NAME, REPO, WEAR, analyze, batch_sweeps, spearman, write_csv

OUT = REPO / "build" / "bathtub" / "v1"
EXTRA = {"chip08": ["1793893689"]}      # 승격 표가 없는 칩의 마모 세션 폴더 (data/wear/)
MIN_CP = 5
ALPHA = 0.05
FEATS = ["ceil_width_ps", "wall_L_1e4to1e1_ps", "wall_R_1e4to1e1_ps", "wall_L_steps", "wall_R_steps",
         "asym_steps", "asym_1e4to1e1_ps", "shelf"]
LABEL = {"ceil_width_ps": "천장 폭 (ps)", "wall_L_1e4to1e1_ps": "L 벽 1e-4→1e-1 (ps)", "wall_R_1e4to1e1_ps": "R 벽 1e-4→1e-1 (ps)",
         "wall_L_steps": "L 벽 스텝 수", "wall_R_steps": "R 벽 스텝 수", "asym_steps": "비대칭 L-R (스텝)",
         "asym_1e4to1e1_ps": "비대칭 L-R (ps)", "shelf": "절반 높이 턱 유무"}


def session_map():
    """{스윕 파일명: (chip, wear_session, cycle)}. 못 찾은 행은 화면에 알린다."""
    sweeps = batch_sweeps()
    out = {}

    def put(sw, key):
        if out.setdefault(sw, key) != key:
            raise SystemExit(f"{sw}: {out[sw]} 와 {key} 충돌")

    for f in sorted(glob.glob(str(WEAR / "wear_endurance_*.csv")) + glob.glob(str(WEAR / "wear_pilot_*.csv"))):
        chip = re.search(r"wear_(?:endurance|pilot)_(chip\d+)_", f)[1]
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["mhz"].strip() != "25" or not r["wear_session"].strip() or not r["sweep_batch"].strip():
                    continue                              # sweep_batch 가 빈 행 = 결측 체크포인트
                sw = sweeps.get((chip, r["sweep_batch"].strip()))
                if not sw:
                    print(f"  [세션] {Path(f).name} cycle={r['cycle']} sweep_batch='{r['sweep_batch']}' — 스윕 파일 없음, 건너뜀")
                    continue
                put(sw, (chip, r["wear_session"].strip(), int(r["cycle"])))
    for chip, sessions in EXTRA.items():
        for s in sessions:
            with open(DATA / "wear" / s / "checkpoints.csv", newline="", encoding="utf-8") as fh:
                for r in csv.DictReader(fh):
                    if r["mhz"].strip() == "25" and r["sweep_csv"].strip():
                        put(r["sweep_csv"].strip(), (chip, r["session"].strip(), int(r["cycle"])))
    return out


def binom_tail(k, n, p):
    return sum(comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))


def main():
    argparse.ArgumentParser(description="욕조 벽 특징 대 P/E cycle 추세 — 한 마모 세션(한 장착) 안, 체크포인트 평균 단위 (build/bathtub/v1/)").parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    smap = session_map()
    cps = defaultdict(list)                                # (chip, session, cycle) → 런 특징 목록
    for sw, key in sorted(smap.items()):
        if not NAME.match(sw):
            print(f"  [이름] {sw} — 형식 밖, 건너뜀")
            continue
        st, f = analyze(DATA / sw)
        if st != "ok":
            print(f"  [{st}] {sw} — 건너뜀")
            continue
        f["shelf"] = int(f["shelf_L_steps"] + f["shelf_R_steps"] > 0)
        cps[key].append(f)

    cols = FEATS + ["shelf_L_steps", "shelf_R_steps"]
    rows, sess = [], defaultdict(list)
    for (chip, s, cy), rs in sorted(cps.items()):
        row = {"chip": chip, "session": s, "cycle": cy, "n_runs": len(rs)}
        for ft in cols:
            v = [r[ft] for r in rs if r[ft] is not None]
            row[ft] = float(np.mean(v)) if v else None
        rows.append(row)
        sess[(chip, s)].append(row)
    write_csv(OUT / "session_checkpoints.csv", ["chip", "session", "cycle", "n_runs"] + cols, rows)

    rng = np.random.default_rng(0)
    trend = []
    for (chip, s), cp in sorted(sess.items()):
        for ft in FEATS:
            pts = [(r["cycle"], r[ft]) for r in cp if r[ft] is not None]
            rho, p = spearman([q[0] for q in pts], [q[1] for q in pts], rng) if len(pts) >= MIN_CP else (None, None)
            trend.append({"chip": chip, "session": s, "feature": ft, "n_checkpoints": len(pts),
                          "cycle_min": min(q[0] for q in pts) if pts else None, "cycle_max": max(q[0] for q in pts) if pts else None,
                          "rho": rho, "p": p,
                          "value_min": min(q[1] for q in pts) if pts else None, "value_max": max(q[1] for q in pts) if pts else None})
    write_csv(OUT / "session_trend.csv", ["chip", "session", "feature", "n_checkpoints", "cycle_min", "cycle_max", "rho", "p",
                                          "value_min", "value_max"], trend)

    big = {k: v for k, v in sess.items() if len(v) >= MIN_CP}
    L = [f"세션 안 추세 — 세션 {len(sess)}개(칩 {len({k[0] for k in sess})}) 중 체크포인트 {MIN_CP}개 이상 {len(big)}개(칩 {len({k[0] for k in big})}), "
         f"체크포인트 {sum(len(v) for v in sess.values())}개 · 런 {sum(len(v) for v in cps.values())}개",
         f"단위 = 체크포인트 평균 · Spearman(cycle, 특징) · p 는 순열 검정 · 유의 = p < {ALPHA}",
         "L · R 은 덩어리 기준 (L = 위상이 낮은 쪽)", ""]
    for ft in FEATS:
        t = [r for r in trend if r["feature"] == ft and r["rho"] is not None]
        same = sum(r["feature"] == ft and r["n_checkpoints"] >= MIN_CP and r["rho"] is None for r in trend)
        if not t:
            L.append(f"{LABEL[ft]}: 검정한 세션 없음 (값이 세션 안에서 일정 {same}개)")
            continue
        sig = [r for r in t if r["p"] < ALPHA]
        up, dn = sum(r["rho"] > 0 for r in sig), sum(r["rho"] < 0 for r in sig)
        pos = sum(r["rho"] > 0 for r in t)
        tail = binom_tail(len(sig), len(t), ALPHA)
        rng_med = float(np.median([r["value_max"] - r["value_min"] for r in t]))
        L.append(f"{LABEL[ft]}: {'세션 안에서 변한다' if tail < ALPHA else '변한다는 증거 없음'} — 유의 {len(sig)}/{len(t)} 세션 (증가 {up} · 감소 {dn}, "
                 f"우연 기대 {ALPHA * len(t):.1f}, 이항 꼬리 P = {tail:.3g}) · ρ 중앙값 {np.median([r['rho'] for r in t]):+.2f} "
                 f"(ρ > 0 {pos} · ρ < 0 {len(t) - pos}) · 세션 안 변동폭 중앙값 {rng_med:.1f}"
                 + (f" · 값이 일정해 뺀 세션 {same}" if same else ""))
        for r in sig:
            L.append(f"    {r['chip']} {r['session']} ({r['cycle_min']:,}-{r['cycle_max']:,}, n={r['n_checkpoints']}) ρ {r['rho']:+.2f} p {r['p']:.4f} "
                     f"· 값 {r['value_min']:.1f} - {r['value_max']:.1f}")
    (OUT / "session_trend_summary.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"출력: {OUT.relative_to(REPO)}/ — session_checkpoints.csv · session_trend.csv · session_trend_summary.txt")


if __name__ == "__main__":
    main()
