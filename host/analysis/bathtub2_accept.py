# bathtub2_accept.py — 수정안 #4 A4 · A5 실칩 인수 판정 (같은 장착의 v1 스윕 + v2 std 런)
#
# 사용: uv run python host/analysis/bathtub2_accept.py a4 <v1 sweep_….csv> <v2 bathtub2_….csv>
#       uv run python host/analysis/bathtub2_accept.py a5 <v2 75MHz bathtub2_….csv>
#
# 입력 확인 — 유효 런(reason complete, 파일명에 _invalid 없음)만 받는다. A4 는 v1 · v2 의 uid · target · reseat · 주파수가 같아야 한다.
#   스텝마다 R 행 수가 n_reads 와 다르거나 flags 에 reads_gap 이 붙은 스텝은 읽기별 판정에서 뺀다(§2.6). 천장 스텝이면 불통과
# 위상은 원형이다 — 스텝을 훑기 덩어리 중심 기준 오프셋으로 풀어 비교한다
#
# A4 (수정안 #4 §4 A4 · 로그 55 [D55-24])
#   1 위치  — v2 scan 덩어리(N = 1)와 v1 덩어리(N = 112)의 첫 · 끝 스텝 차이. 허용 칸 수는 정하지 않았다 — 수치만 낸다
#   2 천장  — 천장 = ceil 행 중 읽기당 오류가 최댓값인 스텝의 첫-끝 범위. 그 범위의 ceil 스텝이 전부 최댓값이어야 하고(구멍이면
#             불통과), 전 읽기 err_count 가 쪽별 하강 수이거나 전 읽기가 쪽 안 상승 수여야 한다(수정안: 하강 56,572 또는 상승
#             56,460 — chip07 2026-09-20 은 상승). 99% 문턱은 벽 끝 칸(611 · 618)이 섞여 쓰지 않는다 — 결과를 본 뒤 정한 것이다.
#             같은 장착 v1 의 최댓값 스텝을 나란히 낸다
#   3 짝    — 전 읽기(scan · ceil · wall · rescan)에서 짝이 골라진다 — bathtub2_analysis.pick_pair 그대로(옆 · 둘 · 옆 아닌 하나).
#             짝 없음(옆 가까움 · 둘 다 안 맞음)이 0 이어야 한다
#   4 방향  — 천장 스텝에서 고른 짝의 「지금 비트」 정렬 c 에서 전 읽기 e1_c = 0 이면 상승 먼저, e1_c = e_c 면 하강 먼저.
#             섞이면 불통과. 극성(e1 이 정답 1 쪽인가)은 이 항목이 검증하지 못한다 — A5 의 선반 방향이 본다
# A5 (수정안 #4 §4 A5 · [D55-20]) — 정답은 같은 런의 오류 수로 정한다
#   선반 후보 = ceil · wall 행 중 읽기당 오류가 그 런 최댓값의 30-70% (bathtub_isi_shelf.py 와 같은 문턱), 최댓값 스텝 왼쪽 L · 오른쪽 R
#   부류 = 읽기별 err_count(min)와 쪽별 개수가 가장 많이 일치하는 PRBS 이력 부류 (bathtub_isi_shelf.candidates)
#   부류 선반 = 부류가 그 스텝의 전 읽기와 일치하는 스텝 (v1 bathtub_isi_shelf 의 112/112 와 같은 뜻). 일부만 맞는 비탈 스텝은
#     참고로만 낸다 — 부류마다 쪽당 개수가 약 250 으로 비슷해 섞인 스텝에서는 다른 부류와 우연히 같은 읽기가 나온다
#     (chip02 75MHz 첫 런: R 626 · 627 이 「0 0 1」 상승과 55 · 488 읽기 우연 일치, 계수기는 R 하강 쪽)
#   부류 선반에서 판정하는 것:
#     ① 계수기 — 오류가 가장 적은 정렬의 (e − e1, e1). 표 그대로: L 상승 · R 하강 → e − e1 = 부류 개수, e1 = 0
#                                                                  L 하강 · R 상승 → e1 = 부류 개수, e − e1 = 0
#     ② 짝 · 정렬 번호 — pick_pair 가 짝을 고르고(짝 없음 0), L 은 오류가 가장 적은 정렬 = c, R 은 = c − 1
#     ③ 짝의 반대쪽 정렬(L 은 c − 1, R 은 c) — 흔한 경우(L 「1 0 1」 상승 · R 「1 1 0」 하강)에만 유도된 값이 있다:
#        L: (e − e1, e1) = (하강 수, 상승+쪽 끝 상승 수 − 부류 개수) · R: (상승+쪽 끝 상승 수, 하강 수 − 부류 개수).
#        ①은 e1 = 0 만 보게 되어 e1 경로가 죽어도 통과한다 — ③이 e1 이 실제 값을 세는지 본다. 다른 부류면 「대조 없음」
#   통과 = L · R 양쪽에 부류 선반 + 부류 선반 전 읽기에서 ① · ② (· ③ 이 있으면 ③). 한쪽에만 부류 선반이면 「판정 불가(한쪽)」.
#   허용 오차는 두지 않는다
# 출력은 화면뿐이다. 판정 결과는 사람이 로그 · results 에 옮긴다

import argparse
import csv
import io
from pathlib import Path

import numpy as np

from bathtub2_analysis import OUTCOMES, page_counts, pick_pair, prbs_page, selfcheck
from bathtub_freq_compare import block
from bathtub_isi_shelf import candidates

SHELF_LO, SHELF_HI = 0.3, 0.7
NAMES = {"one": "옆 하나", "both": "둘 → 옆", "far": "옆 아닌 하나", "near": "옆 가까움(짝 없음)", "none": "둘 다 안 맞음(짝 없음)"}
READS_COLS = "phase_step,pass,read_idx,err_count,e_c0,e_c1,e_c2,e1_c0,e1_c1,e1_c2"
COMMON = {("L", "「1 0 1」 상승"), ("R", "「1 1 0」 하강")}       # ③ 의 유도가 있는 경우 (+쪽 경계 포함)


def ok(flag):
    return "통과" if flag else "불통과"


def load_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    name = Path(path).name
    if "_invalid" in name or {r["reason"] for r in rows} != {"complete"}:
        raise SystemExit(f"{name}: 유효 런이 아니다 (reason {sorted({r['reason'] for r in rows})})")
    return rows


def load_main(path):
    rows = load_csv(path)
    if "pass" not in rows[0]:
        raise SystemExit(f"{Path(path).name}: v2(bathtub2_*) 메인 CSV 가 아니다")
    if {r["mode"] for r in rows} != {"std"}:
        raise SystemExit(f"{Path(path).name}: std 런만 받는다")
    flags = sorted({f for r in rows for f in r["flags"].split("|") if f} - {"reads_gap"})
    print(f"     flags {flags or '없음'}")
    return rows


def load_reads(path):
    """_reads.csv → (step, pass 글자, read_idx, err_count, e (n,3), e1 (n,3))."""
    head, txt = Path(path).read_text(encoding="utf-8").split("\n", 1)
    if head.strip() != READS_COLS:
        raise SystemExit(f"{Path(path).name}: 열이 다르다 — {head.strip()}")
    p = np.array([ln.split(",", 2)[1] for ln in txt.splitlines()])
    a = np.loadtxt(io.StringIO(txt.translate(str.maketrans({"s": "0", "c": "1", "w": "2", "r": "3"}))),
                   delimiter=",", dtype=np.int64, ndmin=2)
    return a[:, 0], p, a[:, 2], a[:, 3], a[:, 4:7], a[:, 7:10]


def gap_steps(rows, step, ps):
    """(pass 글자, 스텝) 중 R 행 수 ≠ n_reads 이거나 reads_gap 표시 — 읽기별 판정에서 뺀다."""
    have = {}
    for k in zip(ps.tolist(), step.tolist()):
        have[k] = have.get(k, 0) + 1
    out = set()
    for r in rows:
        k = (r["pass"][0], int(r["phase_step"]))
        if have.get(k, 0) != int(r["n_reads"]) or "reads_gap" in r["flags"].split("|"):
            out.add(k)
    return out


def scan_block(rows, n_steps):
    e = np.zeros(n_steps, np.int64)
    for r in rows:
        if r["pass"] == "scan":
            e[int(r["phase_step"])] = int(r["bit_errors"])
    first, length = block(e)
    return first, length


def pages(base, n):
    return [base * 16 + i for i in range(n)]


def top_range(per_read, off):
    """{스텝: 읽기당 오류} → (최댓값, 최댓값 스텝의 첫-끝 범위 안 스텝 목록(오프셋 순)). 범위 안에 최댓값 아닌 스텝이 섞일 수 있다."""
    top = max(per_read.values())
    tops = [s for s, v in per_read.items() if v == top]
    lo, hi = min(off(s) for s in tops), max(off(s) for s in tops)
    return top, sorted((s for s in per_read if lo <= off(s) <= hi), key=off)


def a4(v1_path, v2_path):
    selfcheck()
    v1 = sorted(load_csv(v1_path), key=lambda r: int(r["phase_step"]))
    n_steps = len(v1)
    print(f"A4 — v1 {Path(v1_path).name}\n     v2 {Path(v2_path).name}")
    rows = load_main(v2_path)
    for k in ("uid", "target", "reseat", "f_sclk_hz"):
        a, b = {r[k] for r in v1}, {r[k] for r in rows}
        if a != b or len(a) != 1:
            raise SystemExit(f"v1 · v2 의 {k} 가 다르다: {sorted(a)} · {sorted(b)} — 같은 장착 · 같은 칩만 받는다")
    base = int(rows[0]["base_sector"])
    print(f"     {rows[0]['target']} · base sector {base}")

    # 1 위치
    e_v1 = np.array([int(r["bit_errors"]) for r in v1])
    f1, l1 = block(e_v1)
    s_first, s_len = scan_block(rows, n_steps)
    center = s_first + (s_len - 1) / 2
    off = lambda s: (s - center + n_steps / 2) % n_steps - n_steps / 2      # noqa: E731 — 덩어리 중심 기준, 원형을 푼다
    d_first = round(off(s_first) - off(f1))
    d_last = round(off((s_first + s_len - 1) % n_steps) - off((f1 + l1 - 1) % n_steps))
    print(f"\n1 위치   v1 덩어리 {f1}-{(f1 + l1 - 1) % n_steps} ({l1}칸) · v2 scan {s_first}-{(s_first + s_len - 1) % n_steps} "
          f"({s_len}칸) · 첫 스텝 차 {d_first:+d} · 끝 스텝 차 {d_last:+d} — 허용 칸 수 미정, 수치만")

    step, ps, idx, err, e, e1 = load_reads(str(v2_path)[:-4] + "_reads.csv")
    gaps = gap_steps(rows, step, ps)
    if gaps:
        print(f"         R 행 결측 · reads_gap 스텝 (읽기별 판정에서 뺌): {sorted(gaps)}")
    cnt = np.array([page_counts(p) for p in pages(base, idx.max() + 1)], np.int64)    # (쪽 안 전이, 상승+끝, 하강)
    T, DN, UPIN = cnt[idx, 0], cnt[idx, 2], cnt[idx, 0] - cnt[idx, 2]
    use = ~np.array([(p, s) in gaps for p, s in zip(ps.tolist(), step.tolist())])

    # 2 천장
    per = {int(r["phase_step"]): int(r["bit_errors"]) / int(r["n_reads"]) for r in rows if r["pass"] == "ceil"}
    top, rng = top_range(per, off)
    holes = [s for s in rng if per[s] != top]
    gap_top = [s for s in rng if ("c", s) in gaps]
    m = (ps == "c") & np.isin(step, rng) & use
    hit_dn, hit_up = int((err[m] == DN[m]).sum()), int((err[m] == UPIN[m]).sum())
    kind = "하강 수" if hit_dn == m.sum() else "쪽 안 상승 수" if hit_up == m.sum() else None
    v1_top = np.flatnonzero(e_v1 == e_v1.max())
    good2 = kind is not None and not holes and not gap_top and m.sum() > 0
    print(f"2 천장   천장 스텝 {rng[0]}-{rng[-1]} ({len(rng)}칸, 읽기당 {top:.1f}) · 구멍 {holes or '없음'} · "
          f"err_count = 하강 수 {hit_dn}/{m.sum()} · = 쪽 안 상승 수 {hit_up}/{m.sum()}"
          f"{' (' + kind + ')' if kind else ''} — {ok(good2)}"
          + (f" · 천장에 R 행 결측 {gap_top}" if gap_top else ""))
    print(f"         같은 장착 v1 의 최댓값 스텝 {v1_top.min()}-{v1_top.max()} ({len(v1_top)}칸)")
    for s in sorted(per, key=off):
        k = (ps == "c") & (step == s)
        print(f"         ceil {s} 읽기당 {per[s]:.1f} · 하강 수 일치 {(err[k] == DN[k]).sum()}/{k.sum()}"
              + ("  ← 천장" if s in rng else ""))

    # 3 짝 — 옆 짝은 훑기 덩어리 중심 기준 (bathtub2_analysis.read_stats 와 같다)
    right = off(step) > 0
    c, out = pick_pair(e, T, right)
    tally = np.bincount(out[use], minlength=len(OUTCOMES))
    print(f"3 짝     읽기 {use.sum()} — " + " · ".join(f"{NAMES[k]} {v}" for k, v in zip(OUTCOMES, tally)) +
          f" — {ok(tally[3] + tally[4] == 0)}")
    for p, nm in (("s", "scan"), ("c", "ceil"), ("w", "wall"), ("r", "rescan")):
        t = np.bincount(out[(ps == p) & use], minlength=len(OUTCOMES))
        print(f"         {nm:6s} " + " · ".join(f"{NAMES[k].split('(')[0]} {v}" for k, v in zip(OUTCOMES, t)))

    # 4 방향
    rows_m = np.flatnonzero(m)
    cc = c[rows_m]
    ec, e1c = e[rows_m, np.maximum(cc, 1)], e1[rows_m, np.maximum(cc, 1)]
    zero, full = int((e1c == 0).sum()), int((e1c == ec).sum())
    pick = ", ".join(f"c={k} {v}" for k, v in zip(*np.unique(cc, return_counts=True)))
    if len(cc) and zero == len(cc):
        verdict = "판정: 상승 먼저 — 통과"
    elif len(cc) and full == len(cc):
        verdict = "판정: 하강 먼저 — 통과"
    else:
        verdict = "섞임 — 불통과"
    print(f"4 방향   천장 읽기 {len(cc)} · 고른 정렬 {pick} · e1_c = 0 {zero} · e1_c = e_c {full} — {verdict}"
          f" (극성은 A5 의 선반 방향으로 확인)")


def a5(v2_path):
    selfcheck()
    print(f"A5 — {Path(v2_path).name}")
    rows = load_main(v2_path)
    base = int(rows[0]["base_sector"])
    n_steps = int(round(1e12 / float(rows[0]["f_sclk_hz"]) / float(rows[0]["dphi_ps"])))
    print(f"     {rows[0]['target']} · {round(float(rows[0]['f_sclk_hz']) / 1e6)}MHz · base sector {base}")
    s_first, s_len = scan_block(rows, n_steps)
    center = s_first + (s_len - 1) / 2
    off = lambda s: (s - center + n_steps / 2) % n_steps - n_steps / 2      # noqa: E731

    deep = {int(r["phase_step"]): int(r["bit_errors"]) / int(r["n_reads"]) for r in rows if r["pass"] in ("ceil", "wall")}
    top, rng = top_range(deep, off)
    lo, hi = off(rng[0]), off(rng[-1])
    shelf = sorted((s for s, v in deep.items() if SHELF_LO * top < v < SHELF_HI * top), key=off)
    print(f"최댓값 스텝 {rng[0]}-{rng[-1]} (읽기당 {top:.1f}) · 선반 후보 {len(shelf)}스텝")
    if not shelf:
        print("선반이 없다 — 판정 불가")
        return

    step, ps, idx, err, e, e1 = load_reads(str(v2_path)[:-4] + "_reads.csv")
    gaps = gap_steps(rows, step, ps)
    n_pages = idx.max() + 1
    cnt = np.array([page_counts(p) for p in pages(base, n_pages)], np.int64)
    T, R, DN = cnt[idx, 0], cnt[idx, 1], cnt[idx, 2]
    c, out = pick_pair(e, T, off(step) > 0)
    cands = candidates(np.array([prbs_page(p) for p in pages(base, n_pages)]))

    plateau = {"L": 0, "R": 0}
    bad = []
    for s in shelf:
        side = "L" if off(s) < lo else "R" if off(s) > hi else None
        if side is None:
            print(f"  스텝 {s}: 최댓값 범위 안쪽 — 건너뜀")
            continue
        if any((p, s) in gaps for p in ("c", "w")):
            print(f"  스텝 {s} {side}: R 행 결측 · reads_gap — 건너뜀")
            continue
        m = np.isin(ps, ("c", "w")) & (step == s)
        i, rows_m = idx[m], np.flatnonzero(m)
        name, cv = max(cands, key=lambda k: int((err[m] == k[1][i]).sum()))
        cls = err[m] == cv[i]
        n, n_cls = int(m.sum()), int(cls.sum())
        amin = e[rows_m].argmin(1)
        emin, e1min = e[rows_m, amin], e1[rows_m, amin]
        base_name = name.replace(" +쪽 경계", "")
        rise = base_name.endswith("상승")
        on_e1 = (side == "L") != rise                  # L 하강 · R 상승 → e1 쪽에 부류 개수
        cnt_part, zero_part = (e1min, emin - e1min) if on_e1 else (emin - e1min, e1min)
        ctr = (cnt_part == cv[i]) & (zero_part == 0)
        cs = c[rows_m]
        pair = (out[rows_m] <= 2) & (amin == (cs if side == "L" else cs - 1))
        if (side, base_name) in COMMON:                # ③ 짝의 반대쪽 정렬
            j = np.where(side == "L", cs - 1, cs).astype(int)
            j = np.clip(j, 0, 2)
            eo, e1o = e[rows_m, j], e1[rows_m, j]
            opp = ((eo - e1o == DN[m]) & (e1o == R[m] - cv[i])) if side == "L" else ((eo - e1o == R[m]) & (e1o == DN[m] - cv[i]))
            opp_txt = f"{int((opp & cls).sum())}/{n_cls}"
        else:
            opp = np.ones(n, bool)
            opp_txt = "대조 없음"
        all_ok = ctr & pair & opp
        if n_cls == 0:
            kind = "부류 없음(벽 · 천장 가장자리)"
        elif n_cls == n:
            kind = "부류 선반"
            plateau[side] += 1
            if not all_ok.all():
                bad.append(s)
        else:
            kind = "비탈(참고)"
        print(f"  스텝 {s} {side} · 읽기 {n} · {name} {n_cls}/{n} [{kind}] · 그중 ① 계수기"
              f"({'e1' if on_e1 else 'e − e1'} = 개수) {int((ctr & cls).sum())} · ② 짝 · 정렬 {int((pair & cls).sum())} · "
              f"③ 반대쪽 {opp_txt} · 가장 적은 정렬 {np.bincount(amin, minlength=3).tolist()}")
    nopair = int((out[np.isin(ps, ("c", "w"))] >= 3).sum())
    print(f"벽 집중 읽기 중 짝 없음 {nopair}")
    if plateau["L"] and plateau["R"]:
        verdict = "통과" if not bad and nopair == 0 else "불통과"
    elif plateau["L"] or plateau["R"]:
        verdict = "판정 불가(한쪽 선반만)" if not bad else "불통과"
    else:
        verdict = "판정 불가(부류 선반 없음)"
    print(f"부류 선반 L {plateau['L']}스텝 · R {plateau['R']}스텝 · 어긋난 부류 선반 {bad or '없음'} — A5 {verdict}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p4 = sub.add_parser("a4")
    p4.add_argument("v1")
    p4.add_argument("v2")
    p5 = sub.add_parser("a5")
    p5.add_argument("v2")
    a = ap.parse_args(argv)
    if a.cmd == "a4":
        a4(a.v1, a.v2)
    else:
        a5(a.v2)


if __name__ == "__main__":
    main()
