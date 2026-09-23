"""I2: two consecutive host steps preserve independent results and R8 entries."""

import cocotb
from cocotb.triggers import Timer

from I1_host_step_loopback import read_reg, wait_status, write_reg


async def run_step(dut, step_index):
    """Run one host step and verify its completion/result window."""
    await write_reg(dut, 0x04, 0x2)  # PHASE_INC
    await wait_status(dut, 1 << 2, False)
    phase = await read_reg(dut, 0x14)
    assert phase == step_index, f"I2 step {step_index}: phase=0x{phase:08x}"

    await write_reg(dut, 0x04, 0x1)  # MEAS_START
    await wait_status(dut, 1 << 1, False)  # DONE must clear for this START
    status = await wait_status(dut, 1 << 1, True, limit=4000)
    assert not (status & (1 << 0)), f"I2 step {step_index}: MEAS_BUSY still high"
    assert not (status & (1 << 4)), f"I2 step {step_index}: unexpected TIMEOUT"
    assert not (status & (1 << 5)), f"I2 step {step_index}: unexpected CFG_ERR"
    assert await read_reg(dut, 0x18) == 0, f"I2 step {step_index}: ERR_BITS nonzero"
    assert await read_reg(dut, 0x1C) == 0, f"I2 step {step_index}: ERR_READS nonzero"

    for index in range(2):
        await write_reg(dut, 0x20, index)
        entry = await read_reg(dut, 0x24)
        assert entry == 0, f"I2 step {step_index}: e_{index}={entry}"


@cocotb.test()
async def test_I2_two_host_steps_keep_results_separate(dut):
    dut.aresetn.value = 0
    await Timer(700, unit="ns")
    dut.aresetn.value = 1
    await Timer(100, unit="ns")

    await write_reg(dut, 0x0C, 2)   # N_READS
    await write_reg(dut, 0x10, 64)  # legal small burst
    await run_step(dut, 1)
    await run_step(dut, 2)
    dut._log.info("I2 two host steps: both DONE, counters, and R8 entries clean")
