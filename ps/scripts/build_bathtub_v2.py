# build_bathtub_v2.py — 욕조 v2 ELF 빌드 (클럭 묶음 치환, unified Vitis CLI)
#
# 실행:  BT2_MHZ=25|75 vitis -s ps/scripts/build_bathtub_v2.py
# 선행:  build/vivado_g3_<mhz>/g3_chip_<mhz>.xsa — 에지 계수기가 든 새 비트스트림(FEATURE bit0 = 1, 수정안 #4).
#        옛 XSA 로 빌드해도 ELF 는 나오지만 보드에서 no_feature(무효 ⑪)로 끝난다
# 산출:  build/vitis_bt2_<mhz>/bathtub_v2/build/bathtub_v2.elf
#
# build_g3_sweep.py 와 같은 구조다 — bathtub_v2.c 원본은 고치지 않고 bathtub_v2_gen.py 가 클럭 상수를 치환한
# 사본을 빌드한다. 벽 N(std · deep)과 base_sector 는 빌드가 아니라 실행 때 xsct 가 덮어쓴다 (program_g3.tcl).

import os
import shutil
import sys
from pathlib import Path

import vitis

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bathtub_v2_gen import gen_source  # noqa: E402

MHZ = int(os.environ.get("BT2_MHZ", "25"))
REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / f"vitis_bt2_{MHZ}"
XSA = REPO / "build" / f"vivado_g3_{MHZ}" / f"g3_chip_{MHZ}.xsa"

src = gen_source(MHZ)
if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run build_g3_chip.tcl (mhz={MHZ}) first")

# 생성 사본은 워크스페이스 밖에 (build_g3_sweep.py 와 같은 이유)
gen = REPO / "build" / f"bt2_gen_{MHZ}"
shutil.rmtree(gen, ignore_errors=True)
gen.mkdir(parents=True)
(gen / "bathtub_v2.c").write_text(src)

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="bt2_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="bathtub_v2",
    platform=str(WS / "bt2_plat" / "export" / "bt2_plat" / "bt2_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(gen), files=["bathtub_v2.c"], dest_dir_in_cmp="src")
app.build()

elf = next((WS / "bathtub_v2").rglob("bathtub_v2.elf"))
print(f"== done ({MHZ}MHz): {elf}")
