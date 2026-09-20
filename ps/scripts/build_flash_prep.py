# build_flash_prep.py — flash_prep 베어메탈 앱 빌드 (G2 XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_flash_prep.py                       기본 (0~127 전체, 종전 동작)
#        PREP_BASE=7 PREP_N=7 vitis -s ps/scripts/build_flash_prep.py  체크포인트 준비 (근접 7~13)
# 선행:  build/vivado_g2/g2_jedec.xsa (fpga/scripts/build_g2_jedec.tcl)
# 산출:  기본       build/vitis_prep/flash_prep/build/flash_prep.elf        (run_sweep_chip.py 가 이 경로를 본다)
#        체크포인트 build/vitis_prep_<base>_<n>/flash_prep/build/flash_prep.elf
# 프로그래밍: xsct ps/scripts/program_g2.tcl <위 elf>   (G2 비트스트림 사용)
#
# 워크스페이스는 변형마다 따로다 — 자기 워크스페이스만 지운다 (build/vitis(g0)·세은 G2 앱·다른
# 변형과 충돌 방지). 범위는 빌드 타임 define(PREP_BASE_SECTOR·PREP_N_SECTORS)으로 들어가고
# 하드 가드(tally·TB 영역)에 걸리면 flash_prep.c 의 _Static_assert 가 빌드를 깨뜨린다 (로그 45).

import os
import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
XSA = REPO / "build" / "vivado_g2" / "g2_jedec.xsa"

base, n = os.environ.get("PREP_BASE"), os.environ.get("PREP_N")
if (base is None) != (n is None):
    raise SystemExit("PREP_BASE 와 PREP_N 은 같이 준다")
defines = [] if base is None else [f"PREP_BASE_SECTOR={int(base)}u", f"PREP_N_SECTORS={int(n)}u"]
WS = REPO / "build" / ("vitis_prep" if base is None else f"vitis_prep_{int(base)}_{int(n)}")

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
app.import_files(from_loc=str(REPO / "ps" / "src"),
                 files=["flash_prep.c", "flash_io.c", "flash_io.h"],
                 dest_dir_in_cmp="src")
if defines:
    app.set_app_config(key="USER_COMPILE_DEFINITIONS", values=defines)
app.build()

elf = next((WS / "flash_prep").rglob("flash_prep.elf"))
print(f"== done ({'default 0~127' if base is None else f'sectors {base}~{int(base) + int(n) - 1}'}): {elf}")
