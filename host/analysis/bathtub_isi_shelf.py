# bathtub_isi_shelf.py — 기존 v1 원본으로 「주파수에 따른 ISI 선반」 을 본다: 선반의 오류 수가 PRBS 의 어느 이력 부류와 맞는가
#                        (로그 55 [D55-12] · §7 추기 · 개념 16 「이 계수기가 못 하는 것」)
#
# 사용: uv run python host/analysis/bathtub_isi_shelf.py
#
# 입력: data/sweep_chip*.csv + 짝 _reads.csv (계약 §6) — 25 · 45 · 75MHz 전 런. _invalid 는 뺀다
# 선반 스텝 = 덩어리 안에서 BER 이 천장의 30-70% 인 스텝 (bathtub_freq_compare.py 의 선반과 같은 문턱).
#   L = 천장보다 위상이 낮은 쪽, R = 높은 쪽 (덩어리 기준 — 로그 55 · 개념 16 의 왼쪽 · 오른쪽)
#   25MHz 는 선반이 아니라 가파른 벽의 중턱 한 점이 이 문턱에 걸리는 일이 흔하다 — 부류와 맞는지로 가린다
# PRBS = PRBS-15, x^15+x^14+1, 시드 {1, page[13:0]}, dout = lfsr[14] 뒤 시프트 (flash_prbs15.v · flash_prep.c 와 같다).
#   읽기 i = 쪽 i, 읽기 한 번 = b_bits(2,048) 비트
# 부류 = 전이 자리의 (앞 이력, 전이 방향):
#   3비트 「a b c」 = 앞앞 비트 a, b → c 전이 (b ≠ c). c = 1 이면 상승, 0 이면 하강. 4비트 「z a b c」 는 이력 한 비트 더
#   쪽 안 = 세 · 네 비트가 다 그 쪽 안에 있는 전이만 센다
#   +쪽 경계 = 쪽 안 + 쪽 머리 · 끝의 전이. 선(MISO)을 [앞 상태, 쪽 2,048비트, 다음 쪽 첫 비트] 로 본다:
#     쪽 끝 상승 — 마지막 SCLK 하강에 칩이 다음 쪽 첫 비트(1)를 내놓는다 (flash_spi_ctrl.v: 프레임당 SCLK b_bits + 40).
#                  쪽 마지막 비트가 0 이면 상승이고 이력은 그 앞 비트다
#     쪽 머리 하강 — 첫 비트 1 → 둘째 비트 0. 이력은 데이터 앞의 선 상태: 읽기 0 은 0(쉬던 선), 읽기 1 이후는 1(앞 프레임이
#                  끝에 내놓은 1 이 남는다). 이 「앞 상태」 는 75MHz 실측에서 유도한 모형이다 — R 선반이 읽기 0 만 빼고
#                  읽기마다 정확히 +1. 프레임 간격이 긴 낮은 주파수에서도 맞는지는 확인하지 못했다
#   4비트 부류는 쪽 안만 센다
# 맞춤 = 선반 스텝의 bit_errors 와 부류별 개수 합(읽은 쪽 0..n_reads-1)이 가장 가까운 부류.
#   exact = 합이 같다 · near = 차이가 n_reads 이하(읽기당 평균 1개 이내) · far = 그 밖(부류 선반이 아니라 벽 중턱)
#   reads_exact = 그 부류의 쪽별 개수와 읽기별 err_count 가 같은 읽기 수 — 합이 우연히 맞은 것과 가린다
# 시작할 때 PRBS 생성기를 알려진 수로 검산한다 (selfcheck) — 틀리면 멈춘다
# 출력: build/bathtub/v1/ — isi_shelf_steps.csv (선반 스텝마다) · isi_shelf_runs.csv (런 × 쪽) · isi_shelf_summary.txt
# 같은 칩이라도 런마다 배선이 다를 수 있다 (chip07 은 10/19 에 점퍼선 교체) — 요약은 런 단위로 적고 런끼리 합치지 않는다

import argparse
import csv
import glob
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from bathtub_freq_compare import REPO, block

OUT = REPO / "build" / "bathtub" / "v1"
SHELF_LO, SHELF_HI = 0.3, 0.7
CEIL_FRAC = 0.99


def prbs_pages(n, b):
    """쪽 0..n-1 의 PRBS 비트 (n, b) — flash_prbs15.v: dout = lfsr[14], 뒤에 {lfsr[13:0], lfsr[14]^lfsr[13]}."""
    out = np.empty((n, b), np.uint8)
    for p in range(n):
        lfsr = 0x4000 | (p & 0x3FFF)
        for i in range(b):
            out[p, i] = lfsr >> 14
            lfsr = ((lfsr << 1) | ((lfsr >> 14) ^ (lfsr >> 13)) & 1) & 0x7FFF
    return out


def name(pat):
    return f"「{' '.join(map(str, pat))}」 {'상승' if pat[-1] else '하강'}"


def candidates(x):
    """쪽 비트 (n, b) → [(부류 이름, 읽기별 개수 (n,))]. 3비트 쪽 안 · 3비트 +쪽 경계 · 4비트 쪽 안."""
    n = len(x)
    inpage = {}
    for a in (0, 1):
        for b in (0, 1):
            inpage[(a, b, 1 - b)] = ((x[:, :-2] == a) & (x[:, 1:-1] == b) & (x[:, 2:] == 1 - b)).sum(1)
    edge = {k: np.zeros(n, int) for k in inpage}
    pre = np.ones(n, int)
    pre[0] = 0                                             # 데이터 앞의 선 상태 (머리말 「쪽 머리 하강」)
    for r in range(n):
        if x[r, -1] == 0:                                  # 쪽 끝 상승: 마지막 비트 0 → 다음 쪽 첫 비트 1
            edge[(int(x[r, -2]), 0, 1)][r] += 1
        if x[r, 0] == 1 and x[r, 1] == 0:                  # 쪽 머리 하강
            edge[(int(pre[r]), 1, 0)][r] += 1
    out = [(name(k), v) for k, v in inpage.items()]
    out += [(name(k) + " +쪽 경계", inpage[k] + edge[k]) for k in inpage if edge[k].any()]
    for z in (0, 1):
        for a in (0, 1):
            for b in (0, 1):
                out.append((name((z, a, b, 1 - b)),
                            ((x[:, :-3] == z) & (x[:, 1:-2] == a) & (x[:, 2:-1] == b) & (x[:, 3:] == 1 - b)).sum(1)))
    return out


def falls(x):
    """쪽 안 하강 전이 수 (읽기별) — 쪽 머리 하강 포함. 천장 오류 수와 맞대는 값."""
    return ((x[:, :-1] == 1) & (x[:, 1:] == 0)).sum(1)


def selfcheck():
    """PRBS 생성기 검산 — 로그 55 · 개념 16 에 적힌 수."""
    x = prbs_pages(112, 2048)
    c = dict(candidates(x))
    got = {"하강 전이 112쪽 (25MHz 천장)": int(falls(x).sum()), "하강 전이 100쪽 (chip01 7/8 천장)": int(falls(x[:100]).sum()),
           "「1 0 1」 상승 112쪽": int(c["「1 0 1」 상승"].sum()), "「1 1 0」 하강 112쪽": int(c["「1 1 0」 하강"].sum())}
    want = {"하강 전이 112쪽 (25MHz 천장)": 56572, "하강 전이 100쪽 (chip01 7/8 천장)": 50416,
            "「1 0 1」 상승 112쪽": 27840, "「1 1 0」 하강 112쪽": 28008}
    if got != want:
        raise SystemExit(f"PRBS 생성기 검산 실패: {got} != {want}")
    return got


def reads_matrix(path, n_steps, n_reads):
    """_reads.csv → (n_steps, n_reads) err_count. 없는 행은 0."""
    a = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.int64, ndmin=2)
    m = np.zeros((n_steps, n_reads), np.int64)
    m[a[:, 0], a[:, 1]] = a[:, 2]
    return m


def analyze(path, cache):
    """스윕 한 개 → (런 dict, 선반 스텝 행 목록). v2 파일(n_reads 가 섞임)은 None."""
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if len({r["n_reads"] for r in rows}) != 1:
        return None
    rows.sort(key=lambda r: int(r["phase_step"]))
    e = np.array([int(r["bit_errors"]) for r in rows])
    n, nr, bb = len(e), int(rows[0]["n_reads"]), int(rows[0]["b_bits"])
    dphi, mhz = float(rows[0]["dphi_ps"]), round(float(rows[0]["f_sclk_hz"]) / 1e6)
    if not e.any():
        return None
    if (nr, bb) not in cache:
        x = prbs_pages(nr, bb)
        cache[(nr, bb)] = (candidates(x), int(falls(x).sum()))
    cands, n_falls = cache[(nr, bb)]
    first, length = block(e)
    idx = (first + np.arange(length)) % n
    b = e[idx]
    ceil = int(b.max())
    top = np.flatnonzero(b >= CEIL_FRAC * ceil)
    shelf = np.flatnonzero((b > SHELF_LO * ceil) & (b < SHELF_HI * ceil))
    name_ = Path(path).name
    run = {"file": name_, "chip": name_.split("_")[1], "utc": name_[:-4].rsplit("_", 1)[1], "mhz": mhz, "n_reads": nr,
           "block_ps": length * dphi, "ceil_ps": len(top) * dphi, "ceil_errors": ceil, "ceil_is_falls": int(ceil == n_falls),
           "dphi": dphi}
    steps = []
    if len(shelf):
        m = reads_matrix(path[:-4] + "_reads.csv", n, nr)
        for k in shelf:
            side = "L" if k < top[0] else "R" if k > top[-1] else None
            if side is None:                               # 천장 안쪽이 꺼진 스텝 — 벽이 아니다
                continue
            s, err = int(idx[k]), int(b[k])
            vec = m[s]
            if vec.sum() != err:
                raise SystemExit(f"{name_} step {s}: Σ err_count {vec.sum()} != bit_errors {err} (R8)")
            cls, cv = min(cands, key=lambda c: abs(int(c[1].sum()) - err))
            diff = err - int(cv.sum())
            steps.append({"file": name_, "chip": run["chip"], "utc": run["utc"], "mhz": mhz, "side": side, "phase_step": s,
                          "from_ceiling_steps": int(top[0] - k if side == "L" else k - top[-1]), "bit_errors": err,
                          "frac_of_ceiling": err / ceil, "class": cls, "class_count": int(cv.sum()), "diff": diff,
                          "match": "exact" if diff == 0 else "near" if abs(diff) <= nr else "far",
                          "reads_exact": int((vec == cv).sum()), "n_reads": nr})
    return run, steps


def side_rows(run, steps):
    """런 → 쪽(L · R)별 요약 행."""
    out = []
    for side in "LR":
        ss = [s for s in steps if s["side"] == side]
        hit = [s for s in ss if s["match"] != "far"]
        tally = Counter(s["class"] for s in hit)
        exact = Counter(s["class"] for s in hit if s["match"] == "exact")
        base = Counter(s["class"].split(" +")[0] for s in hit)
        out.append({**{k: run[k] for k in ("file", "chip", "utc", "mhz", "n_reads", "block_ps", "ceil_ps", "ceil_errors", "ceil_is_falls")},
                    "side": side, "shelf_steps": len(ss), "shelf_ps": len(ss) * run["dphi"],
                    "match_steps": len(hit), "match_ps": len(hit) * run["dphi"], "exact_steps": sum(exact.values()),
                    "main_class": base.most_common(1)[0][0] if base else "",
                    "classes": " · ".join(f"{c} ×{k} (exact {exact[c]})" for c, k in tally.most_common())})
    return out


def fmt(v):
    return f"{v:.3f}" if isinstance(v, float) else v


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows({k: fmt(v) for k, v in r.items()} for r in rows)


def main():
    argparse.ArgumentParser(description="v1 스윕 원본의 선반(천장의 30-70%) 오류 수를 PRBS 이력 부류 개수와 맞춘다 — 주파수 · 쪽(L · R)별 (build/bathtub/v1/)").parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    chk = selfcheck()
    cache, runs, steps, sides = {}, [], [], []
    for p in sorted(glob.glob(str(REPO / "data" / "sweep_chip*.csv"))):
        if p.endswith("_reads.csv") or "_invalid" in p:
            continue
        r = analyze(p, cache)
        if r is None:
            print(f"  [건너뜀] {Path(p).name}")
            continue
        runs.append(r[0])
        steps += r[1]
        sides += side_rows(*r)
    write_csv(OUT / "isi_shelf_steps.csv", steps)
    write_csv(OUT / "isi_shelf_runs.csv", sides)

    L = ["PRBS 생성기 검산 통과 — " + " · ".join(f"{k} {v:,}" for k, v in chk.items()),
         "L · R 은 덩어리 기준 (L = 천장보다 위상이 낮은 쪽). exact = 오류 수 = 부류 개수 · near = 차이 ≤ n_reads · far = 벽 중턱", ""]
    for mhz in sorted({r["mhz"] for r in runs}):
        rs = [r for r in runs if r["mhz"] == mhz]
        L.append(f"{mhz}MHz 천장 오류 수 = 하강 전이 수(쪽 머리 포함): {sum(r['ceil_is_falls'] for r in rs)}/{len(rs)} 런")
    for mhz in sorted({r["mhz"] for r in runs if r["mhz"] != 25}, reverse=True):
        L += ["", f"== {mhz}MHz — 런마다 (선반 = 30-70% 스텝 폭, 괄호 = 그중 부류와 맞은 폭) =="]
        ss = [s for s in sides if s["mhz"] == mhz]
        for a, b in zip(ss[0::2], ss[1::2]):
            L.append(f"  {a['chip']} {a['utc']}  L {a['shelf_ps']:6.0f}ps ({a['match_ps']:4.0f})  R {b['shelf_ps']:6.0f}ps ({b['match_ps']:4.0f})"
                     f"  천장 {a['ceil_ps']:5.0f}ps")
            for s in (a, b):
                L.append(f"      {s['side']}: {s['classes'] or '부류와 맞은 스텝 없음'}")
        for side in "LR":
            v = [s for s in ss if s["side"] == side]
            L.append(f"  {side} 요약 — 선반 폭 중앙값 {np.median([s['shelf_ps'] for s in v]):.0f}ps · 맞은 폭 중앙값 {np.median([s['match_ps'] for s in v]):.0f}ps · "
                     "주 부류: " + " · ".join(f"{c or '없음'} {k}런" for c, k in Counter(s["main_class"] for s in v).most_common()))
    ss = [s for s in sides if s["mhz"] == 25]
    st = [s for s in steps if s["mhz"] == 25]
    L += ["", f"== 25MHz — 벽 {len(ss)}개 (런 {len(ss) // 2}) =="]
    L.append(f"  30-70% 스텝이 있는 벽 {sum(s['shelf_steps'] > 0 for s in ss)} · 그중 부류와 맞은(exact · near) 스텝이 있는 벽 "
             f"{sum(s['match_steps'] > 0 for s in ss)} · exact 스텝이 있는 벽 {sum(s['exact_steps'] > 0 for s in ss)}")
    L.append(f"  30-70% 스텝 {len(st)}개: " + " · ".join(f"{m} {sum(s['match'] == m for s in st)}" for m in ("exact", "near", "far")))
    for side in "LR":
        t = Counter(s["class"] for s in st if s["side"] == side and s["match"] == "exact")
        L.append(f"  {side} exact 스텝의 부류: " + (" · ".join(f"{c} ×{k}" for c, k in t.most_common()) or "없음"))
    by = defaultdict(list)
    for s in ss:
        if s["exact_steps"]:
            by[s["chip"]].append(s)
    L.append("  exact 스텝이 있는 칩 (런 · 쪽 · 맞은 폭 · 부류):")
    for chip in sorted(by):
        for s in by[chip]:
            L.append(f"    {chip} {s['utc']} {s['side']} {s['match_ps']:4.0f}ps  {s['classes']}")
    (OUT / "isi_shelf_summary.txt").write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"출력: {OUT.relative_to(REPO)}/ — isi_shelf_steps.csv ({len(steps)}행) · isi_shelf_runs.csv ({len(sides)}행) · isi_shelf_summary.txt")


if __name__ == "__main__":
    main()
