"""F3: prove that each wire address selects the matching PRBS page."""

import os

import cocotb

from flash_spi_test_helpers import (
    monitor_spi_headers,
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
)


VENDOR_MODEL_ENABLED = os.getenv("WINBOND_MODEL_ENABLED") == "1"


@cocotb.test(skip=not VENDOR_MODEL_ENABLED)
async def test_F3_wire_address_selects_matching_vendor_PRBS_page(dut) -> None:
    """Read pages 0..256 and require exact addresses and zero PRBS errors."""
    start_clocks(dut)
    await reset_dut(dut)

    assert int(dut.vendor_model_present.value) == 1, "Winbond model was not compiled"

    # Page 256 crosses byte address 0x00FF00 -> 0x010000.  B=16 includes the
    # complete 15-bit seed, so every page's low seed bits affect the oracle.
    n_reads = 257
    burst_bits = 16
    dut.use_vendor_model.value = 1
    header_monitor = cocotb.start_soon(monitor_spi_headers(dut, n_reads))

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    observed_frames = await header_monitor

    assert not timed_out, "address-to-seed verification caused TIMEOUT"
    assert int(dut.vendor_timing_error.value) == 0, (
        "Winbond model reported a timing violation during F3"
    )
    assert len(observed_frames) == n_reads, (
        f"observed {len(observed_frames)} frames, expected {n_reads}"
    )

    for read_index, frame in enumerate(observed_frames):
        expected_address = read_index * 256
        assert frame["command"] == 0x0B, (
            f"read {read_index}: command=0x{frame['command']:02X}, expected 0x0B"
        )
        assert frame["address"] == expected_address, (
            f"read {read_index}: address=0x{frame['address']:06X}, "
            f"expected page {read_index} at 0x{expected_address:06X}"
        )
        assert frame["dummy"] == 0, (
            f"read {read_index}: dummy=0x{frame['dummy']:02X}, expected 0x00"
        )

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert per_read == [0] * n_reads, (
        "wire address and internal PRBS seed are not aligned: "
        f"per-read errors={per_read}"
    )
    assert int(dut.err_bits.value) == 0, "matching vendor pages produced ERR_BITS"
    assert int(dut.err_reads.value) == 0, "matching vendor pages produced ERR_READS"

    dut._log.info(
        "F3 address-to-seed mapping: pages=0..%d addresses=0x%06X..0x%06X "
        "per_read=%s",
        n_reads - 1,
        observed_frames[0]["address"],
        observed_frames[-1]["address"],
        per_read,
    )
