# build_flash_prep.py — flash_prep 베어메탈 앱 빌드 (G2 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_flash_prep.py
# 선행:  build/vivado_g2/g2_jedec.xsa (fpga/scripts/build_g2_jedec.tcl)
# 산출:  build/vitis_prep/flash_prep/build/flash_prep.elf
# 프로그래밍: xsct ps/scripts/program_g2.tcl <위 elf>   (G2 비트스트림 사용)
#
# 워크스페이스를 build/vitis_prep으로 분리 — build/vitis(g0)·세은 G2 앱과 충돌 방지.

import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis_prep"
XSA = REPO / "build" / "vivado_g2" / "g2_jedec.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g2_jedec.tcl first")

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="prep_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="flash_prep",
    platform=str(WS / "prep_plat" / "export" / "prep_plat" / "prep_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"), files=["flash_prep.c"],
                 dest_dir_in_cmp="src")
app.build()

elf = next((WS / "flash_prep").rglob("flash_prep.elf"))
print(f"== done: {elf}")
