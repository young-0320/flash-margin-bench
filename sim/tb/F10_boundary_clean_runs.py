"""F10: clean runs at the read-count, minimum-burst, and default-burst boundaries."""

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge, with_timeout

from flash_spi_test_helpers import (
    drive_prbs_flash,
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
)


async def collect_log_writes(dut, expected_count: int) -> list[tuple[int, int]]:
    """Observe every receiver write so a clean all-zero buffer cannot hide aliasing."""
    writes = []
    while len(writes) < expected_count:
        await RisingEdge(dut.clk_sample)
        await ReadOnly()
        if int(dut.test_log_we.value):
            writes.append(
                (int(dut.test_log_waddr.value), int(dut.test_log_wdata.value))
            )
    return writes


async def run_clean_boundary(dut, *, n_reads: int, burst_bits: int) -> list[int]:
    """Run one independent clean measurement and return every log entry."""
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
    observed_frames = await flash_driver

    assert not timed_out, (
        f"clean N={n_reads}, B={burst_bits} run unexpectedly timed out"
    )
    assert len(observed_frames) == n_reads, (
        f"observed {len(observed_frames)} frames, expected {n_reads}"
    )
    assert int(dut.meas_busy.value) == 0, "BUSY remained high after clean run"
    assert int(dut.cfg_err.value) == 0, "clean boundary run raised CFG_ERR"
    assert int(dut.spi_cs_n.value) == 1, "CS was not released after clean run"
    assert int(dut.err_bits.value) == 0, "clean boundary run reported ERR_BITS"
    assert int(dut.err_reads.value) == 0, "clean boundary run reported ERR_READS"

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert len(per_read) == n_reads
    assert all(error_count == 0 for error_count in per_read), (
        f"clean N={n_reads}, B={burst_bits} log contains errors"
    )
    assert sum(per_read) == int(dut.err_bits.value), "R8-1 sum(e_i) != ERR_BITS"
    assert sum(error_count > 0 for error_count in per_read) == int(
        dut.err_reads.value
    ), "R8-2 count(e_i>0) != ERR_READS"
    assert all(error_count <= burst_bits for error_count in per_read), (
        "R8-3 one or more e_i values exceeded B"
    )
    return per_read


@cocotb.test()
async def test_F10_N2048_full_log_buffer_is_clean_through_last_entry(dut) -> None:
    """N=2048 must fill, preserve, and expose the complete per-read log."""
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 2048
    burst_bits = 8
    write_monitor = cocotb.start_soon(collect_log_writes(dut, n_reads))
    per_read = await run_clean_boundary(
        dut,
        n_reads=n_reads,
        burst_bits=burst_bits,
    )
    # A broken final write must fail promptly rather than leave the regression
    # waiting forever for an address that will never arrive after DONE.
    observed_writes = await with_timeout(write_monitor, 1, "us")

    assert [address for address, _ in observed_writes] == list(range(n_reads)), (
        "full-buffer log write addresses did not cover 0..2047 exactly once"
    )
    assert all(data == 0 for _, data in observed_writes), (
        "clean full-buffer run attempted to write a nonzero error count"
    )
    assert per_read[0] == 0
    assert per_read[-1] == 0
    dut._log.info(
        "F10 full log: N=%d B=%d entries=%d first=%d last=%d",
        n_reads,
        burst_bits,
        len(per_read),
        per_read[0],
        per_read[-1],
    )


@cocotb.test()
async def test_F10_B8_minimum_burst_is_clean(dut) -> None:
    """The minimum legal burst B=8 must be accepted and complete cleanly."""
    start_clocks(dut)
    await reset_dut(dut)

    per_read = await run_clean_boundary(dut, n_reads=2, burst_bits=8)
    dut._log.info("F10 minimum burst: N=2 B=8 per_read=%s", per_read)


@cocotb.test()
async def test_F10_B2048_default_page_burst_is_clean(dut) -> None:
    """The contract-default one-page burst B=2048 must complete cleanly."""
    start_clocks(dut)
    await reset_dut(dut)

    per_read = await run_clean_boundary(dut, n_reads=2, burst_bits=2048)
    dut._log.info("F10 default burst: N=2 B=2048 per_read=%s", per_read)
