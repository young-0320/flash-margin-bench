"""I1: one host step through core + flash loopback, including R8 recovery."""

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
    assert int(dut.s_axi_rvalid.value), "AXI read response was not returned"
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


async def wait_status(dut, mask, expected, limit=2000):
    for _ in range(limit):
        status = await read_reg(dut, 0x08)
        if bool(status & mask) is expected:
            return status
    raise AssertionError(f"STATUS mask 0x{mask:02x} did not become {expected}")


@cocotb.test()
async def test_I1_one_host_step_loopback(dut):
    dut.aresetn.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await write_reg(dut, 0x0C, 2)    # N_READS
    await write_reg(dut, 0x10, 64)   # B, small but legal
    await write_reg(dut, 0x04, 0x2) # PHASE_INC
    await wait_status(dut, 1 << 2, False)
    phase = await read_reg(dut, 0x14)
    assert phase == 1, f"I1 phase step failed: 0x{phase:08x}"

    await write_reg(dut, 0x04, 0x1) # MEAS_START
    status = await wait_status(dut, 1 << 1, True, limit=4000)
    assert not (status & (1 << 0)), "I1 ended with MEAS_BUSY still high"
    assert not (status & (1 << 4)), "I1 loopback unexpectedly timed out"
    assert not (status & (1 << 5)), "I1 loopback raised CFG_ERR"

    err_bits = await read_reg(dut, 0x18)
    err_reads = await read_reg(dut, 0x1C)
    assert err_bits == 0, f"I1 ERR_BITS={err_bits}, expected 0"
    assert err_reads == 0, f"I1 ERR_READS={err_reads}, expected 0"
    for index in range(2):
        await write_reg(dut, 0x20, index)
        entry = await read_reg(dut, 0x24)
        assert entry == 0, f"I1 e_{index}={entry}, expected 0"
    dut._log.info("I1 host step: INC -> START -> DONE -> ERR/e_i all clean")
