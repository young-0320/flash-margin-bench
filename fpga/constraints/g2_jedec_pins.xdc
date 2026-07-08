# g2_jedec_pins.xdc — G2 JEDEC ID 브링업: PS SPI0(EMIO) → PMOD JB 상단열
#
# 핀 배열은 Digilent Pmod SPI 표준 (Pmod Interface Spec Type 2):
#   JB1=CS  JB2=MOSI  JB3=MISO  JB4=SCK  (+ JB5=GND, JB6=3V3)
# 이 배정이 4번(실칩 곡선)의 SPI 핀 배정으로 그대로 이어진다.
set_property -dict {PACKAGE_PIN V8 IOSTANDARD LVCMOS33} [get_ports spi_cs]
set_property -dict {PACKAGE_PIN W8 IOSTANDARD LVCMOS33} [get_ports spi_mosi]
set_property -dict {PACKAGE_PIN U7 IOSTANDARD LVCMOS33} [get_ports spi_miso]
set_property -dict {PACKAGE_PIN V7 IOSTANDARD LVCMOS33} [get_ports spi_sclk]

# 저속(~5MHz) 브링업 전용 — 타이밍 제약 없음. 미제약 IO 경고는 무시 대상.
set_false_path -to [get_ports {spi_cs spi_mosi spi_sclk}]
set_false_path -from [get_ports spi_miso]
