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
    assert "빠른 무리" in wi.program_check(program, "fast")
    assert "어긋난다" in wi.program_check(program, "slow")
