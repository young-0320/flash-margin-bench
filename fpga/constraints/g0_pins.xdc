# g0_pins.xdc — G0 루프백 핀·클럭 (Zybo Z7-20, 계약 §5·결정 20)

# 보드 125MHz PL 클럭
set_property -dict {PACKAGE_PIN K17 IOSTANDARD LVCMOS33} [get_ports clk125]
create_clock -name clk125 -period 8.000 [get_ports clk125]

# 루프백 점퍼: JE1(출력) → 점퍼 → JE2(입력). JE 내장 200Ω 직렬 저항(충돌 보험)
set_property -dict {PACKAGE_PIN V12 IOSTANDARD LVCMOS33} [get_ports pattern_out]
set_property -dict {PACKAGE_PIN W16 IOSTANDARD LVCMOS33} [get_ports pattern_in]
