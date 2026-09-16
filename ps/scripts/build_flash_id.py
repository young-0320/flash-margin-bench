# build_flash_id.py — flash_id 베어메탈 앱 빌드 (G2 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_flash_id.py
# 선행:  build/vivado_g2/g2_jedec.xsa (fpga/scripts/build_g2_jedec.tcl)  — Vivado 재빌드 불필요
# 산출:  build/vitis_id/flash_id/build/flash_id.elf
# 프로그래밍: xsct ps/scripts/program_g2.tcl <위 elf>   (G2 비트스트림 사용)
#
# 워크스페이스를 build/vitis_id로 분리 — build/vitis_prep(flash_prep)·build/vitis(g0)와 충돌 방지.

import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis_id"
XSA = REPO / "build" / "vivado_g2" / "g2_jedec.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g2_jedec.tcl first")

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="id_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="flash_id",
    platform=str(WS / "id_plat" / "export" / "id_plat" / "id_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"),
                 files=["flash_id.c", "flash_io.c", "flash_io.h"],
                 dest_dir_in_cmp="src")
app.build()

elf = next((WS / "flash_id").rglob("flash_id.elf"))
print(f"== done: {elf}")
