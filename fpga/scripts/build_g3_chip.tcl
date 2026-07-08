# build_g3_chip.tcl — 실칩 스윕: 프로젝트 재생성 → BD → 비트스트림·XSA → ELF 원샷
#
# 실행:  vivado -mode batch -source fpga/scripts/build_g3_chip.tcl [-tclargs <stage> <mhz>]
#   stage = all(기본) | bit | bd,  mhz = 25(기본) | 45 | 75  (클럭 사다리, 로그 10 결정 ⑤)
# 산출:  build/vivado_g3_<mhz>/g3_chip_<mhz>.xsa (+ELF: build/vitis_g3_<mhz>/)
# 프로그래밍: xsct ps/scripts/program_g3.tcl <mhz> [elf]
#
# build_g0_loopback.tcl과 동일 골격 — 차이는 flash_top_spi(SPI 프런트엔드),
# JB 핀 XDC, core O_DIV 파라미터(45/25/15), 클럭별 프로젝트 분리(사전 빌드 3벌).

if {![string match "2024.2*" [version -short]]} {
    error "Vivado 2024.2 필요 (현재: [version -short])"
}

set stage "all"
set mhz   25
set pl_ov ""
if {$argc > 0} { set stage [lindex $argv 0] }
if {$argc > 1} { set mhz   [lindex $argv 1] }
if {$argc > 2} { set pl_ov [lindex $argv 2] }   ;# PAY_LEAD 오버라이드 (보험 빌드)
if {$mhz ni {25 45 75}} { error "mhz는 25|45|75 (VCO 1,125MHz의 약수 사다리)" }
set odiv [expr {1125 / $mhz}]

# PAY_LEAD 오버라이드 빌드는 별도 디렉터리(_pl<k>) + bit 전용 — ELF는 인터페이스
# 동일이라 기본 빌드 것을 재사용한다 (프로그래밍: program_g3.tcl <mhz> pl<k>)
set sfx ""
if {$pl_ov ne ""} {
    set sfx "_pl$pl_ov"
    if {$stage eq "all"} { set stage "bit" }
}

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set build_dir  $repo/build/vivado_g3_$mhz$sfx
set part       xc7z020clg400-1

set_param board.repoPaths [list $repo/fpga/boards]

create_project g3_chip_$mhz$sfx $build_dir -part $part -force
set bp [get_board_parts -quiet digilentinc.com:zybo-z7-20:*]
if {[llength $bp] == 0} { error "zybo-z7-20 board files not found under fpga/boards/" }
set_property board_part [lindex [lsort $bp] end] [current_project]

add_files [glob $repo/fpga/rtl/core/*.v] [glob $repo/fpga/rtl/flash/*.v]
add_files -fileset constrs_1 \
    $repo/fpga/constraints/g3_chip_pins.xdc \
    $repo/fpga/constraints/g3_cdc.xdc
set_property USED_IN_SYNTHESIS false [get_files g3_cdc.xdc]

# ---------------- BD 조립 ----------------
create_bd_design g3

set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps7
set_property CONFIG.PCW_USE_M_AXI_GP0 1 $ps7

set core0  [create_bd_cell -type module -reference core_top      core_0]
set flash0 [create_bd_cell -type module -reference flash_top_spi flash_0]

# 클럭 사다리: MMCM 분주 파라미터 (core_mmcm 헤더)
set_property CONFIG.O_DIV $odiv $core0
# PAY_LEAD 클럭별 보정 훅 (flash_spi_ctrl 헤더 — 왕복 지연 > 1UI면 1 감소).
# 현재 전 단 5 — 실측에서 전 위상 BER 0.5가 나오는 단만 여기서 내리거나,
# 미리 구운 보험 빌드(-tclargs bit <mhz> <k>)로 현장 교체
array set pay_lead {25 5 45 5 75 5}
set pl $pay_lead($mhz)
if {$pl_ov ne ""} { set pl $pl_ov }
set_property CONFIG.PAY_LEAD $pl $flash0
# X_INTERFACE_PARAMETER의 FREQ_HZ(25MHz 고정 표기)를 실주파수로 교정 — STA는
# MMCM 파생 클럭을 쓰므로 메타데이터 문제지만, XSA·IP 구성이 틀린 주파수를
# 물려받는다. 실패는 조용한 경고가 아니라 빌드 중단 (loud-failure 관례)
if {$mhz != 25} {
    foreach p {clk_core clk_sample} {
        set_property CONFIG.FREQ_HZ [expr {$mhz * 1000000}] [get_bd_pins core_0/$p]
    }
}

create_bd_port -dir I -type clk -freq_hz 125000000 clk125
connect_bd_net [get_bd_ports clk125] [get_bd_pins core_0/clk125]

set c0 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const0]
set_property CONFIG.CONST_VAL 0 $c0
connect_bd_net [get_bd_pins const0/dout] [get_bd_pins core_0/mmcm_rst]

set psr [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 psr_core]
connect_bd_net [get_bd_pins core_0/clk_core]    [get_bd_pins psr_core/slowest_sync_clk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N]  [get_bd_pins psr_core/ext_reset_in]
connect_bd_net [get_bd_pins core_0/mmcm_locked] [get_bd_pins psr_core/dcm_locked]
connect_bd_net [get_bd_pins psr_core/peripheral_aresetn] \
    [get_bd_pins core_0/aresetn] [get_bd_pins flash_0/rstn]

set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_sc]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] $sc
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0]  [get_bd_intf_pins axi_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_sc/M00_AXI] [get_bd_intf_pins core_0/s_axi]
connect_bd_net [get_bd_pins core_0/clk_core] \
    [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins axi_sc/aclk]
connect_bd_net [get_bd_pins psr_core/peripheral_aresetn] [get_bd_pins axi_sc/aresetn]

connect_bd_net [get_bd_pins core_0/clk_core]   [get_bd_pins flash_0/clk_core]
connect_bd_net [get_bd_pins core_0/clk_sample] [get_bd_pins flash_0/clk_sample]
foreach s {meas_start meas_busy meas_done meas_timeout cfg_err \
           err_bits err_reads log_rd_addr log_rd_data cfg_n_reads cfg_burst_bits} {
    connect_bd_net [get_bd_pins core_0/$s] [get_bd_pins flash_0/$s]
}

# SPI 핀 (JB — g3_chip_pins.xdc가 배치)
foreach {port dir} {spi_cs_n O spi_sclk O spi_mosi O spi_miso I} {
    create_bd_port -dir $dir $port
    connect_bd_net [get_bd_ports $port] [get_bd_pins flash_0/$port]
}

assign_bd_address
set seg [get_bd_addr_segs ps7/Data/*core_0*]
if {[llength $seg] != 1} { error "core_0 address segment not found: got '$seg'" }
set_property offset 0x43C00000 $seg
puts "== core base: [get_property OFFSET $seg]  range: [get_property RANGE $seg]"

validate_bd_design
save_bd_design

set_property synth_checkpoint_mode None [get_files g3.bd]
set wrapper [make_wrapper -files [get_files g3.bd] -top]
add_files $wrapper
set_property top g3_wrapper [current_fileset]

if {$stage eq "bd"} {
    puts "== stage=bd: BD 검증까지 완료 (합성 생략)"
    exit 0
}

# ---------------- 합성 → 구현 → 비트스트림 ----------------
generate_target all [get_files g3.bd]
launch_runs synth_1 -jobs 8
wait_on_run synth_1
if {[get_property PROGRESS [get_runs synth_1]] ne "100%"} { error "synthesis failed" }

launch_runs impl_1 -to_step write_bitstream -jobs 8
wait_on_run impl_1
if {[get_property PROGRESS [get_runs impl_1]] ne "100%"} { error "implementation failed" }

open_run impl_1
set wns [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -setup]]
set whs [get_property SLACK [get_timing_paths -max_paths 1 -nworst 1 -hold]]
puts "== timing: WNS=$wns WHS=$whs"
if {$wns < 0 || $whs < 0} { error "timing failed: WNS=$wns WHS=$whs" }

write_hw_platform -fixed -include_bit -force $build_dir/g3_chip_$mhz$sfx.xsa
puts "== bit+XSA done: $build_dir/g3_chip_$mhz$sfx.xsa"

if {$stage eq "bit"} {
    puts "== stage=bit: ELF 생략"
    exit 0
}

# ---------------- ELF (unified Vitis CLI 체인, 클럭은 env로 전달) ----------------
set vitis_exe [string map {Vivado Vitis} $::env(XILINX_VIVADO)]/bin/vitis
if {![file executable $vitis_exe]} { set vitis_exe vitis }
puts "== vitis -s ps/scripts/build_g3_sweep.py (G3_MHZ=$mhz)"
exec env G3_MHZ=$mhz $vitis_exe -s $repo/ps/scripts/build_g3_sweep.py >@stdout 2>@stderr
puts "== all done: bit=$build_dir/g3_chip_$mhz.runs/impl_1/g3_wrapper.bit elf=$repo/build/vitis_g3_$mhz/g3_sweep/build/g3_sweep.elf"
