"""Shared clock, reset, measurement, and PRBS helpers for Flash SPI tests."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, First, ReadOnly, RisingEdge, Timer
from cocotb.utils import get_sim_time


CORE_PERIOD_NS = 40


def start_clocks(dut) -> None:
    cocotb.start_soon(Clock(dut.clk_core, CORE_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(Clock(dut.clk_sample, CORE_PERIOD_NS, unit="ns").start())


async def _start_clock_after_phase(signal, phase_ns: float) -> None:
    """Start a 25 MHz clock after a one-time phase offset."""
    signal.value = 0
    await Timer(phase_ns, unit="ns")
    await Clock(signal, CORE_PERIOD_NS, unit="ns").start()


def start_clocks_with_sample_phase(dut, sample_phase_ns: float) -> None:
    """Start clk_sample as a phase-delayed copy of clk_core."""
    cocotb.start_soon(Clock(dut.clk_core, CORE_PERIOD_NS, unit="ns").start())
    cocotb.start_soon(_start_clock_after_phase(dut.clk_sample, sample_phase_ns))


async def sample_after_rising_edge(dut) -> None:
    """Sample after sequential logic has updated for the current clock edge."""
    await RisingEdge(dut.clk_core)
    await Timer(1, unit="ns")


async def reset_dut(dut) -> None:
    dut.rstn.value = 0
    dut.meas_start.value = 0
    dut.cfg_n_reads.value = 4
    dut.cfg_burst_bits.value = 64
    dut.log_rd_addr.value = 0
    dut.spi_miso.value = 0
    if hasattr(dut, "use_vendor_model"):
        dut.use_vendor_model.value = 0
    if hasattr(dut, "vendor_extra_delay_ns"):
        dut.vendor_extra_delay_ns.value = 0
    if hasattr(dut, "block_rx_done"):
        dut.block_rx_done.value = 0
    if hasattr(dut, "vendor_command_xor_mask"):
        dut.vendor_command_xor_mask.value = 0
    if hasattr(dut, "force_vendor_miso_low"):
        dut.force_vendor_miso_low.value = 0
    if hasattr(dut, "use_timing_probe"):
        dut.use_timing_probe.value = 0
        dut.timing_probe_cs_n.value = 1
        dut.timing_probe_clk.value = 0
        dut.timing_probe_dio.value = 0

    for _ in range(3):
        await sample_after_rising_edge(dut)

    dut.rstn.value = 1
    await sample_after_rising_edge(dut)


async def start_measurement(dut, n_reads: int, burst_bits: int) -> None:
    """Apply a valid configuration and pulse START for one core clock."""
    await FallingEdge(dut.clk_core)
    dut.cfg_n_reads.value = n_reads
    dut.cfg_burst_bits.value = burst_bits
    dut.meas_start.value = 1

    await sample_after_rising_edge(dut)
    dut.meas_start.value = 0

    assert int(dut.cfg_err.value) == 0, "valid START was rejected"
    assert int(dut.meas_busy.value) == 1, "valid START did not enter busy"


async def wait_for_done(dut, max_core_cycles: int) -> bool:
    """Wait for the one-cycle done pulse and return whether timeout accompanied it."""
    for _ in range(max_core_cycles):
        await sample_after_rising_edge(dut)
        if int(dut.meas_done.value):
            return bool(int(dut.meas_timeout.value))
    raise AssertionError(f"measurement did not finish within {max_core_cycles} core cycles")


async def read_error_log(dut, read_index: int) -> int:
    """Read one synchronous entry from the per-read error log."""
    await FallingEdge(dut.clk_core)
    dut.log_rd_addr.value = read_index
    await sample_after_rising_edge(dut)
    return int(dut.log_rd_data.value)


def prbs15_bits(page_index: int, bit_count: int) -> list[int]:
    """Generate bits using the exact MSB-first rule from flash_prbs15.v."""
    lfsr = (1 << 14) | (page_index & 0x3FFF)
    bits = []
    for _ in range(bit_count):
        bits.append((lfsr >> 14) & 1)
        feedback = ((lfsr >> 14) ^ (lfsr >> 13)) & 1
        lfsr = ((lfsr << 1) & 0x7FFF) | feedback
    return bits


def zero_miso_error_count(page_index: int, bit_count: int) -> int:
    """Predict e_i=min(e0,e1,e2) when every captured MISO bit is zero."""
    # Constant-zero input cannot identify the true framing candidate. The RTL
    # therefore reports the minimum PRBS-one count across its three B-bit windows.
    bits = prbs15_bits(page_index, bit_count + 2)
    return min(sum(bits[offset : offset + bit_count]) for offset in range(3))


def bits_to_int(bits: list[int]) -> int:
    """Convert an MSB-first bit list into an integer."""
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return value


async def count_sclk_rising_edges_until_cs_release(dut) -> int:
    """Count physical SCLK rising edges in the current active-low CS frame."""
    edge_count = 0
    while True:
        await First(RisingEdge(dut.spi_sclk), RisingEdge(dut.spi_cs_n))
        if int(dut.spi_cs_n.value):
            return edge_count
        edge_count += 1


async def monitor_mode0_timing(
    dut, n_frames: int, expected_sclk_edges: int | None = None
) -> list[dict[str, float]]:
    """Measure CS/SCLK mode-0 timing directly at the DUT pins."""
    observations = []
    previous_cs_release_ns = None

    for frame_index in range(n_frames):
        await FallingEdge(dut.spi_cs_n)
        cs_assert_ns = float(get_sim_time(unit="ns"))
        await ReadOnly()
        assert int(dut.spi_sclk.value) == 0, (
            f"frame {frame_index}: SCLK was not low when CS asserted"
        )

        cs_high_gap_ns = None
        if previous_cs_release_ns is not None:
            cs_high_gap_ns = cs_assert_ns - previous_cs_release_ns
            assert cs_high_gap_ns >= 10.0, (
                f"frame {frame_index}: CS high gap={cs_high_gap_ns}ns, expected >=10ns"
            )

        await RisingEdge(dut.spi_sclk)
        first_sclk_rise_ns = float(get_sim_time(unit="ns"))
        cs_to_first_sclk_ns = first_sclk_rise_ns - cs_assert_ns
        assert cs_to_first_sclk_ns >= 5.0, (
            f"frame {frame_index}: CS-to-first-SCLK={cs_to_first_sclk_ns}ns, "
            "expected >=5ns"
        )

        last_sclk_rise_ns = first_sclk_rise_ns
        min_sclk_high_ns = None
        min_sclk_low_ns = None
        min_sclk_period_ns = None

        if expected_sclk_edges is not None:
            for edge_index in range(expected_sclk_edges):
                await FallingEdge(dut.spi_sclk)
                falling_ns = float(get_sim_time(unit="ns"))
                high_ns = falling_ns - last_sclk_rise_ns
                min_sclk_high_ns = (
                    high_ns
                    if min_sclk_high_ns is None
                    else min(min_sclk_high_ns, high_ns)
                )
                assert high_ns >= 18.0, (
                    f"frame {frame_index}: SCLK high={high_ns}ns, expected >=18ns"
                )

                if edge_index == expected_sclk_edges - 1:
                    break

                await RisingEdge(dut.spi_sclk)
                rising_ns = float(get_sim_time(unit="ns"))
                low_ns = rising_ns - falling_ns
                period_ns = rising_ns - last_sclk_rise_ns
                min_sclk_low_ns = (
                    low_ns
                    if min_sclk_low_ns is None
                    else min(min_sclk_low_ns, low_ns)
                )
                min_sclk_period_ns = (
                    period_ns
                    if min_sclk_period_ns is None
                    else min(min_sclk_period_ns, period_ns)
                )
                assert low_ns >= 18.0, (
                    f"frame {frame_index}: SCLK low={low_ns}ns, expected >=18ns"
                )
                assert period_ns >= 40.0, (
                    f"frame {frame_index}: SCLK period={period_ns}ns, expected >=40ns"
                )
                last_sclk_rise_ns = rising_ns

        await RisingEdge(dut.spi_cs_n)
        cs_release_ns = float(get_sim_time(unit="ns"))
        await ReadOnly()
        assert int(dut.spi_sclk.value) == 0, (
            f"frame {frame_index}: SCLK was not low when CS released"
        )
        last_sclk_to_cs_ns = cs_release_ns - last_sclk_rise_ns
        assert last_sclk_to_cs_ns >= 3.0, (
            f"frame {frame_index}: last-SCLK-to-CS={last_sclk_to_cs_ns}ns, "
            "expected >=3ns"
        )

        observations.append(
            {
                "frame": frame_index,
                "cs_to_first_sclk_ns": cs_to_first_sclk_ns,
                "cs_high_gap_ns": cs_high_gap_ns,
                "min_sclk_high_ns": min_sclk_high_ns,
                "min_sclk_low_ns": min_sclk_low_ns,
                "min_sclk_period_ns": min_sclk_period_ns,
                "last_sclk_to_cs_ns": last_sclk_to_cs_ns,
            }
        )
        previous_cs_release_ns = cs_release_ns

    return observations


async def monitor_spi_headers(dut, n_frames: int) -> list[dict[str, int]]:
    """Decode command, address, and dummy byte without driving MISO.

    This observer is used with the official Flash model.  It watches only the
    physical MOSI wire, so the address evidence is independent of the DUT's
    internal page counter and of the model's returned data.
    """
    observed_frames = []

    for read_index in range(n_frames):
        await FallingEdge(dut.spi_cs_n)
        header = []
        for _ in range(40):
            await RisingEdge(dut.spi_sclk)
            header.append(int(dut.spi_mosi.value))

        observed_frames.append(
            {
                "read_index": read_index,
                "command": bits_to_int(header[0:8]),
                "address": bits_to_int(header[8:32]),
                "dummy": bits_to_int(header[32:40]),
            }
        )
        await RisingEdge(dut.spi_cs_n)

    return observed_frames


async def drive_prbs_flash(
    dut,
    n_reads: int,
    burst_bits: int,
    *,
    inject_read: int | None = None,
    inject_bit: int | None = None,
    output_delay_ns: int = 8,
) -> list[dict[str, int]]:
    """Respond to 0x0B reads and optionally invert one payload bit.

    The driver observes the command and address on the SPI wires rather than
    reading the controller's internal page index. This keeps the response
    independent from the address-generation logic under test.
    """
    if (inject_read is None) != (inject_bit is None):
        raise ValueError("inject_read and inject_bit must be supplied together")
    if inject_read is not None and not 0 <= inject_read < n_reads:
        raise ValueError("inject_read is outside the requested read range")
    if inject_bit is not None and not 0 <= inject_bit < burst_bits:
        raise ValueError("inject_bit is outside the payload range")

    dut.spi_miso.value = 0
    observed_frames = []

    for read_index in range(n_reads):
        await FallingEdge(dut.spi_cs_n)
        edge_counter = cocotb.start_soon(count_sclk_rising_edges_until_cs_release(dut))

        header = []
        for _ in range(40):
            await RisingEdge(dut.spi_sclk)
            header.append(int(dut.spi_mosi.value))

        command = bits_to_int(header[0:8])
        address = bits_to_int(header[8:32])
        dummy = bits_to_int(header[32:40])
        expected_address = read_index * 256

        assert command == 0x0B, (
            f"read {read_index}: command=0x{command:02X}, expected 0x0B"
        )
        assert address == expected_address, (
            f"read {read_index}: address=0x{address:06X}, "
            f"expected 0x{expected_address:06X}"
        )
        assert dummy == 0, f"read {read_index}: dummy byte was not zero"

        page_index = address >> 8
        payload = prbs15_bits(page_index, burst_bits)
        for bit_index, bit in enumerate(payload):
            await FallingEdge(dut.spi_sclk)
            await Timer(output_delay_ns, unit="ns")
            if read_index == inject_read and bit_index == inject_bit:
                bit ^= 1
            dut.spi_miso.value = bit

        sclk_edges = await edge_counter
        dut.spi_miso.value = 0
        observed_frames.append(
            {
                "read_index": read_index,
                "command": command,
                "address": address,
                "dummy": dummy,
                "sclk_edges": sclk_edges,
            }
        )

    return observed_frames
