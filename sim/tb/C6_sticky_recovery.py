"""C6: TIMEOUT/CFG_ERR sticky flags clear only on valid START busy rise."""

import cocotb
from cocotb.triggers import ReadOnly, ReadWrite, RisingEdge, Timer


async def read_reg(dut, address):
    dut.s_axi_araddr.value = address
    dut.s_axi_arvalid.value = 1
    dut.s_axi_rready.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.s_axi_arvalid.value = 0
    await ReadOnly()
    assert int(dut.s_axi_rvalid.value)
    value = int(dut.s_axi_rdata.value)
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")
    return value


async def write_reg(dut, address, value):
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
    await Timer(1, unit="ns")


async def pulse(dut, name):
    signal = getattr(dut, name)
    signal.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    signal.value = 0
    await Timer(1, unit="ns")


@cocotb.test()
async def test_C6_timeout_cfg_err_sticky_recovery(dut):
    dut.aresetn.value = 0
    # Establish MEAS_BUSY before creating the sticky faults. A busy rise is
    # itself the documented recovery event, so it must not occur after the
    # faults when testing that a rejected START preserves them.
    dut.meas_busy.value = 1
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")
    dut.meas_timeout.value = 0
    dut.cfg_err.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await pulse(dut, "cfg_err")
    await pulse(dut, "meas_timeout")
    status = await read_reg(dut, 0x08)
    assert status & (1 << 5)
    assert status & (1 << 4)

    await write_reg(dut, 0x04, 0x1)
    dut.meas_busy.value = 0
    await Timer(1, unit="ns")
    status = await read_reg(dut, 0x08)
    assert status & (1 << 5)
    assert status & (1 << 4)

    await write_reg(dut, 0x04, 0x1)
    dut.meas_busy.value = 1
    await RisingEdge(dut.clk_core)
    await ReadWrite()
    dut.meas_busy.value = 0
    await Timer(1, unit="ns")
    status = await read_reg(dut, 0x08)
    assert not (status & (1 << 5))
    assert not (status & (1 << 4))
    dut._log.info("C6 sticky recovery: rejected START preserves; valid busy rise clears")
