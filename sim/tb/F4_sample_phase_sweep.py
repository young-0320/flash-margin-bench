"""F4: sweep clk_sample across one full UI without a framing cliff."""

import cocotb

from flash_spi_test_helpers import (
    drive_prbs_flash,
    read_error_log,
    reset_dut,
    start_clocks_with_sample_phase,
    start_measurement,
    wait_for_done,
)


# Densify the old 3 ns smoke grid to 0.5 ns and add near-boundary probes.
# Exact 0/40 ns coincide with clk_core edges and are the same phase modulo one UI;
# 0.1/39.9 ns probe both sides without simulator delta-cycle ambiguity.
PHASE_POINTS_NS = (
    [0.1]
    + [0.5 * index for index in range(1, 80)]
    + [39.9]
)


@cocotb.test()
@cocotb.parametrize(sample_phase_ns=PHASE_POINTS_NS)
async def test_F4_full_UI_sample_phase_has_no_framing_cliff(
    dut, sample_phase_ns: float
) -> None:
    """Require a clean PRBS result at each sampled phase in one 40 ns UI."""
    start_clocks_with_sample_phase(dut, sample_phase_ns)
    await reset_dut(dut)

    n_reads = 2
    burst_bits = 64
    flash_driver = cocotb.start_soon(
        drive_prbs_flash(
            dut,
            n_reads=n_reads,
            burst_bits=burst_bits,
            output_delay_ns=8,
        )
    )

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    await flash_driver

    assert not timed_out, f"phase {sample_phase_ns}ns caused TIMEOUT"
    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert per_read == [0] * n_reads, (
        f"phase {sample_phase_ns}ns caused a framing cliff: {per_read}"
    )
    assert int(dut.err_bits.value) == 0, (
        f"phase {sample_phase_ns}ns produced ERR_BITS={int(dut.err_bits.value)}"
    )
    assert int(dut.err_reads.value) == 0, (
        f"phase {sample_phase_ns}ns produced ERR_READS={int(dut.err_reads.value)}"
    )

    dut._log.info(
        "F4 phase %.1fns/40ns UI clean: per_read=%s",
        sample_phase_ns,
        per_read,
    )
