"""F8: reject invalid N/B settings and accept a later valid START."""

import cocotb
from cocotb.triggers import FallingEdge

from flash_spi_test_helpers import reset_dut, sample_after_rising_edge, start_clocks


async def _try_rejected_start(dut, n_reads: int, burst_bits: int, label: str) -> None:
    """Issue one invalid START and verify a one-cycle cfg_err-only rejection."""
    await FallingEdge(dut.clk_core)
    dut.cfg_n_reads.value = n_reads
    dut.cfg_burst_bits.value = burst_bits
    dut.meas_start.value = 1

    await sample_after_rising_edge(dut)
    dut.meas_start.value = 0

    assert int(dut.cfg_err.value) == 1, f"{label}: cfg_err did not pulse"
    assert int(dut.meas_busy.value) == 0, f"{label}: busy rose for rejected START"
    assert int(dut.meas_done.value) == 0, f"{label}: done rose for rejected START"
    assert int(dut.meas_timeout.value) == 0, f"{label}: timeout rose for rejected START"

    cfg_err_pulses = 1
    for _ in range(3):
        await sample_after_rising_edge(dut)
        cfg_err_pulses += int(dut.cfg_err.value)
        assert int(dut.meas_busy.value) == 0, f"{label}: busy rose after rejection"
        assert int(dut.meas_done.value) == 0, f"{label}: done rose after rejection"
        assert int(dut.meas_timeout.value) == 0, f"{label}: timeout rose after rejection"

    assert cfg_err_pulses == 1, f"{label}: cfg_err was not a one-cycle pulse"


# F8 검사: 잘못된 N/B 설정 3종을 거부하고 다음 정상 START를 받아들이는가
@cocotb.test()
async def test_F8_reject_invalid_N_B_and_accept_valid_recovery(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    assert int(dut.meas_busy.value) == 0, "reset: busy must be low"
    assert int(dut.meas_done.value) == 0, "reset: done must be low"
    assert int(dut.cfg_err.value) == 0, "reset: cfg_err must be low"

    await _try_rejected_start(dut, n_reads=0, burst_bits=64, label="N=0")
    await _try_rejected_start(dut, n_reads=4, burst_bits=4, label="B<8")
    await _try_rejected_start(dut, n_reads=4, burst_bits=100, label="B%8!=0")

    # Recovery check: a valid request after the three rejections must be accepted.
    await FallingEdge(dut.clk_core)
    dut.cfg_n_reads.value = 1
    dut.cfg_burst_bits.value = 8
    dut.meas_start.value = 1

    await sample_after_rising_edge(dut)
    dut.meas_start.value = 0

    assert int(dut.cfg_err.value) == 0, "valid START was incorrectly rejected"
    assert int(dut.meas_busy.value) == 1, "valid START did not enter the busy state"
    assert int(dut.meas_done.value) == 0, "valid START completed too early"
    assert int(dut.meas_timeout.value) == 0, "valid START timed out immediately"
