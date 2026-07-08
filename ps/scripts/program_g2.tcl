# program_g2.tcl — G2 JEDEC 브링업: JTAG로 비트스트림+ELF 프로그래밍
#
# 실행:  xsct ps/scripts/program_g2.tcl <g2 앱 elf 경로>
#   elf 생략 시 비트스트림만 굽는다 (배선 전 연기 확인용)
# 선행:  vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl
#        보드 USB 연결, JP5=JTAG 부팅 모드
# ps7_init.tcl은 XSA 안에 들어 있어 여기서 자동 추출한다 — 앱 워크스페이스 위치 무관.
# UART 확인: .venv/bin/python -m serial.tools.miniterm /dev/ttyUSB1 115200

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize $script_dir/../..]
set bit        $repo/build/vivado_g2/g2_jedec.runs/impl_1/g2_wrapper.bit
set xsa        $repo/build/vivado_g2/g2_jedec.xsa
set extract    $repo/build/vivado_g2/prog

set elf ""
if {$argc > 0} { set elf [lindex $argv 0] }

foreach f [list $bit $xsa] {
    if {![file exists $f]} { error "missing: $f — build_g2_jedec.tcl 먼저" }
}
if {$elf ne "" && ![file exists $elf]} { error "missing elf: $elf" }

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

if {$elf eq ""} {
    puts "== 비트스트림만 프로그래밍 완료 (elf 미지정)"
    exit 0
}

targets -set -filter {name =~ "ARM*#0"}
source $extract/ps7_init.tcl
ps7_init
ps7_post_config

dow $elf
con
puts "== running — UART에서 JEDEC ID 출력 확인 (기대: EF 40 17)"
