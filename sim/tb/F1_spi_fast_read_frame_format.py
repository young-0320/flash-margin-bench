"""F1: decode each physical SPI frame and verify the 0x0B read format."""

import cocotb

from flash_spi_test_helpers import (
    drive_prbs_flash,
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
)


# F1 검사: wire에서 cmd, 주소, dummy, 프레임 SCLK 개수를 직접 확인하는가
@cocotb.test()
async def test_F1_decode_0x0B_address_dummy_and_exact_frame_length(dut) -> None:
    start_clocks(dut)
    await reset_dut(dut)

    n_reads = 3
    burst_bits = 64
    expected_sclk_edges = 40 + burst_bits

    flash_driver = cocotb.start_soon(
        drive_prbs_flash(dut, n_reads=n_reads, burst_bits=burst_bits)
    )

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )
    observed_frames = await flash_driver

    assert not timed_out, "valid 0x0B frames must not cause TIMEOUT"
    assert len(observed_frames) == n_reads, (
        f"observed {len(observed_frames)} frames, expected {n_reads}"
    )

    for read_index, frame in enumerate(observed_frames):
        expected_address = read_index * 256
        assert frame["command"] == 0x0B, (
            f"frame {read_index}: command=0x{frame['command']:02X}, expected 0x0B"
        )
        assert frame["address"] == expected_address, (
            f"frame {read_index}: address=0x{frame['address']:06X}, "
            f"expected 0x{expected_address:06X}"
        )
        assert frame["address"] & 0xFF == 0, (
            f"frame {read_index}: address low byte was not zero"
        )
        assert frame["dummy"] == 0, (
            f"frame {read_index}: dummy byte=0x{frame['dummy']:02X}, expected 0x00"
        )
        assert frame["sclk_edges"] == expected_sclk_edges, (
            f"frame {read_index}: SCLK edges={frame['sclk_edges']}, "
            f"expected {expected_sclk_edges}"
        )

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    assert per_read == [0] * n_reads, f"clean frame produced errors: {per_read}"
    assert int(dut.err_bits.value) == 0, "clean frame produced ERR_BITS"
    assert int(dut.err_reads.value) == 0, "clean frame produced ERR_READS"

    dut._log.info(
        "F1 frames: %s",
        [
            (
                f"cmd=0x{frame['command']:02X} "
                f"addr=0x{frame['address']:06X} "
                f"dummy=0x{frame['dummy']:02X} "
                f"sclk={frame['sclk_edges']}"
            )
            for frame in observed_frames
        ],
    )
