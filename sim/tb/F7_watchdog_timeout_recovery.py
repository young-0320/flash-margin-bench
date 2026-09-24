"""F7: R10 exact watchdog deadline, safe termination, and recovery."""

import cocotb
from cocotb.triggers import FallingEdge, ReadOnly

from flash_spi_test_helpers import (
    drive_prbs_flash,
    read_error_log,
    reset_dut,
    sample_after_rising_edge,
    start_clocks,
    start_measurement,
    wait_for_done,
)


@cocotb.test()
async def test_F7_blocked_done_times_out_at_exact_Tmax_and_recovers(dut) -> None:
    """Block rx_done, require exact R10 termination, then complete a clean run."""
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 2
    burst_bits = 64
    t_max_cycles = 2 * n_reads * (burst_bits + 64)

    dut.block_rx_done.value = 1
    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)

    timeout_cycle = None
    for elapsed_cycles in range(1, t_max_cycles + 1):
        await sample_after_rising_edge(dut)
        if int(dut.meas_done.value):
            timeout_cycle = elapsed_cycles
            break

    assert timeout_cycle == t_max_cycles, (
        f"watchdog completed at cycle {timeout_cycle}, expected exactly "
        f"T_max={t_max_cycles}"
    )
    assert int(dut.test_wd_cnt.value) == t_max_cycles, (
        f"internal watchdog count={int(dut.test_wd_cnt.value)}, "
        f"expected {t_max_cycles}"
    )
    assert int(dut.meas_done.value) == 1, "R10 must emit DONE on forced termination"
    assert int(dut.meas_timeout.value) == 1, (
        "R10 TIMEOUT must pulse in the same cycle as DONE"
    )
    assert int(dut.meas_busy.value) == 0, "BUSY did not drop on watchdog termination"
    assert int(dut.cfg_err.value) == 0, "watchdog fault was misreported as CFG_ERR"

    # Check the physical outputs after the current forwarded-clock half-cycle.
    await FallingEdge(dut.clk_core)
    await ReadOnly()
    assert int(dut.spi_cs_n.value) == 1, "watchdog did not release CS"
    assert int(dut.spi_sclk.value) == 0, "watchdog did not return SCLK low"

    # DONE and TIMEOUT are one-cycle pulses at the flash-block interface.
    await sample_after_rising_edge(dut)
    assert int(dut.meas_done.value) == 0, "DONE lasted longer than one core cycle"
    assert int(dut.meas_timeout.value) == 0, (
        "TIMEOUT lasted longer than one core cycle"
    )

    dut.block_rx_done.value = 0
    for _ in range(6):
        await sample_after_rising_edge(dut)
    assert int(dut.test_rx_done_s.value) == 0, (
        "released completion path did not return to idle before recovery run"
    )

    # A timeout must not leave the controller or receiver wedged. Run the same
    # legal measurement again with a clean independent SPI responder.
    flash_driver = cocotb.start_soon(
        drive_prbs_flash(
            dut,
            n_reads=n_reads,
            burst_bits=burst_bits,
            output_delay_ns=8,
        )
    )
    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(dut, max_core_cycles=t_max_cycles + 200)
    await flash_driver

    assert not timed_out, "first legal run after watchdog termination timed out"
    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert per_read == [0, 0], f"recovery run produced PRBS errors: {per_read}"
    assert int(dut.err_bits.value) == 0
    assert int(dut.err_reads.value) == 0
    assert int(dut.meas_busy.value) == 0
    assert int(dut.spi_cs_n.value) == 1

    dut._log.info(
        "F7 exact watchdog: T_max=%d cycles, DONE+TIMEOUT pulse, recovery clean",
        t_max_cycles,
    )
