"""C3: busy states silently gate conflicting control commands."""

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


async def _wait_status(dut, mask: int, expected: bool) -> int:
    for _ in range(40):
        status = await _read_reg(dut, 0x08)
        if bool(status & mask) is expected:
            return status
    raise AssertionError(f"STATUS mask 0x{mask:02x} did not become {expected}")


@cocotb.test()
async def test_C3_busy_states_gate_conflicting_commands(dut) -> None:
    """PS_BUSY and MEAS_BUSY reject a phase command without CMD_ERR."""
    dut.aresetn.value = 0
    dut.meas_busy.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await _write_reg(dut, 0x04, 0x2)  # PHASE_INC
    await _wait_status(dut, 1 << 2, True)

    await _write_reg(dut, 0x04, 0x2)
    await _wait_status(dut, 1 << 2, False)
    phase = await _read_reg(dut, 0x14)
    status = await _read_reg(dut, 0x08)
    assert phase == 1, f"PS_BUSY gate failed: PHASE_POS=0x{phase:08x}"
    assert not (status & (1 << 6)), "busy-ignore incorrectly raised CMD_ERR"

    dut.meas_busy.value = 1
    await RisingEdge(dut.clk_core)
    await _write_reg(dut, 0x04, 0x2)
    dut.meas_busy.value = 0
    await Timer(40, unit="ns")
    phase = await _read_reg(dut, 0x14)
    status = await _read_reg(dut, 0x08)
    assert phase == 1, f"MEAS_BUSY gate failed: PHASE_POS=0x{phase:08x}"
    assert not (status & (1 << 6)), "MEAS_BUSY ignore incorrectly raised CMD_ERR"
    dut._log.info("C3 busy gating: PS_BUSY and MEAS_BUSY ignores are silent")
