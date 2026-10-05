"""`host/analysis/wear_inverse.py` — 합성 교정 곡선으로 무리 선택·구간 출력·모의 블라인드를 잰다."""

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "analysis"))
import wear_curves as wc                                     # noqa: E402
import wear_inverse as wi                                    # noqa: E402

FRESH = {"fastA": 30_000, "fastB": 34_000, "slowA": 48_000, "slowB": 50_000}


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
                    mid = erase(chip, k * 1000 + 500) * (1 + 0.004 * s)
                    w.writerow([chip, k * 1000 + 1, (k + 1) * 1000, s, 1000,
                                int(mid * 0.97), int(mid), int(mid * 1.03), 6900, 6950, 7000])
    return str(tmp_path / "wear_curves_*_2026-09.csv")


def test_invert_picks_group_and_brackets_truth(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    # 빠른 칩이 45k 만큼 닳았다고 치자 — fastA 곡선의 45,500 값 근처 (계단 전)
    worn = [int((30_000 + 0.6 * 45_500) * (1 + 0.004 * s)) for s in range(7)]
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000)
    assert r["group"] == "fast" and set(r["chips"]) == {"fastA", "fastB"}
    assert any(a <= 45_500 <= z for a, z in r["hpd95"])
    assert r["outside_at_map"] == 0
    # 같은 소거 시간(약 57ms)이 느린 칩에서 나오면 무리가 바뀌고 답은 훨씬 큰 사이클이다
    r2 = wi.invert(49_000, worn, curves, FRESH, "ms", 40_000)
    assert r2["group"] == "slow" and r2["map"][0] > 20_000


def test_step_region_is_distinguished(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [int((30_000 + 0.6 * 70_500 + 20_000) * (1 + 0.004 * s)) for s in range(7)]   # 계단 뒤
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000)
    assert all(a >= 60_001 for a, _ in r["hpd95"])


def test_loco_runs_both_scales(tmp_path):
    curves = wi.load_curves(synth_curves(tmp_path))
    for scale in ("ms", "ratio"):
        rows = wi.loco(curves, FRESH, scale, 40_000, cycles=(10_000, 50_000, 90_000))
        assert len(rows) == 12                                 # 4칩 × 3점
        assert all(r[6] for r in rows if r[5])                 # 68% 안이면 95% 안
        assert all(a <= z and a % 1000 == 1 for r in rows for a, z in r[4])
    # 합성 느린 무리는 두 칩의 ms 차이가 기울기에 비해 작다 → ms 눈금에서 95% 가 정답을 다 품는다.
    # 빠른 무리는 신품값 차이(4ms)가 7k 사이클에 해당해 ms 로는 놓친다 — 눈금 선택 규칙이 잡아야 할 바로 그 상황
    rows = wi.loco(curves, FRESH, "ms", 40_000, cycles=(10_000, 50_000, 90_000))
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
                mid = (30_000 + 0.6 * (k * 1000 + 500) + 20_000) * (1 + 0.004 * s)
                w.writerow(["fastA", k * 1000 + 1, (k + 1) * 1000, s, 1000,
                            int(mid * 0.97), int(mid), int(mid * 1.03), 6900, 6950, 7000])
    curves = wi.load_curves(pattern)
    worn = [int((30_000 + 0.6 * 130_500 + 20_000) * (1 + 0.004 * s)) for s in range(7)]
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000)
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
    ref = wi.loco(curves, FRESH, "ratio", 40_000, cycles=cyc, rate_range=2.0)
    rows, skipped = wi.loco_study(curves, FRESH, "ratio", 40_000, 2.0, cycles=cyc)
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
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000)
    lines = wi.screen({"0000000000000000"}, {0: [], 127: []}, 1, 31_000, worn, r, 1.0, 40_000)
    labeled = [ln for ln in lines if ": " in ln and not ln.startswith(("─", " "))]
    assert {wi._w(ln.split(": ")[0]) for ln in labeled} == {13}      # 한글을 2칸으로 세어 콜론이 같은 자리
    assert lines[-2].startswith("판정") and "확률" in lines[-2] and lines[-1] == "─" * 61
    assert "UID 0000000000000000 (등록부에 없음)" in lines[1] and lines[6].startswith("─")


def test_screen_calls_a_chip_below_the_first_band_new(tmp_path):
    """곡선 첫 구간(1-1,000)보다도 덜 닳은 칩 — 교정 밴드 밖이어도 보류가 아니라 신품이고, 주의 대신 참고 줄이 뜬다."""
    curves = wi.load_curves(synth_curves(tmp_path))
    worn = [25_000] * 7                                          # fastA 첫 구간(약 30.3ms)의 밴드보다 아래
    r = wi.invert(31_000, worn, curves, FRESH, "ms", 40_000)
    lines = wi.screen({"0000000000000000"}, {0: [], 127: []}, 1, 31_000, worn, r, 1.0, 40_000)
    assert any(ln.startswith("참고") and ln.endswith("교정 첫 구간(1-1,000회)보다 덜 닳음") for ln in lines)
    assert not any(ln.startswith("주의") for ln in lines) and lines[-2].startswith("판정") and "신품" in lines[-2]


def test_median_bin_is_the_half_mass_bin():
    """v3 대표값 — 누적 확률이 처음 절반을 넘는 구간. 오른쪽 꼬리가 길면 MAP 보다 뒤에 선다."""
    post = {1: 0.30, 1001: 0.15, 2001: 0.15, 3001: 0.15, 4001: 0.25}
    assert max(post, key=post.get) == 1 and wi.median_bin(post) == 2001
    assert wi.median_bin({5001: 1.0}) == 5001


def test_v3_defaults():
    assert wi.RATE_RANGE == 1.6 and not hasattr(wi, "program_check")
