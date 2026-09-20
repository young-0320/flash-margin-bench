"""S-4 §7 T6 — **채점표가 실패하는 것을 먼저 확인한다.**

가짜 엔진과 채점표를 같은 손이 짰다. 그러면 가짜 엔진이 채점표가 기대하는 대로 동작해
**언제나 통과하는 채점표**가 될 수 있다 — 로그 14 의 `6/6 PASS` 가 그 모양이었고,
박지민도 `docs/log/jimin/3.cocotb_verification_plan.md` §8 에 *"`assert True` 만 적어도
covered 로 잡힌다"* 로 같은 지적을 해 두었다.

그래서 엔진에 버그를 하나씩 심고 **지정한 항목이 반드시 깨지는지** 본다. 깨지지 않으면
그 항목은 아무것도 재고 있지 않은 것이다. 역방향도 집행한다 —
**버그 하나로도 안 깨지는 채점 항목**이 있으면 그 항목이 비어 있는 것이다.
"""

import pytest

import harness as H
import mock_engine as me

# 버그 → (깨져야 하는 항목, 돌릴 사이클 수, 같이 켜야 하는 버그)
CASES = [
    ("undercount",          "A1", 100, ()),
    ("drop_sector_rows",    "A2", 100, ()),
    ("drop_b_row",          "A3", 100, ()),
    ("tally_rewrite",       "A4", 200, ()),        # 100 사이클로는 안 드러난다
    ("tally_single",        "A5", 100, ()),
    ("uid_wrong",           "A7", 100, ()),
    ("no_reerase",          "B",  100, ()),
    ("no_checkpoint_due",   "C",  100, ()),
    ("resume_picks_larger", "resume", 100, ("tally_single",)),
    ("program_check_dead",  "probe", 100, ()),
    ("tally_by_delta",      "J",   100, ()),        # 한 구간짜리 A1~A5 로는 안 드러난다
]


@pytest.mark.parametrize("bug, item, cycles, extra", CASES)
def test_bug_is_caught(bug, item, cycles, extra):
    H.score(item, cycles=cycles, bugs=set(extra))              # 정상 엔진은 통과하고
    with pytest.raises(AssertionError):                        # 버그 엔진에서는 깨진다
        H.score(item, cycles=cycles, bugs={bug, *extra})


def test_every_bug_has_a_case():
    """버그 목록과 이 파일이 어긋나면 잡히지 않는 버그가 생긴다."""
    assert {b for b, *_ in CASES} == set(me.BUGS), (
        f"케이스 없는 버그: {set(me.BUGS) - {b for b, *_ in CASES}}")


def test_every_score_item_has_a_bug():
    """T6 의 **역방향** — 버그 하나로도 안 깨지는 채점 항목은 비어 있는 항목이다."""
    assert set(H.SCORE) == {item for _, item, *_ in CASES}, (
        f"버그 케이스 없는 채점 항목: {set(H.SCORE) - {i for _, i, *_ in CASES}}")
