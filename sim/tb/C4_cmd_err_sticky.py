"""C4: malformed CTRL commands are rejected and CMD_ERR is sticky."""

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


async def _wait_ps_idle(dut) -> None:
    for _ in range(40):
        status = await _read_reg(dut, 0x08)
        if not (status & (1 << 2)):
            return
    raise AssertionError("PS_BUSY did not clear")


@cocotb.test()
async def test_C4_malformed_ctrl_sets_sticky_cmd_err(dut) -> None:
    """INC+DEC is rejected; a later valid command does not clear CMD_ERR."""
    dut.aresetn.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await _write_reg(dut, 0x04, 0x6)  # PHASE_INC + PHASE_DEC: malformed
    status = await _read_reg(dut, 0x08)
    phase = await _read_reg(dut, 0x14)
    assert status & (1 << 6), "malformed CTRL did not set CMD_ERR"
    assert not (status & (1 << 2)), "malformed CTRL started PS_BUSY"
    assert phase == 0, f"malformed CTRL changed PHASE_POS to 0x{phase:08x}"

    await _write_reg(dut, 0x04, 0x2)  # valid PHASE_INC
    await _wait_ps_idle(dut)
    phase = await _read_reg(dut, 0x14)
    status = await _read_reg(dut, 0x08)
    assert phase == 1, f"valid recovery INC failed: PHASE_POS=0x{phase:08x}"
    assert status & (1 << 6), "CMD_ERR was cleared by a valid command"
    dut._log.info("C4 CMD_ERR: malformed command rejected; sticky through recovery")
