"""F6: one corrupted payload bit must produce exactly one logged error."""

import cocotb

from flash_spi_test_helpers import (
    drive_prbs_flash,
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
)


# F6 검사: 읽기 2의 한 비트만 뒤집었을 때 e_i와 두 합계가 모두 정확한가
@cocotb.test()
async def test_F6_single_bit_corruption_has_exact_error_counts(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 4
    burst_bits = 64
    injected_read = 2
    injected_bit = 19

    flash_driver = cocotb.start_soon(
        drive_prbs_flash(
            dut,
            n_reads,
            burst_bits,
            inject_read=injected_read,
            inject_bit=injected_bit,
        )
    )

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    observed_frames = await flash_driver

    assert not timed_out, "single-bit corruption must not cause TIMEOUT"
    assert int(dut.meas_busy.value) == 0, "busy remained high after done"
    assert int(dut.spi_cs_n.value) == 1, "CS was not released after measurement"
    assert len(observed_frames) == n_reads, "Flash model did not observe every read"

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    expected_per_read = [0, 0, 1, 0]

    assert per_read == expected_per_read, (
        f"per-read errors={per_read}, expected={expected_per_read}"
    )
    assert int(dut.err_bits.value) == 1, (
        f"err_bits={int(dut.err_bits.value)}, expected 1"
    )
    assert int(dut.err_reads.value) == 1, (
        f"err_reads={int(dut.err_reads.value)}, expected 1"
    )

    # R8 integrity: aggregate outputs must agree with the raw per-read log.
    assert sum(per_read) == int(dut.err_bits.value), "R8-1 sum(e_i) != ERR_BITS"
    assert sum(error_count > 0 for error_count in per_read) == int(
        dut.err_reads.value
    ), "R8-2 count(e_i>0) != ERR_READS"
    assert all(error_count <= burst_bits for error_count in per_read), (
        "R8-3 one or more e_i values exceeded B"
    )

    dut._log.info(
        "F6 single-bit injection: read=%d bit=%d per_read=%s err_bits=%d err_reads=%d",
        injected_read,
        injected_bit,
        per_read,
        int(dut.err_bits.value),
        int(dut.err_reads.value),
    )
