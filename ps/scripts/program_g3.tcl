# program_g3.tcl — 실칩 스윕: JTAG로 비트스트림+ELF 프로그래밍 (클럭 사다리)
#
# 실행:  xsct ps/scripts/program_g3.tcl <mhz> [elf]
#   mhz = 25|45|75, elf 생략 시 build/vitis_g3_<mhz>/…/g3_sweep.elf 자동
# 선행:  build_g3_chip.tcl (해당 mhz), 사전 쓰기 #PREP PASS (flash_prep, 로그 10 ④)
# 재실행 규칙: 반드시 이 전체 경로로 — ELF만 재로드하면 MMCM 위상이 남아
#   phase_pos_mismatch로 거부된다 (temp.md/로그 10 재실행 규칙, 의도된 방어).
# UART 캡처: .venv/bin/python host/capture/sweep_uart_capture.py --uid <16hex> (래퍼 run_sweep_chip.py 권장)

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
# BUILD_DIR 환경변수로 산출물 폴더 선택 (기본 build). 재기준선 A/B용 — 워크플로 8 R:
#   BUILD_DIR=<폴더> xsct ps/scripts/program_g3.tcl 25   (래퍼 경유도 동일: 환경변수가 xsct 에 상속)
#   A/B 는 생략 결정, build_2024.2 는 2026-09-21 삭제 — 현재 쓰는 곳 없다
set build      $repo/build
if {[info exists env(BUILD_DIR)]} { set build $repo/$env(BUILD_DIR) }

if {$argc < 1} { error "usage: xsct program_g3.tcl <mhz 25|45|75> \[pl<k>\] \[elf\]" }
set mhz [lindex $argv 0]
if {$mhz ni {25 45 75}} { error "mhz는 25|45|75" }

# pl<k> = PAY_LEAD 보험 비트스트림 선택 (build_g3_chip.tcl -tclargs bit <mhz> <k>).
# ELF는 인터페이스 동일 — 기본 빌드 것을 그대로 쓴다
set sfx ""
set elf $build/vitis_g3_$mhz/g3_sweep/build/g3_sweep.elf
set rest [lrange $argv 1 end]
if {[llength $rest] > 0 && [string match "pl*" [lindex $rest 0]]} {
    set sfx "_[lindex $rest 0]"
    set rest [lrange $rest 1 end]
}
if {[llength $rest] > 0} { set elf [lindex $rest 0] }

set bit     $build/vivado_g3_$mhz$sfx/g3_chip_$mhz$sfx.runs/impl_1/g3_wrapper.bit
set xsa     $build/vivado_g3_$mhz$sfx/g3_chip_$mhz$sfx.xsa
set extract $build/vivado_g3_$mhz$sfx/prog

foreach f [list $bit $xsa $elf] {
    if {![file exists $f]} { error "missing: $f — build_g3_chip.tcl (mhz=$mhz) 먼저" }
}

file mkdir $extract
if {[catch {exec unzip -o -j $xsa ps7_init.tcl -d $extract} msg]} {
    error "XSA에서 ps7_init.tcl 추출 실패 (unzip 필요): $msg"
}

connect
# 케이블 인식 지연 대비 재시도 — 없으면 원인 짚는 에러로
set ok 0
for {set i 0} {$i < 10} {incr i} {
    if {![catch {targets -set -filter {name =~ "APU*"}}]} { set ok 1; break }
    after 1000
}
if {!$ok} { error "JTAG 타겟 없음 — 보드 USB 연결·전원·JP5(JTAG 모드) 확인" }
rst -system
after 1000

fpga $bit

targets -set -filter {name =~ "ARM*#0"}
source $extract/ps7_init.tcl
ps7_init
ps7_post_config

dow $elf
con
puts "== running ($mhz MHz) — sweep_uart_capture.py --uid <16hex> (래퍼 run_sweep_chip.py 권장) 로 수집"
