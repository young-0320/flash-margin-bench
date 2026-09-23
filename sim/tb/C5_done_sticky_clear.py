"""C5: DONE is sticky and clears on the next accepted START."""

import cocotb
from cocotb.triggers import ReadOnly, ReadWrite, RisingEdge, Timer


async def _read_reg(dut, address: int) -> int:
    dut.s_axi_araddr.value = address
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.s_axi_arvalid.value = 0
    await ReadOnly()
    assert int(dut.s_axi_rvalid.value), "AXI read response was not returned"
    value = int(dut.s_axi_rdata.value)
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")
    return value


async def _write_reg(dut, address: int, value: int) -> None:
    dut.s_axi_awaddr.value = address
    dut.s_axi_wdata.value = value
    dut.s_axi_wstrb.value = 0xF
    dut.s_axi_awvalid.value = 1
    dut.s_axi_wvalid.value = 1
    dut.s_axi_bready.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.s_axi_awvalid.value = 0
    dut.s_axi_wvalid.value = 0
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")


@cocotb.test()
async def test_C5_done_sticky_clears_on_valid_start(dut) -> None:
    """A DONE pulse latches; a valid START clears the latch."""
    dut.aresetn.value = 0
    dut.meas_busy.value = 0
    dut.meas_done.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    # Inject the one-cycle flash completion event.
    dut.meas_done.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.meas_done.value = 0
    await Timer(1, unit="ns")

    status = await _read_reg(dut, 0x08)
    assert status & (1 << 1), "DONE pulse did not set sticky DONE"

    # A valid START is accepted because neither busy input is asserted.
    await _write_reg(dut, 0x04, 0x1)
    status = await _read_reg(dut, 0x08)
    assert not (status & (1 << 1)), "valid START did not clear sticky DONE"
    dut._log.info("C5 DONE: completion latched and cleared by valid START")
