"""F2: verify wire-level SPI mode-0 timing and Winbond model assertions."""

import os

import cocotb
from cocotb.triggers import Timer

from flash_spi_test_helpers import (
    drive_prbs_flash,
    monitor_mode0_timing,
    prbs15_bits,
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
)


VENDOR_MODEL_ENABLED = os.getenv("WINBOND_MODEL_ENABLED") == "1"


# F2 wire 검사: CS 양끝에서 SCLK low, tSLCH와 tSHSL1 최소시간을 지키는가
@cocotb.test()
async def test_F2_wire_mode0_CS_and_SCLK_timing(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 3
    burst_bits = 64
    flash_driver = cocotb.start_soon(
        drive_prbs_flash(dut, n_reads=n_reads, burst_bits=burst_bits)
    )
    timing_monitor = cocotb.start_soon(
        monitor_mode0_timing(dut, n_reads, 40 + burst_bits)
    )

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    await flash_driver
    observations = await timing_monitor

    assert not timed_out, "valid mode-0 transaction must not cause TIMEOUT"
    assert len(observations) == n_reads, "timing monitor missed an SPI frame"

    dut._log.info("F2 wire timing: %s", observations)


# F2 vendor 검사: 공식 모델의 실제 응답과 timing_error 무발화를 함께 확인한다.
@cocotb.test(skip=not VENDOR_MODEL_ENABLED)
async def test_F2_vendor_model_timing_assertions_have_no_violations(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    assert int(dut.vendor_model_present.value) == 1, "Winbond model was not compiled"
    assert int(dut.vendor_timing_error.value) == 0, (
        "Winbond timing_error was already set before the test"
    )
    page0_bits = prbs15_bits(0, 16)
    page1_bits = prbs15_bits(1, 16)
    expected_page0_byte0 = sum(
        bit << (7 - index) for index, bit in enumerate(page0_bits[0:8])
    )
    expected_page0_byte1 = sum(
        bit << (7 - index) for index, bit in enumerate(page0_bits[8:16])
    )
    expected_page1_byte0 = sum(
        bit << (7 - index) for index, bit in enumerate(page1_bits[0:8])
    )
    expected_page1_byte1 = sum(
        bit << (7 - index) for index, bit in enumerate(page1_bits[8:16])
    )
    assert expected_page0_byte1 != expected_page1_byte1, (
        "chosen memory probes must distinguish page 0 from page 1"
    )
    assert int(dut.vendor_mem_page0_byte0.value) == expected_page0_byte0, (
        "Winbond MEM.TXT page 0 was not loaded with the prepared PRBS data"
    )
    assert int(dut.vendor_mem_page0_byte1.value) == expected_page0_byte1, (
        "Winbond MEM.TXT page 0 byte 1 does not match its PRBS seed"
    )
    assert int(dut.vendor_mem_page1_byte0.value) == expected_page1_byte0, (
        "Winbond MEM.TXT page 1 was not loaded with the prepared PRBS data"
    )
    assert int(dut.vendor_mem_page1_byte1.value) == expected_page1_byte1, (
        "Winbond MEM.TXT page 1 byte 1 does not match its distinct PRBS seed"
    )

    n_reads = 3
    burst_bits = 64
    dut.use_vendor_model.value = 1
    timing_monitor = cocotb.start_soon(
        monitor_mode0_timing(dut, n_reads, 40 + burst_bits)
    )

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    observations = await timing_monitor

    assert not timed_out, "Winbond-backed transaction caused TIMEOUT"
    assert int(dut.vendor_timing_error.value) == 0, (
        "Winbond model reported a timing violation"
    )

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert per_read == [0] * n_reads, (
        f"Winbond model did not return the prepared PRBS data: {per_read}"
    )
    assert int(dut.err_bits.value) == 0, "Winbond-backed clean read produced ERR_BITS"
    assert int(dut.err_reads.value) == 0, "Winbond-backed clean read produced ERR_READS"

    dut._log.info("F2 Winbond timing clean: %s", observations)


@cocotb.test(skip=not VENDOR_MODEL_ENABLED)
async def test_F2_vendor_timing_guard_detects_deliberate_short_clock(dut) -> None:
    """Prove the model's timing guard can turn a known-bad pulse into an error."""
    start_clocks(dut)
    await reset_dut(dut)

    assert int(dut.vendor_model_present.value) == 1, "Winbond model was not compiled"
    assert int(dut.vendor_timing_error.value) == 0, (
        "timing_error was set before the deliberate negative control"
    )

    dut.use_timing_probe.value = 1
    dut.timing_probe_cs_n.value = 0
    dut.timing_probe_clk.value = 0
    dut.timing_probe_dio.value = 0
    await Timer(5, unit="ns")

    # The official model requires at least 45% of the measured clock period
    # for the high pulse.  A 2 ns high pulse is intentionally invalid.
    dut.timing_probe_clk.value = 1
    await Timer(2, unit="ns")
    dut.timing_probe_clk.value = 0
    await Timer(2, unit="ns")

    assert int(dut.vendor_timing_error.value) == 1, (
        "Winbond timing guard did not detect the deliberate 2 ns high pulse"
    )
    dut.timing_probe_cs_n.value = 1
    dut.use_timing_probe.value = 0
    dut._log.info("F2 negative control: deliberate 2ns SCLK high pulse detected")
