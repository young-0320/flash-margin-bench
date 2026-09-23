"""W1: the official model must loudly reject one-bit-corrupted opcodes."""

import os

import cocotb

from flash_spi_test_helpers import (
    read_error_log,
    reset_dut,
    start_clocks,
    start_measurement,
    wait_for_done,
    zero_miso_error_count,
)


async def run_rejected_opcode(dut, target_opcode: int) -> None:
    """Inject one command-bit error and prove vendor rejection plus noisy data."""
    await reset_dut(dut)

    n_reads = 2
    burst_bits = 2048
    xor_mask = 0x0B ^ target_opcode
    before_count = int(dut.vendor_invalid_opcode_count.value)

    dut.use_vendor_model.value = 1
    dut.vendor_command_xor_mask.value = xor_mask

    # The official model's original invalid-opcode path calls $stop and drives
    # no payload. The runtime copy records that event instead; deterministic
    # low here represents the no-response bus so the DUT can finish and expose
    # the same loud PRBS-error signature as F9.
    dut.force_vendor_miso_low.value = 1

    await start_measurement(dut, n_reads=n_reads, burst_bits=burst_bits)
    timed_out = await wait_for_done(
        dut,
        max_core_cycles=2 * n_reads * (burst_bits + 64) + 200,
    )

    after_count = int(dut.vendor_invalid_opcode_count.value)
    assert after_count - before_count == n_reads, (
        f"vendor rejected {after_count - before_count} frames, expected {n_reads}"
    )
    assert int(dut.vendor_invalid_opcode_seen.value) == 1
    assert int(dut.vendor_invalid_opcode.value) == target_opcode, (
        f"vendor decoded 0x{int(dut.vendor_invalid_opcode.value):02X}, "
        f"expected injected opcode 0x{target_opcode:02X}"
    )

    per_read = [await read_error_log(dut, index) for index in range(n_reads)]
    expected = [
        zero_miso_error_count(page_index, burst_bits)
        for page_index in range(n_reads)
    ]

    assert not timed_out, "invalid-opcode no-response path unexpectedly timed out"
    assert per_read == expected, (
        f"invalid opcode 0x{target_opcode:02X}: errors={per_read}, expected={expected}"
    )
    assert all(0.35 <= errors / burst_bits <= 0.60 for errors in per_read), (
        f"invalid opcode 0x{target_opcode:02X} silently resembled a clean read"
    )
    assert int(dut.err_bits.value) == sum(per_read)
    assert int(dut.err_reads.value) == n_reads

    dut._log.info(
        "W1 opcode 0x%02X: vendor_rejections=%d per_read=%s timeout=%d",
        target_opcode,
        after_count - before_count,
        per_read,
        int(timed_out),
    )


@cocotb.test()
async def test_W1_vendor_rejects_0x0A_and_0x1B_without_silent_pass(dut) -> None:
    """Both one-bit corruptions must hit the vendor invalid-opcode path."""
    if os.getenv("WINBOND_MODEL_ENABLED") != "1":
        cocotb.skip("W1 requires WINBOND_MODEL_DIR and the official W25Q64JV model")

    start_clocks(dut)
    # Let elaborated continuous assignments settle before reading wrapper
    # presence wires. At time 0 Icarus can still expose their initial Z value.
    await reset_dut(dut)
    assert int(dut.vendor_model_present.value) == 1

    await run_rejected_opcode(dut, target_opcode=0x0A)
    await run_rejected_opcode(dut, target_opcode=0x1B)
