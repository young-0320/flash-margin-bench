"""`host/analysis/wear_inverse.py` — 합성 교정 곡선으로 무리 선택·구간 출력·모의 블라인드를 잰다."""

import csv
import math
import statistics
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import wear_curves as wc                                     # noqa: E402
import wear_inverse as wi                                    # noqa: E402

FRESH = {"fastA": 30_000, "fastB": 34_000, "slowA": 48_000, "slowB": 50_000}
V3 = {"model": "v3.2"}
RHO4 = {"sector": 0.5, "prep": 0.3, "chip": 0.2}             # v4 시험용 ρ (등록값이 아니다)
_ND = statistics.NormalDist()


def cell_row(chip, k, s, mid, spread=0.0234):
    """교정 표 한 행 — p10/p90 = ±3% (σ 2.34%) 의 정규 모양을 분위수 21개로도 적는다 (양끝은 ±2.56σ)."""
    z = [max(-2.56, min(2.56, _ND.inv_cdf(q / 100))) if 0 < q < 100 else (-2.56 if q == 0 else 2.56) for q in wc.Q_LEVELS]
    return [chip, k * 1000 + 1, (k + 1) * 1000, s, 1000, int(mid * 0.97), int(mid), int(mid * 1.03), 6900, 6950, 7000,
            *[int(mid * (1 + spread * v)) for v in z]]


def synth_curves(tmp_path):
    """빠른 무리 둘(가파름 + 60k 계단) · 느린 무리 둘(완만). 1k 구간 100개 × 섹터 7개, p10/p90 = ±3%."""
    def erase(chip, cyc):
        f = FRESH[chip]
        if chip.startswith("fast"):
            v = f + 0.6 * cyc + (20_000 if cyc >= 60_000 else 0)      # 30 → 66 → (계단) 106ms
        else:
            v = f + 0.25 * cyc                                        # 48 → 73ms
        return v * (1.01 if chip.endswith("B") else 1.0)
    for chip in FRESH:
        with (tmp_path / f"wear_curves_{chip}_2026-09.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(wc.FIELDS)
            for k in range(100):
                for s in range(7):
                    w.writerow(cell_row(chip, k, s, erase(chip, k * 1000 + 500) * (1 + 0.004 * s)))
    return str(tmp_path / "wear_curves_*_2026-09.csv")


def test_invert_picks_group_and_brackets_truth(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    # 빠른 칩이 45k 만큼 닳았다고 치자 — fastA 곡선의 45,500 값 근처 (계단 전)
    worn = [int((30_000 + 0.6 * 45_500) * (1 + 0.004 * s)) for s in range(7)]
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, **V3)
    assert r["group"] == "fast" and set(r["chips"]) == {"fastA", "fastB"}
    assert any(a <= 45_500 <= z for a, z in r["hpd95"])
    assert r["outside_at_map"] == 0
    # 같은 소거 시간(약 57ms)이 느린 칩에서 나오면 무리가 바뀌고 답은 훨씬 큰 사이클이다
    r2 = wi.invert(49_000, worn, curves, FRESH, "ms", 40_000, **V3)
    assert r2["group"] == "slow" and r2["map"][0] > 20_000


def test_step_region_is_distinguished(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [int((30_000 + 0.6 * 70_500 + 20_000) * (1 + 0.004 * s)) for s in range(7)]   # 계단 뒤
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, **V3)
    assert all(a >= 60_001 for a, _ in r["hpd95"])


def test_loco_runs_both_scales(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    for scale in ("ms", "ratio"):
        rows = wi.loco(curves, FRESH, scale, 40_000, cycles=(10_000, 50_000, 90_000), **V3)
        assert len(rows) == 12                                 # 4칩 × 3점
        assert all(r[6] for r in rows if r[5])                 # 68% 안이면 95% 안
        assert all(a <= z and a % 1000 == 1 for r in rows for a, z in r[4])
    # 합성 느린 무리는 두 칩의 ms 차이가 기울기에 비해 작다 → ms 눈금에서 95% 가 정답을 다 품는다.
    # 빠른 무리는 신품값 차이(4ms)가 7k 사이클에 해당해 ms 로는 놓친다 — 눈금 선택 규칙이 잡아야 할 바로 그 상황
    rows = wi.loco(curves, FRESH, "ms", 40_000, cycles=(10_000, 50_000, 90_000), **V3)
    assert all(r[6] for r in rows if r[0].startswith("slow"))


def test_parse_prep_log_and_observation(tmp_path):
    lines = [f"#PREP ERASE {s} {110_000 if s < 7 else 34_000}" for s in range(128)]
    lines += [f"#PREP PROGRAM {s} {6_950 if s < 7 else 6_700}" for s in range(128)]   # 빠른 무리 서명 (7.0ms 근처)
    p = tmp_path / "session_chip99_0000000000000000_20261001T000000Z.log"
    p.write_text("junk\n" + "\n".join(lines) + "\n#PREP PASS\n", encoding="utf-8")
    erase, program = wi.parse_prep_logs([p])
    ref, worn = wi.observation(erase)
    assert ref == 34_000 and worn == [110_000] * 7
    assert program[0] == [6_950] and program[127] == [6_700]       # 파싱은 남긴다 (v4 프로그램 축 재료) — 화면 · 기록에는 안 쓴다


def test_answers_stop_at_100k(tmp_path):
    pattern = synth_curves(tmp_path)
    # fastA 만 150k 까지 늘린다 (chip01 300k 처럼) — 관측이 그 너머 값이어도 답은 100k 안에 머문다
    with (tmp_path / "wear_curves_fastA_2026-09.csv").open("a", newline="") as fh:
        w = csv.writer(fh)
        for k in range(100, 150):
            for s in range(7):
                w.writerow(cell_row("fastA", k, s, (30_000 + 0.6 * (k * 1000 + 500) + 20_000) * (1 + 0.004 * s)))
    curves = wi.load_curves(pattern)
    worn = [int((30_000 + 0.6 * 130_500 + 20_000) * (1 + 0.004 * s)) for s in range(7)]
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, **V3)
    assert r["map"][1] <= 100_000
    assert all(z <= 100_000 for _, z in r["hpd95"])


# ---------- 부속 연구 (--loco-obs single · --dx) ----------

def _linear_arows(slope_us=0.5, base=50_000, n_cycles=20_000, gap=None):
    import numpy as np
    e = np.full((7, n_cycles + 1), np.nan)
    c = np.arange(1, n_cycles + 1)
    for s in range(7):
        e[s, 1:] = base + slope_us * c + 100 * s
    if gap:
        e[:, gap[0]:gap[1] + 1] = np.nan
    return wi.ARows(e)


def test_window_slope_recovers_line():
    a = _linear_arows(slope_us=0.5)
    slope, sigma, fill = a.window_slope(1001, 5000)
    assert abs(slope - 0.5) < 1e-9 and fill == 1.0
    assert sigma <= 0.02 * 0.5 + 1e-12                       # 직선이면 폭은 2% 하한
    assert a.window_slope(18_000, 5000) is None              # 데이터 끝을 넘는 창


def test_long_gap_and_partial_window():
    a = _linear_arows(gap=(8_000, 9_499))                    # 1,500 사이클 결측
    assert a.has_long_gap(7_001, 12_000)
    assert not a.has_long_gap(1, 7_000)
    assert a.window_slope(7_001, 5000) is not None           # 70% 채움 — 교정 쪽은 쓴다
    assert a.window_slope(8_001, 2000) is None               # 25% 채움


def test_sample_obs_is_seeded_and_in_bin():
    import random
    a = _linear_arows()
    o1 = a.sample_obs(3001, 3, random.Random("0:x"))
    o2 = a.sample_obs(3001, 3, random.Random("0:x"))
    assert o1 == o2 and len(o1) == 7
    assert all(50_000 + 0.5 * 3001 + 100 * s <= v <= 50_000 + 0.5 * 4000 + 100 * s for s, v in enumerate(o1))


def test_study_p50_matches_registered_loco(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    cyc = (10_000, 50_000, 90_000)
    ref = wi.loco(curves, FRESH, "ratio", 40_000, cycles=cyc, rate_range=2.0, **V3)
    rows, skipped = wi.loco_study(curves, FRESH, "ratio", 40_000, 2.0, cycles=cyc, **V3)
    assert not skipped
    assert [(r["chip"], r["x"], (r["med"], r["med"] + 999), r["h68"], r["h95"]) for r in rows] == \
           [(c, x, m, h68, h95) for c, x, m, h68, h95, _, _ in ref]


def test_grade_picks_the_band_with_most_mass():
    """시연 화면의 판정 — 정격 대비 구간(1 · 20 · 60%) 중 사후 확률이 가장 큰 것. 구간은 1k 구간의 끝 사이클로 나눈다."""
    name, span, p = wi.grade({7001: 0.5, 15001: 0.26, 25001: 0.24})
    assert (name, span) == ("저마모", "1-20%") and abs(p - 0.76) < 1e-9
    assert wi.grade({1: 1.0})[:2] == ("신품", "1% 미만")
    assert wi.grade({70001: 1.0})[:2] == ("고마모", "60% 이상")
    assert wi.grade({19001: 0.4, 20001: 0.6})[0] == "중마모"          # 19,001-20,000 은 저마모, 20,001-21,000 은 중마모


def test_screen_aligns_labels_and_ends_with_the_verdict(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [int((30_000 + 0.6 * 12_500) * (1 + 0.004 * s)) for s in range(7)]
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, **V3)
    lines = wi.screen({"0000000000000000"}, {0: [], 127: []}, 1, 31_000, worn, r, 1.0, 40_000)
    labeled = [ln for ln in lines if ": " in ln and not ln.startswith(("─", " "))]
    assert {wi._w(ln.split(": ")[0]) for ln in labeled} == {13}      # 한글을 2칸으로 세어 콜론이 같은 자리
    assert lines[-2].startswith("판정") and "확률" in lines[-2] and lines[-1] == "─" * 61
    assert "UID 0000000000000000 (등록부에 없음)" in lines[1] and lines[6].startswith("─")


def test_screen_calls_a_chip_below_the_first_band_new(tmp_path):
    """곡선 첫 구간(1-1,000)보다도 덜 닳은 칩 — 교정 밴드 밖이어도 보류가 아니라 신품이고, 주의 대신 참고 줄이 뜬다."""
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [25_000] * 7                                          # fastA 첫 구간(약 30.3ms)의 밴드보다 아래
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, **V3)
    lines = wi.screen({"0000000000000000"}, {0: [], 127: []}, 1, 31_000, worn, r, 1.0, 40_000)
    assert any(ln.startswith("참고") and ln.endswith("교정 첫 구간(1-1,000회)보다 덜 닳음") for ln in lines)
    assert not any(ln.startswith("주의") for ln in lines) and lines[-2].startswith("판정") and "신품" in lines[-2]


def test_median_bin_is_the_half_mass_bin():
    """v3 대표값 — 누적 확률이 처음 절반을 넘는 구간. 오른쪽 꼬리가 길면 MAP 보다 뒤에 선다."""
    post = {1: 0.30, 1001: 0.15, 2001: 0.15, 3001: 0.15, 4001: 0.25}
    assert max(post, key=post.get) == 1 and wi.median_bin(post) == 2001
    assert wi.median_bin({5001: 1.0}) == 5001


def test_v3_defaults(tmp_path):
    """v3.1 — R 은 무리별(빠른 1.6 · 느린 1.3), rate_range 를 안 주면(None) 무리에 맞는 값을 쓴다."""
    assert wi.RATE_RANGE == {"fast": 1.6, "slow": 1.3} and not hasattr(wi, "program_check")
    curves = wi.load_curves(synth_curves(tmp_path))
    assert wi.invert(31_000, [40_000] * 7, curves, FRESH, "ms", 40_000, None, **V3)["rate_range"] == 1.6
    assert wi.invert(49_000, [55_000] * 7, curves, FRESH, "ms", 40_000, None, **V3)["rate_range"] == 1.3
    assert wi.invert(49_000, [55_000] * 7, curves, FRESH, "ms", 40_000, 2.0, **V3)["rate_range"] == 2.0


# ---------- v4 — 고른 값을 잰 값으로 (docs/spec/s5 §2 v4 열) ----------

def bimodal_cell(lo_vals, hi_vals):
    """계단 전환 셀 — 아래 봉우리 lo_vals 개 · 위 봉우리 hi_vals 개, 사이는 비었다 (chip04 섹터 3 · 26-27k 꼴)."""
    import random
    rng = random.Random(1)
    vals = [rng.uniform(80_000, 95_000) for _ in range(lo_vals)] + [rng.uniform(110_000, 112_000) for _ in range(hi_vals)]
    q = tuple(wc.pct(vals, p / 100) for p in wc.Q_LEVELS)
    return wi.Cell(q[2], q[10], q[18], q)


def test_quantile_member_gives_the_empty_gap_low_density():
    """v4 ① — 분위수 구성원은 한 번도 안 나온 95-110ms 에 봉우리보다 훨씬 낮은 밀도를 준다. 정규분포는 거기에 최대를 준다."""
    cell = bimodal_cell(593, 407)
    qm, gm = wi.Quant(cell, 1.0), wi.Gauss(cell, 1.0)
    peak = max(qm.logpdf(x) for x in range(80_000, 95_000, 500))
    assert qm.logpdf(100_000) < peak - math.log(8)             # 빈 구간은 봉우리의 1/8 아래
    assert gm.logpdf(100_000) > gm.logpdf(85_000)             # 정규분포는 빈 가운데가 더 높다
    assert qm.logpdf(50_000) == qm.logeps and qm.logpdf(200_000) == qm.logeps
    # 밀도의 적분이 1 — 조각마다 5% 씩
    step = 10.0
    mass = sum(math.exp(qm.logpdf(x)) * step for x in _frange(cell.q[0], cell.q[-1], step))
    assert abs(mass - 1.0) < 0.02
    assert (qm.lo, qm.mu, qm.hi) == (cell.q[2], cell.q[10], cell.q[18])


def _frange(a, b, step):
    x = a
    while x < b:
        yield x
        x += step


def test_quantile_member_floors_zero_width_and_scales_with_ratio():
    q = tuple([50_000] * 21)                                  # 평평한 셀 — 폭 0
    m = wi.Quant(wi.Cell(50_000, 50_000, 50_000, q), 1.0)
    assert math.isfinite(m.logpdf(50_000)) and m.logpdf(50_000) == math.log(0.05 / wi.Q_MIN_WIDTH_US)
    cell = bimodal_cell(500, 500)
    assert abs(wi.Quant(cell, 25_000.0).logpdf(3.6) - (wi.Quant(cell, 1.0).logpdf(90_000) + math.log(25_000))) < 1e-9


def test_quantile_cell_requires_the_columns(tmp_path):
    with (tmp_path / "wear_curves_old_2026-09.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(wc.FIELDS[:11])
        w.writerow(["old", 1, 1000, 0, 1000, 29_000, 30_000, 31_000, 6900, 6950, 7000])
    curves = wi.load_curves(str(tmp_path / "wear_curves_old_2026-09.csv"))
    assert curves["old"][1][0].q is None
    import pytest
    with pytest.raises(SystemExit, match="분위수 열"):
        wi.members(curves, {"old": 30_000}, ["old"], "ratio", cell="quantile")


def test_n_eff_ends_and_middle():
    """v4 ② — ρ_s = 1 · P = 1 이면 1 (v3 와 같다) · 둘 다 0 이면 k·P · 중간은 사이."""
    assert abs(wi.n_eff(7, 1, 1.0, 0.0) - 1.0) < 1e-12
    assert abs(wi.n_eff(7, 5, 0.0, 0.0) - 35.0) < 1e-12
    assert abs(wi.n_eff(7, 1, 0.5, 0.0) - 7 / (1 + 6 * 0.5)) < 1e-12
    assert abs(wi.n_eff(7, 5, 0.5, 0.3) - 1 / (0.5 / 5 + 0.3 / 7 + 0.2 / 35)) < 1e-12
    assert abs(wi.n_eff(7, 5, 0.5, 0.3, 0.2) - 1 / (0.2 + 0.8 * (0.5 / 5 + 0.3 / 7 + 0.2 / 35))) < 1e-12
    assert wi.n_eff(100, 100, 0.0, 0.0, 0.3) < 1 / 0.3 + 1e-9 and wi.n_eff(7, 1, 1.0, 0.0, 0.0) == 1.0   # 칩 효과는 늘려도 안 준다


def test_icc_oneway_recovers_planted_chip_share():
    """ρ_chip — 표마다 공통 성분(분산 c)과 표 안 잡음(분산 1−c)을 심으면 c 가 돌아온다. 공통 성분이 없으면 0."""
    import random
    rng = random.Random(3)
    for c in (0.0, 0.3, 0.7):
        tables = [[z + rng.gauss(0, math.sqrt(1 - c)) for _ in range(7)] for z in (rng.gauss(0, math.sqrt(c)) for _ in range(3000))]
        assert abs(wi.icc_oneway(tables) - c) < 0.04


def test_variance_components_recover_planted_rho():
    """ρ 측정 — prep 공통 · 섹터 공통 · 독립 성분을 심은 P×7 표에서 그 몫이 돌아온다."""
    import random
    rng = random.Random(3)
    P, k, rs, rp = 400, 7, 0.5, 0.3
    zs = [rng.gauss(0, 1) for _ in range(k)]
    table = [[math.sqrt(rs) * zp + math.sqrt(rp) * zs[s] + math.sqrt(1 - rs - rp) * rng.gauss(0, 1) for s in range(k)]
             for zp in (rng.gauss(0, 1) for _ in range(P))]
    got_s, got_p = wi.variance_components(table)
    assert abs(got_s - rs) < 0.06 and abs(got_p - rp) < 0.12   # 섹터 성분은 열 7개로 추정해 거칠다
    assert wi.variance_components([[1, 2, 3], [1, 2, 3], [1, 2, 3]]) == (0.0, 1.0)   # 섹터 차이뿐이면 ρ_p = 1


def test_rho_from_preps_needs_every_sector_each_prep():
    import pytest
    erase = {s: [100_000 + 1000 * s + 10 * p for p in range(3)] for s in range(7)}
    rs, rp = wi.rho_from_preps(erase, 3)
    assert 0 <= rs <= 1 and rp > 0.9                            # 섹터 차이가 크고 prep 차이는 작다
    with pytest.raises(SystemExit):
        wi.rho_from_preps({s: [1, 2] for s in range(7)}, 3)


def speed_curves(tmp_path, factor=1.4):
    """같은 신품값의 빠른 칩 둘 — B 는 A 의 곡선을 가로로 factor 배 눌렀다 (B 가 factor 배 빨리 늙는다)."""
    def erase_a(cyc):
        return 30_000 + 0.6 * cyc + 3e-6 * cyc * cyc            # 휘어진 곡선 — 배율이 식별된다
    for chip in ("spA", "spB"):
        with (tmp_path / f"wear_curves_{chip}_2026-09.csv").open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(wc.FIELDS)
            for k in range(100):
                c = k * 1000 + 500
                for s in range(7):
                    w.writerow(cell_row(chip, k, s, erase_a(c * factor if chip == "spB" else c) * (1 + 0.004 * s)))
    return wi.load_curves(str(tmp_path / "wear_curves_sp*_2026-09.csv")), {"spA": 30_000, "spB": 30_000}


def test_chip_speeds_recover_the_stretch_and_alignment_shrinks_the_mixture(tmp_path):
    """v4 ③ — 쌍별 속도에서 칩당 ŝ (합 0), B/A ≈ 1.4. 정렬하면 구간마다 구성원 중심의 흩어짐이 준다."""
    curves, fresh = speed_curves(tmp_path)
    sp = wi.chip_speeds(curves, fresh, ["spA", "spB"])
    assert abs(sp["spA"] + sp["spB"]) < 1e-9
    assert abs(math.exp(sp["spB"] - sp["spA"]) - 1.4) < 0.05
    assert wi.chip_speeds(curves, fresh, ["spA"]) == {"spA": 0.0}
    raw = wi.members(curves, fresh, ["spA", "spB"], "ratio", "quantile")
    ali = wi.members(curves, fresh, ["spA", "spB"], "ratio", "quantile", sp)
    def spread(mem, b):
        mus = [m.mu for m in mem[b]]
        return max(mus) - min(mus)
    assert all(spread(ali, b) < spread(raw, b) for b in (20_001, 40_001, 60_001))
    assert len(ali[20_001]) == 14 and max(ali) > max(raw)       # 빠른 쪽(B, r̂>1)의 100k 는 공통 시계 100k·r̂ 까지 늘어난다
    assert wi.source_bin(28_499, 1.4) == 20_001 and wi.source_bin(28_499, 1.0) == 28_001


def test_rate_from_speeds_is_derived_not_chosen():
    """v4 ④ — R = exp(1.96·σ_r·√(1+1/M)). 무리에 칩 하나면 다른 무리의 σ_r 을 빌린다, 어디에도 둘이 없으면 1."""
    s = math.log(1.4) / 2
    by = {"fast": {"a": -s, "b": s}, "slow": {"c": 0.0}}
    R, sigma, M = wi.rate_from_speeds(by, "fast")
    assert M == 2 and abs(sigma - math.sqrt(2 * s * s)) < 1e-12
    assert abs(R - math.exp(1.96 * sigma * math.sqrt(1.5))) < 1e-12
    R1, sigma1, M1 = wi.rate_from_speeds(by, "slow")
    assert (M1, sigma1) == (1, sigma) and abs(R1 - math.exp(1.96 * sigma * math.sqrt(2))) < 1e-12
    assert wi.rate_from_speeds({"fast": {"a": 0.0}, "slow": {}}, "fast") == (1.0, 0.0, 1)


def test_v4_invert_brackets_truth_with_measured_knobs(tmp_path):
    """v4 끝에서 끝 — 분위수 셀 · n_eff · 정렬 · 유도 R. 정답을 품고, 손잡이 값이 결과에 찍힌다. ρ 미등록이면 돌지 않는다."""
    import pytest
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [int((30_000 + 0.6 * 45_500) * (1 + 0.004 * s)) for s in range(7)]
    with pytest.raises(SystemExit, match="ρ"):
        wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, None, rho={"sector": None, "prep": None, "chip": None})
    with pytest.raises(SystemExit, match="ρ"):
        wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, None, rho={"sector": 0.5, "prep": 0.3, "chip": None})
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000, None, rho=RHO4)
    assert r["group"] == "fast" and any(a <= 45_500 <= z for a, z in r["hpd95"])
    assert abs(r["evidence"] - wi.n_eff(7, 1, 0.5, 0.3, 0.2)) < 1e-12
    assert set(r["speeds"]) == {"fastA", "fastB"} and abs(sum(r["speeds"].values())) < 1e-9
    assert r["rate_range"] > 1 and r["sigma_r"] > 0            # 유도된 R
    r2 = wi.invert(31_000, worn * 3, curves, FRESH, "ms", 40_000, 2.0, preps=3, rho=RHO4)
    assert r2["rate_range"] == 2.0 and abs(r2["evidence"] - wi.n_eff(7, 3, 0.5, 0.3, 0.2)) < 1e-12
    assert any(a <= 45_500 <= z for a, z in r2["hpd95"])


def test_v4_loco_rows_use_whole_a_rows_and_report_the_band(tmp_path, capsys):
    """v4 ⑤ — rows 관측은 같은 사이클의 7섹터를 그대로 (prep 수 × 7), 빠진 칩 없이 정렬을 다시 낸다. 합격 띠는 점 수에서 미리."""
    import random
    curves = wi.load_curves(synth_curves(tmp_path))
    rows = wi.loco(curves, FRESH, "ratio", 40_000, cycles=(10_000, 50_000), rate_range=None, rho=RHO4)
    assert len(rows) == 8 and all(r[6] for r in rows if r[5])
    a = _linear_arows()
    o = a.sample_rows(3001, 2, random.Random("0:x"))
    assert len(o) == 14 and all(o[s] - o[0] == 100 * s for s in range(7))   # 한 사이클의 7섹터가 통째로
    arows = {c: _linear_arows() for c in FRESH}
    st, skipped = wi.loco_study(curves, FRESH, "ratio", 40_000, None, "rows", 2, reps=2, cycles=(10_000,), arows=arows, rho=RHO4)
    assert not skipped and len(st) == 8 and all(r["rep"] in (0, 1) for r in st)
    st2, skipped2 = wi.loco_study(curves, FRESH, "ratio", 40_000, None, "rows", 2, reps=1, cycles=(10_000,), arows={}, rho=RHO4)
    assert not st2 and len(skipped2) == 4                       # A 행 없는 칩은 이유와 함께 뺀다
    assert wi.coverage_band(58, 0.68) == (33, 46) and wi.coverage_band(58, 0.95) == (52, 58)
    assert wi.band_verdict(39, 58, 0.68).endswith("합격") and wi.band_verdict(50, 58, 0.68).endswith("과소신")
    assert wi.band_verdict(30, 58, 0.68).endswith("과신") and "전부 적중" in wi.band_verdict(58, 58, 0.95)
    wi.print_study(st, skipped, "rows k=2")
    assert "합격 띠" in capsys.readouterr().out


def test_v4_synthetic_draws_from_quantiles_with_correlation(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    cov = wi.synthetic(curves, FRESH, "ratio", 40_000, None, 3, 12, seed=1, loo=True, rho=RHO4)
    assert set(cov) == set(wi.SYN_LEVELS) and all(0 <= v <= 1 for v in cov.values())
    q = tuple(range(0, 2100, 100))
    assert wi._quantile_draw(q, 0.0) == 0 and wi._quantile_draw(q, 1.0) == 2000 and wi._quantile_draw(q, 0.525) == 1050


def test_v4_is_the_default_and_v3_is_reachable():
    assert wi.MODEL_VERSION == "v4" and set(wi.MODELS) == {"v3.2", "v4"}
    assert wi.MODELS["v4"] == {"cell": "quantile", "evidence": "neff", "align": True, "rate": "speeds"}
    assert wi.RHO == {"sector": 0.00, "prep": 0.78, "chip": 0.29}   # 2026-10-09 등록값 (inverse_v4_eval_2026-10.md) — 다시 재면 여기도 바꾼다
    assert wi.rate_label(None) == "유도 (σ_r)" and wi.rate_label(None, "v3.2").startswith("빠른 1.6")
