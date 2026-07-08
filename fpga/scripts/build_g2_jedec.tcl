# build_g2_jedec.tcl — G2 JEDEC ID 브링업용 비트스트림·XSA (PS SPI0 EMIO → PMOD JB)
#
# 실행:  vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl
# 산출:  build/vivado_g2/g2_jedec.xsa (+ 비트스트림, XSA에 포함)
#
# PL에 로직 없음 — PS 하드 SPI0을 EMIO로 JB 핀에 라우팅만 한다. 베어메탈 C(XSpiPs,
# 0x9F → 0xEF 40 17)는 장세은 담당 (docs/log/young/9 인수인계). 보드 프로그래밍은
# ps/scripts/program_g2.tcl.

if {![string match "2024.2*" [version -short]]} {
    error "Vivado 2024.2 필요 (현재: [version -short])"
}

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set build_dir  $repo/build/vivado_g2
set part       xc7z020clg400-1

set_param board.repoPaths [list $repo/fpga/boards]

create_project g2_jedec $build_dir -part $part -force
set bp [get_board_parts -quiet digilentinc.com:zybo-z7-20:*]
if {[llength $bp] == 0} { error "zybo-z7-20 board files not found under fpga/boards/" }
set_property board_part [lindex [lsort $bp] end] [current_project]

add_files -fileset constrs_1 $repo/fpga/constraints/g2_jedec_pins.xdc

# ---------------- BD ----------------
create_bd_design g2
set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps7
set_property -dict [list \
    CONFIG.PCW_SPI0_PERIPHERAL_ENABLE 1 \
    CONFIG.PCW_SPI0_SPI0_IO EMIO \
    CONFIG.PCW_USE_M_AXI_GP0 0 \
] $ps7

# 마스터 고정 결선: _O만 핀으로, 슬레이브용 입력은 무해값 고정
# (SS_I=1 필수 — 0이면 컨트롤러가 mode fault로 마스터를 스스로 내림)
set c1 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const1]
set_property CONFIG.CONST_VAL 1 $c1
set c0 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const0]
set_property CONFIG.CONST_VAL 0 $c0
connect_bd_net [get_bd_pins const1/dout] [get_bd_pins ps7/SPI0_SS_I]
connect_bd_net [get_bd_pins const0/dout] [get_bd_pins ps7/SPI0_SCLK_I] [get_bd_pins ps7/SPI0_MOSI_I]

create_bd_port -dir O spi_cs
create_bd_port -dir O spi_mosi
create_bd_port -dir I spi_miso
create_bd_port -dir O spi_sclk
connect_bd_net [get_bd_ports spi_cs]   [get_bd_pins ps7/SPI0_SS_O]
connect_bd_net [get_bd_ports spi_mosi] [get_bd_pins ps7/SPI0_MOSI_O]
connect_bd_net [get_bd_ports spi_miso] [get_bd_pins ps7/SPI0_MISO_I]
connect_bd_net [get_bd_ports spi_sclk] [get_bd_pins ps7/SPI0_SCLK_O]

validate_bd_design
save_bd_design

set_property synth_checkpoint_mode None [get_files g2.bd]
set wrapper [make_wrapper -files [get_files g2.bd] -top]
add_files $wrapper
set_property top g2_wrapper [current_fileset]

generate_target all [get_files g2.bd]
launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed" }
launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed" }

write_hw_platform -fixed -include_bit -force $build_dir/g2_jedec.xsa
puts "== done: $build_dir/g2_jedec.xsa (bit: $build_dir/g2_jedec.runs/impl_1/g2_wrapper.bit)"
