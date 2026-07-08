# build_core_smoke.py — core_smoke 베어메탈 앱 빌드 (G0 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_core_smoke.py
# 선행:  build/vivado/g0_loopback.xsa (fpga/scripts/build_g0_loopback.tcl)
# 산출:  build/vitis_smoke/core_smoke/build/core_smoke.elf
# 프로그래밍: xsct ps/scripts/program_core_smoke.tcl
#
# 용도: PS↔PL(core 블록) AXI-Lite 스모크 (세은 작성, 로그 14 리뷰 반영).
# core 배치는 G0·G3 동일(0x43C00000)이라 스윕 계열 어느 비트스트림 위에서도 유효.
# 워크스페이스를 build/vitis_smoke으로 분리 — build/vitis(g0)·vitis_prep과 충돌 방지.

import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis_smoke"
XSA = REPO / "build" / "vivado" / "g0_loopback.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g0_loopback.tcl first")

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="smoke_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="core_smoke",
    platform=str(WS / "smoke_plat" / "export" / "smoke_plat" / "smoke_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"), files=["core_smoke.c"],
                 dest_dir_in_cmp="src")
app.build()

elf = next((WS / "core_smoke").rglob("core_smoke.elf"))
print(f"== done: {elf}")
