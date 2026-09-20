# build_flash_wear.py — 마모 엔진(flash_wear) 베어메탈 앱 빌드 (G2 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_flash_wear.py
#        WEAR_SPI_PRESCALE=16 vitis -s ps/scripts/build_flash_wear.py   (8·16·64 — 실측 뒤 사람이 고른다, [U44-7])
# 선행:  build/vivado_g2/g2_jedec.xsa (fpga/scripts/build_g2_jedec.tcl) — 마모는 g2 비트스트림(PS SPI EMIO)
# 산출:  build/vitis_wear/flash_wear/build/flash_wear.elf
# 프로그래밍: xsct ps/scripts/program_g2.tcl <위 elf>   (host/run/run_wear.py accept 가 한다)
#
# git_rev 는 `git rev-parse --short HEAD` 를 wear_build.h 로 생성해 넣는다 — 소스에 하드코딩하지 않는다.
# -Wall -Wextra 는 Vitis 앱 기본 설정(UserConfig.cmake)에 이미 켜져 있다 — 빌드 로그에서 warning 0 을 확인한다.

import os
import shutil
import subprocess
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis_wear"
GEN = REPO / "build" / "wear_gen"
XSA = REPO / "build" / "vivado_g2" / "g2_jedec.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g2_jedec.tcl first")

prescale = os.environ.get("WEAR_SPI_PRESCALE")
if prescale is not None and int(prescale) not in (8, 16, 64):
    raise SystemExit(f"WEAR_SPI_PRESCALE={prescale}: 8|16|64 만 허용")

rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                     capture_output=True, text=True).stdout.strip() or "unknown"
shutil.rmtree(GEN, ignore_errors=True)
GEN.mkdir(parents=True)
(GEN / "wear_build.h").write_text(f'#define WEAR_GIT_REV "{rev}"\n')

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="wear_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="flash_wear",
    platform=str(WS / "wear_plat" / "export" / "wear_plat" / "wear_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"),
                 files=["flash_wear.c", "wear_plat.h", "wear_plat_zynq.c", "flash_io.c", "flash_io.h"],
                 dest_dir_in_cmp="src")
app.import_files(from_loc=str(GEN), files=["wear_build.h"], dest_dir_in_cmp="src")
if prescale is not None:
    app.set_app_config(key="USER_COMPILE_DEFINITIONS", values=[f"WEAR_SPI_PRESCALE={int(prescale)}u"])
app.build()

elf = next((WS / "flash_wear").rglob("flash_wear.elf"))
print(f"== done (git_rev {rev}, spi prescale {prescale or '64 (default)'}): {elf}")
