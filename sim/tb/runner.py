"""Build flash_top_spi and run the first cocotb G1 regression.

Run from the repository root:
    python sim/tb/runner.py
"""

import os
import re
import shutil
from pathlib import Path

from cocotb_tools.runner import get_results, get_runner

from flash_spi_test_helpers import prbs15_bits


REPO_ROOT = Path(__file__).resolve().parents[2]
TB_DIR = REPO_ROOT / "sim" / "tb"
BUILD_DIR = REPO_ROOT / "sim" / "build"
SIM_BUILD_DIR = BUILD_DIR / "icarus"
VENDOR_RUNTIME_DIR = BUILD_DIR / "vendor_model"
RESULTS_XML = BUILD_DIR / "results.xml"
WRAPPER = TB_DIR / "flash_spi_cocotb_top.v"
CORE_WRAPPER = TB_DIR / "core_cocotb_top.v"
INTEGRATION_WRAPPER = TB_DIR / "integration_cocotb_top.v"


def _write_vendor_memory(path: Path, pages: int = 512) -> None:
    """Create model MEM.TXT with one PRBS-filled 256-byte image per page."""
    lines = []
    for page_index in range(pages):
        lines.append(f"@{page_index * 256:06X}")
        bits = prbs15_bits(page_index, 256 * 8)
        page_bytes = [
            sum(bits[byte_index * 8 + bit] << (7 - bit) for bit in range(8))
            for byte_index in range(256)
        ]
        lines.extend(
            " ".join(f"{value:02X}" for value in page_bytes[offset : offset + 16])
            for offset in range(0, 256, 16)
        )
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def _prepare_vendor_model() -> tuple[Path | None, dict[str, int]]:
    """Validate the private model directory and stage runtime data files."""
    raw_dir = os.getenv("WINBOND_MODEL_DIR")
    if not raw_dir:
        os.environ["WINBOND_MODEL_ENABLED"] = "0"
        return None, {}

    model_dir = Path(raw_dir).expanduser().resolve()
    required = ["W25Q64JV.v", "SECSI.TXT", "SFDP.TXT", "SREG.TXT"]
    missing = [name for name in required if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"WINBOND_MODEL_DIR={model_dir} is missing: {', '.join(missing)}"
        )

    VENDOR_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for name in required[1:]:
        shutil.copy2(model_dir / name, VENDOR_RUNTIME_DIR / name)
    _write_vendor_memory(VENDOR_RUNTIME_DIR / "MEM.TXT")

    # The vendor source opens its data files by relative name. Cocotb's runtime
    # working directory is simulator-dependent, so create an ignored build-only
    # copy whose four filename macros point at absolute local paths. The licensed
    # source remains outside Git and the original file is never modified.
    source_text = (model_dir / "W25Q64JV.v").read_text(encoding="utf-8")
    runtime_files = {
        "MEM_FILENAME": VENDOR_RUNTIME_DIR / "MEM.TXT",
        "SECSI_FILENAME": VENDOR_RUNTIME_DIR / "SECSI.TXT",
        "SFDP_FILENAME": VENDOR_RUNTIME_DIR / "SFDP.TXT",
        "SREG_FILENAME": VENDOR_RUNTIME_DIR / "SREG.TXT",
    }
    for macro, runtime_path in runtime_files.items():
        old = f'`define {macro} "{runtime_path.name}"'
        new = f'`define {macro} "{runtime_path.as_posix()}"'
        if old not in source_text:
            raise RuntimeError(f"Winbond model does not contain expected macro: {old}")
        source_text = source_text.replace(old, new, 1)

    # The official model deliberately calls $stop for an invalid opcode. That
    # is a loud rejection, but it terminates Icarus before cocotb can record a
    # JUnit result. Instrument only the ignored runtime copy: retain the vendor
    # decode and message, expose a sticky event/count, and wait for CS release.
    # The licensed original remains untouched outside the repository.
    cmd_decl = "reg [7:0]  cmd_byte;"
    if cmd_decl not in source_text:
        raise RuntimeError("Winbond model cmd_byte declaration was not found")
    source_text = source_text.replace(
        cmd_decl,
        cmd_decl
        + "\nreg vendor_invalid_opcode_seen = 1'b0;"
        + "\nreg [7:0] vendor_invalid_opcode = 8'h00;"
        + "\ninteger vendor_invalid_opcode_count = 0;",
        1,
    )

    # Icarus accepts the model's specify block but does not expose this
    # conditional $width notifier reliably. Add an equivalent monitor to the
    # ignored runtime copy only, so W2 can still prove the vendor rule with
    # the simulator used by this repository. The original licensed source is
    # never modified.
    timing_decl = "reg timing_error;"
    if timing_decl not in source_text:
        raise RuntimeError("Winbond model timing_error declaration was not found")
    timing_monitor = (
        timing_decl
        + "\nbit vendor_tshsl_compat_active = 1'b0;"
        + "\nrealtime vendor_tshsl_compat_start = 0.0;"
        + "\nreg vendor_tshsl_compat_seen = 1'b0;"
        + "\ninteger vendor_tshsl_compat_count = 0;"
        + "\nalways @(posedge CSn) begin"
        + "\n    vendor_tshsl_compat_active = flag_read_op;"
        + "\n    vendor_tshsl_compat_start = $realtime;"
        + "\nend"
        + "\nalways @(negedge CSn) begin"
        + "\n    if (vendor_tshsl_compat_active && "
        + "(($realtime - vendor_tshsl_compat_start) < 10.0)) begin"
        + "\n        timing_error = 1'b1;"
        + "\n        vendor_tshsl_compat_seen = 1'b1;"
        + "\n        vendor_tshsl_compat_count = vendor_tshsl_compat_count + 1;"
        + "\n        timing_reason = $sformatf("
        + '"tSHSL_R: measured=%0.3f ns, limit=10.000 ns", '
        + "($realtime - vendor_tshsl_compat_start));"
        + "\n    end"
        + "\nend"
    )
    source_text = source_text.replace(timing_decl, timing_monitor, 1)

    invalid_stop = re.compile(
        r'(\$display\("Invalid Opcode\. \(%0h\)",cmd_byte\);\s*)\$stop;'
    )

    def instrument_invalid_opcode(match: re.Match[str]) -> str:
        return (
            match.group(1)
            + "vendor_invalid_opcode_seen = 1'b1;\n"
            + "\t\t\tvendor_invalid_opcode = cmd_byte;\n"
            + "\t\t\tvendor_invalid_opcode_count = "
            + "vendor_invalid_opcode_count + 1;\n"
            + "\t\t\twait (CSn == 1'b1);"
        )

    source_text, substitutions = invalid_stop.subn(
        instrument_invalid_opcode, source_text, count=1
    )
    if substitutions != 1:
        raise RuntimeError("Winbond model invalid-opcode stop site was not found")

    runtime_model = VENDOR_RUNTIME_DIR / "W25Q64JV_runtime.v"
    runtime_model.write_text(source_text, encoding="utf-8")

    os.environ["WINBOND_MODEL_ENABLED"] = "1"
    return runtime_model, {"WINBOND_MODEL": 1}


def run() -> Path:
    """Compile the Flash RTL, run cocotb, and return the JUnit report path."""
    simulator = os.getenv("SIM", "icarus")
    model_source, defines = _prepare_vendor_model()
    sources = [REPO_ROOT / "sim" / "smoke" / "unisim_stub.v"]

    BUILD_DIR.mkdir(parents=True, exist_ok=True)

    # Some development machines source ROS globally. Its pytest entry points are
    # unrelated to this regression and can pull unavailable ROS dependencies into
    # cocotb before a test starts, so keep this run isolated from external plugins.
    os.environ["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    if RESULTS_XML.exists():
        RESULTS_XML.unlink()

    runner = get_runner(simulator)
    old_cwd = Path.cwd()
    try:
        # W25Q64JV.v opens MEM/SECSI/SFDP/SREG by relative filename.
        os.chdir(SIM_BUILD_DIR)
        default_test_modules = (
            "F1_spi_fast_read_frame_format,"
            "F3_address_to_prbs_seed,"
            "F5_output_delay_sweep,"
            "F2_spi_mode0_timing,"
            "F4_sample_phase_sweep,"
            "F6_single_bit_error_count,"
            "F7_watchdog_timeout_recovery,"
            "F8_invalid_config_rejection,"
            "F9_no_flash_signature,"
            "F10_boundary_clean_runs,"
            "W1_vendor_invalid_opcode_rejection,"
            "W2_vendor_tshsl_timing"
        )
        test_modules = os.getenv("G1_TEST_MODULES", default_test_modules)
        is_core_run = any(
            item.strip().startswith("C") for item in test_modules.split(",")
        )
        is_integration_run = any(
            item.strip().startswith("I") for item in test_modules.split(",")
        )
        if is_core_run:
            sources.extend(sorted((REPO_ROOT / "fpga" / "rtl" / "core").glob("*.v")))
            sources.append(CORE_WRAPPER)
            hdl_toplevel = "core_cocotb_top"
        elif is_integration_run:
            sources.extend(sorted((REPO_ROOT / "fpga" / "rtl" / "core").glob("*.v")))
            sources.extend(sorted((REPO_ROOT / "fpga" / "rtl" / "flash").glob("*.v")))
            sources.append(INTEGRATION_WRAPPER)
            hdl_toplevel = "integration_cocotb_top"
        else:
            sources.extend(sorted((REPO_ROOT / "fpga" / "rtl" / "flash").glob("*.v")))
            sources.append(WRAPPER)
            if model_source is not None:
                sources.append(model_source)
            hdl_toplevel = "flash_spi_cocotb_top"
        runner.build(
            sources=sources,
            hdl_toplevel=hdl_toplevel,
            build_dir=SIM_BUILD_DIR,
            build_args=["-g2012", "-gspecify"],
            defines=defines,
            always=True,
        )
        result_path = runner.test(
            hdl_toplevel=hdl_toplevel,
            test_module=test_modules,
            test_dir=TB_DIR,
            build_dir=SIM_BUILD_DIR,
            results_xml=RESULTS_XML,
        )
    finally:
        os.chdir(old_cwd)
    tests, failures = get_results(result_path)
    if tests == 0:
        raise RuntimeError("cocotb produced a report but did not execute any tests")
    if failures:
        raise RuntimeError(f"cocotb failed {failures} of {tests} tests")
    return Path(result_path)


if __name__ == "__main__":
    result = run()
    print(f"JUnit result: {result}")
