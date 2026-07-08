# build_g3_sweep.py — 실칩 스윕 ELF 빌드 (클럭 사다리 상수 치환, unified Vitis CLI)
#
# 실행:  G3_MHZ=25|45|75 vitis -s ps/scripts/build_g3_sweep.py
#   (보통은 build_g3_chip.tcl이 체인 호출)
# 선행:  build/vivado_g3_<mhz>/g3_chip_<mhz>.xsa
# 산출:  build/vitis_g3_<mhz>/g3_sweep/build/g3_sweep.elf
#
# 스윕 C는 g0_sweep.c 원본 무수정 원칙(R7·로그 8) — 대신 여기서 클럭별 상수
# (SWEEP_STEPS=56×O, F_SCLK_HZ)만 텍스트 치환한 사본을 생성해 빌드한다.
# Δφ=15.873016ps는 VCO 고정이라 전 사다리 공통(계약 결정 16). 치환 대상 줄이
# 원본에서 사라지면 시끄럽게 죽는다 (조용한 25MHz 상수 잔류 방지).

import os
import re
import shutil
from pathlib import Path

import vitis

MHZ = int(os.environ.get("G3_MHZ", "25"))
if MHZ not in (25, 45, 75):
    raise SystemExit(f"G3_MHZ={MHZ}: 25|45|75만 허용")
O = 1125 // MHZ
STEPS = 56 * O

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / f"vitis_g3_{MHZ}"
XSA = REPO / "build" / f"vivado_g3_{MHZ}" / f"g3_chip_{MHZ}.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run build_g3_chip.tcl (mhz={MHZ}) first")

src = (REPO / "ps" / "src" / "g0_sweep.c").read_text()
for pat, repl in [
    (r"#define SWEEP_STEPS\s+\d+u[^\n]*",
     f"#define SWEEP_STEPS     {STEPS}u          /* 56 x {O} = 1 UI ({MHZ}MHz) */"),
    (r"#define F_SCLK_HZ\s+\d+u[^\n]*",
     f"#define F_SCLK_HZ       {MHZ * 1_000_000}u"),
]:
    src, n = re.subn(pat, repl, src)
    if n != 1:
        raise SystemExit(f"g0_sweep.c에서 치환 대상 미발견/중복: {pat} (n={n})")

# 생성 사본은 워크스페이스 밖에 — WS에 미리 파일이 있으면 Vitis가 워크스페이스
# 버전 인식 실패로 거부한다
gen = REPO / "build" / f"g3_gen_{MHZ}"
shutil.rmtree(gen, ignore_errors=True)
gen.mkdir(parents=True)
(gen / "g3_sweep.c").write_text(src)

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="g3_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="g3_sweep",
    platform=str(WS / "g3_plat" / "export" / "g3_plat" / "g3_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(gen), files=["g3_sweep.c"], dest_dir_in_cmp="src")
app.build()

elf = next((WS / "g3_sweep").rglob("g3_sweep.elf"))
print(f"== done ({MHZ}MHz, steps={STEPS}): {elf}")
