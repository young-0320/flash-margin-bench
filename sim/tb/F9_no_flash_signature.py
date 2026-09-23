"""F9: recognize the error signature produced by an unresponsive Flash MISO."""

import cocotb

from flash_spi_test_helpers import (
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
    zero_miso_error_count,
)


# F9 검사: MISO가 0으로 고정돼도 timeout 없이 끝나고 PRBS 오류를 정확히 세는가
@cocotb.test()
async def test_F9_MISO_stuck_low_reports_exact_PRBS_errors_without_timeout(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 2
    burst_bits = 2048
    expected_per_read = [
        zero_miso_error_count(page_index, burst_bits)
        for page_index in range(n_reads)
    ]
    expected_total = sum(expected_per_read)

    # No Flash drives MISO: the board pulldown leaves the sampled input at zero.
    dut.spi_miso.value = 0
    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(dut, max_core_cycles=9000)

    assert not timed_out, "unresponsive MISO must finish as data errors, not TIMEOUT"
    assert int(dut.meas_busy.value) == 0, "busy remained high after done"
    assert int(dut.spi_cs_n.value) == 1, "CS was not released after measurement"
    assert int(dut.err_bits.value) == expected_total, (
        f"err_bits={int(dut.err_bits.value)}, expected aligned PRBS ones={expected_total}"
    )
    assert int(dut.err_reads.value) == n_reads, (
        f"err_reads={int(dut.err_reads.value)}, expected {n_reads}"
    )

    actual_per_read = [
        await read_error_log(dut, read_index) for read_index in range(n_reads)
    ]
    assert actual_per_read == expected_per_read, (
        f"per-read errors={actual_per_read}, expected={expected_per_read}"
    )

    dut._log.info(
        "F9 no-Flash signature: err_bits=%d, per_read=%s",
        expected_total,
        expected_per_read,
    )
