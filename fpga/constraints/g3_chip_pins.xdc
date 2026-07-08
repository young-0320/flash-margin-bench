# g3_chip_pins.xdc — 실칩 스윕 핀·클럭 (Zybo Z7-20, 로그 9 핀 표 승계)
#
# JB 상단열 = Pmod SPI 표준 (G2 JEDEC과 동일 물리 배선 — 비트스트림만 교체):
#   JB1 CS(V8) / JB2 MOSI(W8) / JB3 MISO(U7) / JB4 SCLK(V7), JB5 GND, JB6 3V3
# /WP·/HOLD 3V3 묶기 등 배선 주의는 docs/log/young/9 ②.

# 보드 125MHz PL 클럭
set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports clk125]
create_clock -name clk125 -period 8.000 [get_ports clk125]

set_property -dict {PACKAGE_PIN V8 IOSTANDARD LVCMOS33} [get_ports spi_cs_n]
set_property -dict {PACKAGE_PIN W8 IOSTANDARD LVCMOS33} [get_ports spi_mosi]
set_property -dict {PACKAGE_PIN U7 IOSTANDARD LVCMOS33} [get_ports spi_miso]
set_property -dict {PACKAGE_PIN V7 IOSTANDARD LVCMOS33} [get_ports spi_sclk]

# MISO 유휴(Hi-Z) 구간 보험 — 심이 먹스로 차단하지만 플로팅 자체를 없앤다
set_property PULLDOWN true [get_ports spi_miso]

# MISO → IOB 캡처 플롭 경로가 측정 대상 그 자체 — 타이밍 도구가 "고치면" 안 됨.
# 출력 3핀은 반주기 구성(SCLK 상승 = 사이클 중앙)이 셋업/홀드를 구조로 보장 —
# STA 제약 대신 flash_spi_ctrl 헤더의 타이밍 유도가 근거 (25~75MHz에서 여유 수 ns).
set_false_path -from [get_ports spi_miso]
set_false_path -to [get_ports {spi_cs_n spi_mosi spi_sclk}]
