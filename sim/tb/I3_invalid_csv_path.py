"""I3: an incomplete UART run is retained as a paired _invalid CSV result."""

import tempfile
from pathlib import Path
import sys
import types

import cocotb

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "host" / "capture"))
# I3 exercises the parser/file path with a fake serial object; it never opens
# a real UART. Keep the test runnable in the cocotb-only environment where
# pyserial is intentionally not required.
serial_stub = types.ModuleType("serial")
serial_stub.Serial = object
sys.modules.setdefault("serial", serial_stub)
from sweep_uart_capture import capture_sweep  # noqa: E402


class FakeSerial:
    """Small serial stand-in containing one deliberately truncated sweep."""

    port = "/fake/tty"
    baudrate = 921600

    def __init__(self):
        self.lines = iter(
            [
                b"#G0 SWEEP BEGIN steps=2 n=2 b=64 f_sclk_hz=25000000 dphi_ps=15\n",
                b"M,0,0,2,64,0,0,0,25000000,15\n",
                b"R,0,0,0\n",
                b"#G0 SWEEP END valid=1 reason=complete\n",
            ]
        )

    def readline(self):
        try:
            return next(self.lines)
        except StopIteration:
            return b""


@cocotb.test()
async def test_I3_incomplete_run_is_saved_as_invalid_csv(dut):
    with tempfile.TemporaryDirectory(prefix="cocotb_i3_") as directory:
        result = capture_sweep(
            FakeSerial(),
            "loopback",
            "",
            outdir=directory,
            log=sys.stdout,
        )
        assert not result.valid
        assert result.reason == "row_mismatch"
        assert result.n_main == 1 and result.n_reads == 1
        assert result.main_path.name.endswith("_invalid.csv")
        assert result.reads_path.name.endswith("_invalid_reads.csv")
        text = result.main_path.read_text(encoding="utf-8")
        assert text.splitlines()[-1].endswith(",row_mismatch")
        dut._log.info("I3 truncated run: valid=0 -> paired _invalid CSV files")
