"""C2: PHASE_INC/DEC updates PHASE_POS as a signed accumulator."""

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
    # Allow the one-cycle write response and the command pulse to settle.
    await RisingEdge(dut.clk_core)
    await ReadOnly()
    await Timer(1, unit="ps")


async def _wait_ps_idle(dut) -> None:
    for _ in range(40):
        status = await _read_reg(dut, 0x08)
        if not (status & (1 << 2)):  # STATUS.PS_BUSY
            return
    raise AssertionError("PS_BUSY did not clear")


@cocotb.test()
async def test_C2_phase_inc_dec_signed_accumulator(dut) -> None:
    """One INC, then two DEC commands produce +1, 0, and -1."""
    dut.aresetn.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await _write_reg(dut, 0x04, 0x2)  # PHASE_INC
    await _wait_ps_idle(dut)
    phase = await _read_reg(dut, 0x14)
    assert phase == 1, f"INC: got PHASE_POS=0x{phase:08x}, expected 1"

    await _write_reg(dut, 0x04, 0x4)  # PHASE_DEC
    await _wait_ps_idle(dut)
    phase = await _read_reg(dut, 0x14)
    assert phase == 0, f"DEC: got PHASE_POS=0x{phase:08x}, expected 0"

    await _write_reg(dut, 0x04, 0x4)  # PHASE_DEC again
    await _wait_ps_idle(dut)
    phase = await _read_reg(dut, 0x14)
    assert phase == 0xFFFF_FFFF, (
        f"signed DEC: got PHASE_POS=0x{phase:08x}, expected 0xffffffff"
    )
    dut._log.info("C2 signed accumulator: INC=+1, DEC=0, DEC=-1")
