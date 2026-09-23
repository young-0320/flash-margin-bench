"""C1: core_top ID, reset configuration, and initial STATUS."""

import cocotb
from cocotb.triggers import ReadOnly, ReadWrite, RisingEdge, Timer


async def _read_reg(dut, address: int) -> int:
    dut.s_axi_araddr.value = address
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 1
    # The core accepts the address on this edge; arready changes after the
    # nonblocking rvalid update, so sampling arready after the edge would miss
    # the handshake. The wrapper has no other outstanding read.
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.s_axi_arvalid.value = 0
    await ReadOnly()
    assert int(dut.s_axi_rvalid.value), "AXI read response was not returned"
    value = int(dut.s_axi_rdata.value)
    # Keep RREADY asserted. The core clears RVALID on the next clock, so the
    # next read starts with no outstanding response and no phase transition is
    # needed from cocotb's ReadOnly region.
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")
    return value


@cocotb.test()
async def test_C1_core_register_reset_and_id(dut) -> None:
    """Reset release exposes the contractual ID and default register values."""
    dut.aresetn.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    checks = [
        (0x00, 0x4D42_0100, "ID"),
        (0x0C, 100, "N_READS reset"),
        (0x10, 2048, "BURST_BITS reset"),
        (0x08, 0x0000_0008, "STATUS idle+locked"),
        (0x14, 0, "PHASE_POS reset"),
    ]
    for address, expected, name in checks:
        actual = await _read_reg(dut, address)
        assert actual == expected, (
            f"{name}: got 0x{actual:08x}, expected 0x{expected:08x}"
        )
        dut._log.info("C1 %s = 0x%08x", name, actual)
