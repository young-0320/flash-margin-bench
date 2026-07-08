# build_flash_jedec.py — flash_jedec 베어메탈 앱 빌드 (G2 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_flash_jedec.py
# 선행:  build/vivado_g2/g2_jedec.xsa (fpga/scripts/build_g2_jedec.tcl)
# 산출:  build/vitis_jedec/flash_jedec/build/flash_jedec.elf
# 프로그래밍: xsct ps/scripts/program_g2.tcl <위 elf>   (G2 비트스트림 사용)
#
# 워크스페이스를 build/vitis_jedec로 분리 — vitis_prep(flash_prep) 산출물 보존.

import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis_jedec"
XSA = REPO / "build" / "vivado_g2" / "g2_jedec.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g2_jedec.tcl first")

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="jedec_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="flash_jedec",
    platform=str(WS / "jedec_plat" / "export" / "jedec_plat" / "jedec_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"), files=["flash_jedec.c"],
                 dest_dir_in_cmp="src")
app.build()

elf = next((WS / "flash_jedec").rglob("flash_jedec.elf"))
print(f"== done: {elf}")
