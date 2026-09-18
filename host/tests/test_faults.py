"""S-4 §3 주입 고장. 엔진은 정상이고 환경이 나쁘다 — 채점표가 시끄러운가."""

from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

import harness as H
import host_side as hs
import mock_engine as me

PHASES = ["program", "erase", "tally", "between"]


# ── §3.1 중단 ─────────────────────────────────────────────────────────────
@settings(max_examples=200, deadline=None)
@given(cut=st.integers(1, 100), phase=st.sampled_from(PHASES))
def test_B_power_cut_any_moment(cut, phase):
    """§13 B — **임의 시점** 전원 차단 → 복원값과 실제 진행의 차이 ≤ 100.

    시점을 나열하지 않고 성질을 적는다. `worn_cycles` 는 채점표가 볼 수 없는 정답이다.
    """
    r = H.run(faults={"power_cut"}, cut_at=cut, cut_phase=phase)
    info = me.MockEngine(r.chip, me.Link()).wear_resume()
    verdict, restored = hs.decide_resume(info, r.log.max_cycle)
    assert verdict != hs.HALT_CALL_HUMAN, f"정상 차단인데 사람을 불렀다 ({cut}/{phase})"
    assert abs(restored - r.chip.worn_cycles) <= 100, (
        f"복원 {restored} vs 실제 {r.chip.worn_cycles} ({cut}/{phase})")


def test_host_death_is_seen():
    """호스트만 죽으면 tally 가 앞선다 — 「큰 쪽 채택」이 아니라 결손으로 읽혀야 한다."""
    r = H.run(faults={"host_death"})
    info = me.MockEngine(r.chip, me.Link()).wear_resume()
    verdict, restored = hs.decide_resume(info, r.log.max_cycle)
    assert verdict == hs.HOST_DIED
    assert restored == 100 and len(r.log.a) == 0


def test_spi_dead_halts_and_calls_human():
    """마모가 안 됐는데 행만 온 경우. 「큰 쪽 채택」이면 X축이 과대 계상된다."""
    r = H.run(faults={"spi_dead"})
    info = me.MockEngine(r.chip, me.Link()).wear_resume()
    verdict, _ = hs.decide_resume(info, r.log.max_cycle)
    assert verdict == hs.HALT_CALL_HUMAN, "실제 마모 0 인데 100 으로 넘어갔다"
    assert r.chip.worn_cycles == 0


def test_board_hang_raises():
    with pytest.raises(TimeoutError):
        H.run(faults={"board_hang"})


def test_link_drop_loses_rows_and_A5_catches_it():
    """연결이 끊긴 구간의 행은 영영 없다 — A5 가 어긋남을 봐야 한다."""
    r = H.run(faults={"link_drop"})
    assert r.link.dropped > 0
    with pytest.raises(AssertionError, match="A5|A2"):
        H.check_A5(r)


# ── §3.2 전송 손상 ────────────────────────────────────────────────────────
def test_garbage_prefix_is_tolerated():
    """앞 쓰레기 바이트는 버리지 않는다 — `sweep_uart_capture.py:164` 와 같은 처리."""
    r = H.run(faults={"garbage_prefix"})
    H.check_A2(r)
    assert r.log.rejected == []


@pytest.mark.parametrize("fault", ["truncate", "glue", "bitflip"])
def test_transport_damage_is_rejected_not_counted(fault):
    """깨진 행을 세면 A2 가 틀린 답을 낸다. 세지 않고 거부해야 한다."""
    r = H.run(faults={fault})
    assert r.log.rejected, f"{fault} 가 그대로 통과했다"
    with pytest.raises(AssertionError, match="A2"):
        H.check_A2(r)


def test_buffer_overflow_shows_up_as_loss():
    r = H.run(faults={"buffer_overflow"})
    assert r.link.dropped > 0
    with pytest.raises(AssertionError, match="A2"):
        H.check_A2(r)


def test_every_fault_has_a_case():
    """S-4 §7 T2 의 집행 장치. `BUGS` 에는 있는데 `FAULTS` 에는 없었다.

    목록과 케이스가 어긋나면 **주입한다고 적어 두고 안 하는 항목**이 생긴다.
    """
    src = "".join(
        (Path(__file__).parent / f).read_text()
        for f in ("test_acceptance.py", "test_faults.py", "test_tb_catches_bugs.py"))
    missing = {f for f in me.FAULTS if f'"{f}"' not in src and f"'{f}'" not in src}
    assert not missing, f"케이스 없는 fault: {sorted(missing)}"
