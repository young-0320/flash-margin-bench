"""F5: sweep the official model's effective MISO output-path delay."""

import cocotb
from cocotb.triggers import FallingEdge

from flash_spi_test_helpers import (
    read_error_log,
    reset_dut,
    start_clocks_with_sample_phase,
    start_measurement,
    wait_for_done,
)


MODEL_TCLQV_NS = 6
UI_NS = 40
PHASE_POINTS_NS = [0.1] + [0.5 * index for index in range(1, 80)] + [39.9]


def _require_vendor_model(dut) -> None:
    if not int(dut.vendor_model_present.value):
        cocotb.skip("F5 requires WINBOND_MODEL_DIR and the official W25Q64JV model")


async def _run_vendor_measurement(
    dut, *, sample_phase_ns: float, extra_delay_ns: int, burst_bits: int
) -> list[int]:
    start_clocks_with_sample_phase(dut, sample_phase_ns)
    await reset_dut(dut)
    _require_vendor_model(dut)

    dut.vendor_extra_delay_ns.value = extra_delay_ns
    dut.use_vendor_model.value = 1
    await FallingEdge(dut.clk_core)

    n_reads = 2
    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut, max_core_cycles=2 * n_reads * (burst_bits + 64) + 200
    )
    assert not timed_out, (
        f"phase={sample_phase_ns}ns extra_delay={extra_delay_ns}ns caused TIMEOUT"
    )
    return [await read_error_log(dut, index) for index in range(n_reads)]


@cocotb.test()
@cocotb.parametrize(extra_delay_ns=[0, 4, 8, 12, 16, 20, 24, 28, 32])
async def test_F5_vendor_effective_delay_below_one_UI_stays_error_free(
    dut, extra_delay_ns: int
):
    """F5: effective delay 6..38ns (<40ns UI) must retain an error-free floor."""
    per_read = await _run_vendor_measurement(
        dut,
        sample_phase_ns=10.0,
        extra_delay_ns=extra_delay_ns,
        burst_bits=64,
    )
    effective_delay_ns = MODEL_TCLQV_NS + extra_delay_ns
    assert effective_delay_ns < UI_NS
    assert per_read == [0, 0], (
        f"effective delay={effective_delay_ns}ns (<1UI) produced {per_read}"
    )
    assert int(dut.err_bits.value) == 0
    assert int(dut.err_reads.value) == 0
    dut._log.info(
        "F5 sub-UI clean: model_tCLQV=%dns path=%dns effective=%dns",
        MODEL_TCLQV_NS,
        extra_delay_ns,
        effective_delay_ns,
    )


@cocotb.test()
async def test_F5_just_over_one_UI_exposes_the_shifted_error_wall(dut):
    """F5: 50ns is no longer universally clean at the original phase."""
    burst_bits = 512
    extra_delay_ns = 44
    per_read = await _run_vendor_measurement(
        dut,
        sample_phase_ns=0.1,
        extra_delay_ns=extra_delay_ns,
        burst_bits=burst_bits,
    )
    effective_delay_ns = MODEL_TCLQV_NS + extra_delay_ns
    assert effective_delay_ns > UI_NS
    lower = int(burst_bits * 0.35)
    upper = int(burst_bits * 0.60)
    assert all(lower <= errors <= upper for errors in per_read), (
        f"phase=0.1ns effective delay={effective_delay_ns}ns did not expose "
        f"the shifted error wall: {per_read}"
    )
    assert int(dut.err_reads.value) == 2
    assert int(dut.err_bits.value) == sum(per_read)
    dut._log.info(
        "F5 just-over-UI wall: phase=0.1ns effective=%dns per_read=%s",
        effective_delay_ns,
        per_read,
    )


@cocotb.test()
@cocotb.parametrize(sample_phase_ns=PHASE_POINTS_NS)
async def test_F5_beyond_three_candidate_span_has_no_false_zero_error_floor(
    dut, sample_phase_ns: float
):
    """F5: beyond the +/-1-bit candidate span, every phase must fail loudly."""
    burst_bits = 512
    extra_delay_ns = 84
    per_read = await _run_vendor_measurement(
        dut,
        sample_phase_ns=sample_phase_ns,
        extra_delay_ns=extra_delay_ns,
        burst_bits=burst_bits,
    )
    effective_delay_ns = MODEL_TCLQV_NS + extra_delay_ns
    assert effective_delay_ns > 2 * UI_NS

    # The receiver reports min(e0,e1,e2), so a finite PRBS record need not be
    # exactly 0.5.  Once the fixed displacement exceeds both one-UI correction
    # candidates, no sample phase may masquerade as a zero-error bathtub floor.
    lower = int(burst_bits * 0.35)
    upper = int(burst_bits * 0.60)
    assert all(lower <= errors <= upper for errors in per_read), (
        f"phase={sample_phase_ns}ns effective delay={effective_delay_ns}ns "
        f"did not show saturated PRBS errors: {per_read}"
    )
    assert int(dut.err_reads.value) == 2
    assert int(dut.err_bits.value) == sum(per_read)
    dut._log.info(
        "F5 outside candidate span: phase=%.1fns effective=%dns per_read=%s",
        sample_phase_ns,
        effective_delay_ns,
        per_read,
    )
