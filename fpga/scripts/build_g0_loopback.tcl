# build_g0_loopback.tcl — G0 루프백: 프로젝트 재생성 → BD 조립 → 비트스트림·XSA → ELF 원샷
#
# 실행:  vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl [-tclargs <stage>]
#   stage = all(기본: bit+XSA+elf) | bit(비트스트림·XSA까지) | bd(BD 검증까지 — 빠른 반복용)
# ELF 단계는 ps/scripts/build_g0_sweep.py(unified Vitis CLI)를 체인 호출한다.
# 보드 프로그래밍은 ps/scripts/program_g0.tcl (xsct, GUI 불필요).
#
# 설계 소스는 RTL + 이 tcl + XDC가 전부다 (.xpr은 생성물, build/ 커밋 금지).
# core/flash는 Package IP가 아니라 BD 모듈 참조(Add Module)로 들어간다 —
# RTL 수정이 재패키징 없이 다음 빌드에 바로 반영된다.

# 버전 가드 (메모리/운영 결정: 2024.2 단독 빌드 — 상위 버전 산출물은 조원이 못 연다)
if {![string match "2024.2*" [version -short]]} {
    error "Vivado 2024.2 필요 (현재: [version -short])"
}

set stage "all"
if {$argc > 0} { set stage [lindex $argv 0] }

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set build_dir  $repo/build/vivado
set part       xc7z020clg400-1

# 벤더링된 Digilent 보드파일 (fpga/boards/) — PS7 프리셋(DDR·UART1 MIO)의 출처
set_param board.repoPaths [list $repo/fpga/boards]

create_project g0_loopback $build_dir -part $part -force
set bp [get_board_parts -quiet digilentinc.com:zybo-z7-20:*]
if {[llength $bp] == 0} { error "zybo-z7-20 board files not found under fpga/boards/" }
set_property board_part [lindex [lsort $bp] end] [current_project]

add_files [glob $repo/fpga/rtl/core/*.v] [glob $repo/fpga/rtl/flash/*.v]
add_files -fileset constrs_1 \
    $repo/fpga/constraints/g0_pins.xdc \
    $repo/fpga/constraints/g0_cdc.xdc
# CDC 제약은 구현 전용 — 파일 헤더 참조
set_property USED_IN_SYNTHESIS false [get_files g0_cdc.xdc]

# ---------------- BD 조립 ----------------
create_bd_design g0

# Zynq PS: 보드 프리셋(DDR·UART1) 적용, GP0만 사용
set ps7 [create_bd_cell -type ip -vlnv xilinx.com:ip:processing_system7:5.5 ps7]
apply_bd_automation -rule xilinx.com:bd_rule:processing_system7 \
    -config {make_external "FIXED_IO, DDR" apply_board_preset "1" Master "Disable" Slave "Disable"} $ps7
set_property CONFIG.PCW_USE_M_AXI_GP0 1 $ps7

# core/flash 모듈 참조
set core0  [create_bd_cell -type module -reference core_top  core_0]
set flash0 [create_bd_cell -type module -reference flash_top flash_0]

# 보드 125MHz (K17) — PS와 무관한 PL 입력 클럭
create_bd_port -dir I -type clk -freq_hz 125000000 clk125
connect_bd_net [get_bd_ports clk125] [get_bd_pins core_0/clk125]

# mmcm_rst 평시 0 고정 (core_top 헤더 전제 — 재로크는 재구성으로만)
set c0 [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 const0]
set_property CONFIG.CONST_VAL 0 $c0
connect_bd_net [get_bd_pins const0/dout] [get_bd_pins core_0/mmcm_rst]

# 리셋: FCLK_RESET0_N + MMCM lock → clk_core 동기 해제 (core_top 헤더 전제)
set psr [create_bd_cell -type ip -vlnv xilinx.com:ip:proc_sys_reset:5.0 psr_core]
connect_bd_net [get_bd_pins core_0/clk_core]    [get_bd_pins psr_core/slowest_sync_clk]
connect_bd_net [get_bd_pins ps7/FCLK_RESET0_N]  [get_bd_pins psr_core/ext_reset_in]
connect_bd_net [get_bd_pins core_0/mmcm_locked] [get_bd_pins psr_core/dcm_locked]
connect_bd_net [get_bd_pins psr_core/peripheral_aresetn] \
    [get_bd_pins core_0/aresetn] [get_bd_pins flash_0/rstn]

# AXI: PS GP0 → SmartConnect → core. ACLK 전부 clk_core (계약 §1: 제어 전 도메인 clk_core)
set sc [create_bd_cell -type ip -vlnv xilinx.com:ip:smartconnect:1.0 axi_sc]
set_property -dict [list CONFIG.NUM_SI 1 CONFIG.NUM_MI 1] $sc
connect_bd_intf_net [get_bd_intf_pins ps7/M_AXI_GP0]  [get_bd_intf_pins axi_sc/S00_AXI]
connect_bd_intf_net [get_bd_intf_pins axi_sc/M00_AXI] [get_bd_intf_pins core_0/s_axi]
connect_bd_net [get_bd_pins core_0/clk_core] \
    [get_bd_pins ps7/M_AXI_GP0_ACLK] [get_bd_pins axi_sc/aclk]
connect_bd_net [get_bd_pins psr_core/peripheral_aresetn] [get_bd_pins axi_sc/aresetn]

# core ↔ flash 계약 §2 신호 + 클럭
connect_bd_net [get_bd_pins core_0/clk_core]   [get_bd_pins flash_0/clk_core]
connect_bd_net [get_bd_pins core_0/clk_sample] [get_bd_pins flash_0/clk_sample]
foreach s {meas_start meas_busy meas_done meas_timeout cfg_err \
           err_bits err_reads log_rd_addr log_rd_data cfg_n_reads cfg_burst_bits} {
    connect_bd_net [get_bd_pins core_0/$s] [get_bd_pins flash_0/$s]
}

# 루프백 핀 (JE1/JE2 — g0_pins.xdc가 배치)
create_bd_port -dir O pattern_out
create_bd_port -dir I pattern_in
connect_bd_net [get_bd_ports pattern_out] [get_bd_pins flash_0/pattern_out]
connect_bd_net [get_bd_ports pattern_in]  [get_bd_pins flash_0/pattern_in]

# 주소 배정 — 베어메탈 #define과 일치해야 하는 고정 베이스
assign_bd_address
set seg [get_bd_addr_segs ps7/Data/*core_0*]
if {[llength $seg] != 1} { error "core_0 address segment not found: got '$seg'" }
set_property offset 0x43C00000 $seg
puts "== core base: [get_property OFFSET $seg]  range: [get_property RANGE $seg]"

validate_bd_design
save_bd_design

# 모듈 참조 포함 전체를 톱 합성으로 (OOC 분할 없이 — XDC 계층 매칭 단순화)
set_property synth_checkpoint_mode None [get_files g0.bd]
set wrapper [make_wrapper -files [get_files g0.bd] -top]
add_files $wrapper
set_property top g0_wrapper [current_fileset]

if {$stage eq "bd"} {
    puts "== stage=bd: BD 검증까지 완료 (합성 생략)"
    exit 0
}

# ---------------- 합성 → 구현 → 비트스트림 ----------------
generate_target all [get_files g0.bd]
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

# Vitis 입력 (.xsa, 비트스트림 포함)
write_hw_platform -fixed -include_bit -force $build_dir/g0_loopback.xsa
puts "== bit+XSA done: $build_dir/g0_loopback.xsa"

if {$stage eq "bit"} {
    puts "== stage=bit: ELF 생략"
    exit 0
}

# ---------------- ELF (unified Vitis CLI 체인) ----------------
# 실패 시 exec가 에러를 던져 빌드 전체가 시끄럽게 죽는다
set vitis_exe [string map {Vivado Vitis} $::env(XILINX_VIVADO)]/bin/vitis
if {![file executable $vitis_exe]} { set vitis_exe vitis }
puts "== vitis -s ps/scripts/build_g0_sweep.py"
exec $vitis_exe -s $repo/ps/scripts/build_g0_sweep.py >@stdout 2>@stderr
puts "== all done: bit=$build_dir/g0_loopback.runs/impl_1/g0_wrapper.bit elf=$repo/build/vitis/g0_sweep/build/g0_sweep.elf"
