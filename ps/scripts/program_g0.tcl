# program_g0.tcl — JTAG로 비트스트림+ELF 보드 프로그래밍 (Vivado GUI 불필요)
#
# 실행:  xsct ps/scripts/program_g0.tcl
#   (xsct의 프로젝트 명령은 이 설치본에서 불용이지만 — 로그 8 — JTAG 명령은
#    hw_server 경로라 별개. connect가 hw_server를 자동 기동한다.)
# 선행:  vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl  (bit+elf)
#        보드 USB(JTAG·UART 겸용) 연결, JP5=JTAG 부팅 모드
#
# 순서는 Vitis IDE의 Run 버튼이 하는 일과 동일: PS 리셋 → PL 비트스트림 →
# ps7_init(FSBL 대역: 클럭·DDR·MIO 초기화 — JTAG 부팅이라 FSBL이 없다) →
# ps7_post_config(비트스트림 이후 레벨시프터 해제) → ELF 다운로드 → 실행.
# UART 수신(.venv/bin/python host/capture/sweep_uart_capture.py)을 먼저 띄워놓고 돌릴 것 —
# con 직후 스트림이 시작된다.

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set bit        $repo/build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit
set elf        $repo/build/vitis/g0_sweep/build/g0_sweep.elf
set psinit     $repo/build/vitis/g0_sweep/_ide/psinit/ps7_init.tcl

foreach f [list $bit $elf $psinit] {
    if {![file exists $f]} { error "missing: $f — build_g0_loopback.tcl 먼저" }
}

# 원격 hw_server: xsct ps/scripts/program_g0.tcl tcp:<호스트>:3121 (기본: 로컬 자동 기동)
if {$argc >= 1} { connect -url [lindex $argv 0] } else { connect }
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
source $psinit
ps7_init
ps7_post_config

dow $elf
con
puts "== running: 스윕 시작됨 — UART로 #G0 SWEEP BEGIN 확인"
