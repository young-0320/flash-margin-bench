# program_core_smoke.tcl — core_smoke를 G0 비트스트림 위에 JTAG 로드
#
# 실행:  xsct ps/scripts/program_core_smoke.tcl
# 선행:  vitis -s ps/scripts/build_core_smoke.py  (elf)
#        build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit
# 결과 확인: miniterm /dev/ttyUSB1 115200 — 6개 테스트 PASS/FAIL 로그
# (TEST4·5는 JE1↔JE2 점퍼가 있어야 측정 경로까지 완주 — 없으면 TIMEOUT FAIL이 정상 서명)

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set bit        $repo/build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit
set elf        $repo/build/vitis_smoke/core_smoke/build/core_smoke.elf
set psinit     $repo/build/vitis_smoke/core_smoke/_ide/psinit/ps7_init.tcl

foreach f [list $bit $elf $psinit] {
    if {![file exists $f]} { error "missing: $f — build_core_smoke.py 먼저" }
}

# 원격 hw_server: xsct ps/scripts/program_core_smoke.tcl tcp:<호스트>:3121 (기본: 로컬 자동 기동)
if {$argc >= 1} { connect -url [lindex $argv 0] } else { connect }
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
source $psinit
ps7_init
ps7_post_config

dow $elf
con
puts "== running: UART로 브링업 테스트 로그 확인"
