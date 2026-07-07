# g0_cdc.xdc — clk_core ↔ clk_sample CDC 제약 (구현 전용: build_g0_loopback.tcl이 USED_IN_SYNTHESIS=false 설정)
#
# 두 클럭은 같은 MMCM의 CLKOUT0/1 — 동일 주파수, clk_sample만 동적 위상 시프트.
# STA는 빌드 시점 위상(0)만 보므로, 스윕 중 위상이 최대 1UI 움직여도 성립해야 하는
# 크로싱은 전부 위상 무관 구조여야 한다 (계약 1-1):
#   - run / rx_done: 2FF 동기화기 (flash_sync2, ASYNC_REG)
#   - err_bits/err_reads/e_i BRAM: 준정적 — rx_done 이전에 값 정지, R3가 읽기 시점 보장
# → 양방향 set_max_delay -datapath_only 1주기(40ns). 이 제약이 빠지면 위상 0 기준의
#   가짜 셋업 요구로 라우팅이 흔들리거나, 스윕 도중 조용히 틀어진다.
#
# get_pins가 하나도 안 잡히면 get_clocks가 하드 에러 → 계층 이름 변경 사고를 침묵 대신
# 빌드 실패로 노출 (의도된 동작, -quiet 금지)

set clk_core_c   [get_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ */u_mmcm/u_mmcm/CLKOUT0}]]
set clk_sample_c [get_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ */u_mmcm/u_mmcm/CLKOUT1}]]

set_max_delay -datapath_only -from $clk_core_c -to $clk_sample_c 40.000
set_max_delay -datapath_only -from $clk_sample_c -to $clk_core_c 40.000

# pattern_in → IOB 캡처 플롭 경로가 측정 대상 그 자체 — 타이밍 도구가 "고치면" 안 됨.
# pattern_out은 점퍼 루프백이라 외부 타이밍 계약 없음. 둘 다 STA 제외(미제약 경고 소거).
set_false_path -from [get_ports pattern_in]
set_false_path -to [get_ports pattern_out]
