"""W2: prove the Winbond model's CS high-time (tSHSL) timing guard."""

import os

import cocotb
from cocotb.triggers import Timer

from flash_spi_test_helpers import reset_dut, start_clocks


VENDOR_MODEL_ENABLED = os.getenv("WINBOND_MODEL_ENABLED") == "1"


async def _clock_bit(dut, bit: int) -> None:
    """Send one mode-0 bit to the model-only timing probe."""
    dut.timing_probe_dio.value = bit
    dut.timing_probe_clk.value = 1
    await Timer(5, unit="ns")
    dut.timing_probe_clk.value = 0
    await Timer(5, unit="ns")


async def _probe_byte(
    dut, value: int, *, extra_clocks: int = 0, high_gap_ns: int = 100
) -> None:
    """Send one SPI command frame, then leave CS high for a safe interval."""
    dut.timing_probe_cs_n.value = 0
    await Timer(5, unit="ns")
    for bit_index in range(7, -1, -1):
        await _clock_bit(dut, (value >> bit_index) & 1)
    for _ in range(extra_clocks):
        await _clock_bit(dut, 0)
    dut.timing_probe_cs_n.value = 1
    await Timer(high_gap_ns, unit="ns")


async def _clear_vendor_timing_error(dut) -> None:
    """Clear only the model notifier left by an earlier test in this run."""
    dut.vendor_timing_reset.value = 1
    await Timer(1, unit="ns")
    dut.vendor_timing_reset.value = 0
    await Timer(1, unit="ns")


@cocotb.test(skip=not VENDOR_MODEL_ENABLED)
async def test_W2_vendor_tshsl_clean_and_negative_control(dut) -> None:
    """Legal CS gaps stay clean; a sub-minimum gap must raise timing_error."""
    start_clocks(dut)
    await reset_dut(dut)

    assert int(dut.vendor_model_present.value) == 1, "Winbond model was not compiled"
    dut.use_timing_probe.value = 1
    dut.timing_probe_cs_n.value = 1
    dut.timing_probe_clk.value = 0
    dut.timing_probe_dio.value = 0
    await Timer(5, unit="ns")

    # F2's deliberate short-clock negative control leaves timing_error sticky.
    # Clear only that test notifier so W2 is order-safe; this is not a Flash
    # reset and does not change any simulated memory contents.
    await _clear_vendor_timing_error(dut)
    # Also separate W1's final CS release from W2's first frame. Otherwise
    # the transition itself can be interpreted as a short tSHSL interval.
    await Timer(100, unit="ns")
    assert int(dut.vendor_tshsl_compat_count.value) == 0, (
        "W2 tSHSL violation counter was not clear at test start"
    )

    # The supplied model uses tSHSL_R=10 ns for reads and tSHSL_W=50 ns for
    # non-read commands. Use gaps above both limits so W2 is independent of
    # the command state left by an earlier vendor-model test.
    for legal_gap_ns in (60, 100, 150):
        await _probe_byte(dut, 0x0B, high_gap_ns=legal_gap_ns)
        assert int(dut.vendor_tshsl_compat_count.value) == 0, (
            f"legal CS-high gap {legal_gap_ns} ns raised a tSHSL violation"
        )

    # Negative control: the next CS-high interval is 1 ns, below tSHSL_R=10 ns.
    # The Verilog $width check reports at the falling edge that ends the high
    # interval, so start the following frame before reading timing_error.
    await _probe_byte(dut, 0x0B, high_gap_ns=1)
    dut.timing_probe_cs_n.value = 0
    await Timer(1, unit="ns")
    assert int(dut.vendor_tshsl_compat_count.value) >= 1, (
        "sub-minimum CS-high gap did not raise the Winbond tSHSL assertion"
    )
    dut.timing_probe_cs_n.value = 1
    dut.use_timing_probe.value = 0
    dut._log.info(
        "W2 tSHSL: legal gaps 60/100/150 ns clean; 1 ns negative control detected"
    )
