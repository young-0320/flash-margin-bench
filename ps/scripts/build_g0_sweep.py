# build_g0_sweep.py — g0_sweep 베어메탈 앱 재생성·빌드 (XSA 소비, unified Vitis CLI)
#
# 실행:  vitis -s ps/scripts/build_g0_sweep.py
#   (보통은 직접 부를 일 없음 — build_g0_loopback.tcl이 체인 호출한다.
#    클래식 xsct 프로젝트 플로우는 2024.2 설치본에서 Vitis 서버 접속 타임아웃으로 불용 — 로그 8)
# 선행:  build/vivado/g0_loopback.xsa (fpga/scripts/build_g0_loopback.tcl)
# 산출:  build/vitis/g0_sweep/build/g0_sweep.elf
#
# 보드 프로그래밍은 ps/scripts/program_g0.tcl (xsct JTAG, GUI 불필요).
# UART 수신은 host/capture/sweep_uart_capture.py (115200 8N1, PS UART1=USB).

import shutil
from pathlib import Path

import vitis

REPO = Path(__file__).resolve().parents[2]
WS = REPO / "build" / "vitis"
XSA = REPO / "build" / "vivado" / "g0_loopback.xsa"

if not XSA.exists():
    raise SystemExit(f"XSA not found: {XSA} — run fpga/scripts/build_g0_loopback.tcl first")

shutil.rmtree(WS, ignore_errors=True)
client = vitis.create_client(workspace=str(WS))

plat = client.create_platform_component(
    name="g0_plat", hw_design=str(XSA), os="standalone", cpu="ps7_cortexa9_0")
plat.build()

app = client.create_app_component(
    name="g0_sweep",
    platform=str(WS / "g0_plat" / "export" / "g0_plat" / "g0_plat.xpfm"),
    template="empty_application")
app.import_files(from_loc=str(REPO / "ps" / "src"), files=["g0_sweep.c"],
                 dest_dir_in_cmp="src")
app.build()

elf = next((WS / "g0_sweep").rglob("g0_sweep.elf"))
print(f"== done: {elf}")
