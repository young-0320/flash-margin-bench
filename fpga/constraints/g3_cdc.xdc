# g3_cdc.xdc — 실칩(G3) clk_core ↔ clk_sample CDC 제약 (구현 전용)
#
# g0_cdc.xdc의 G3 대응물. 두 가지가 다르다:
#  1. 루프백 전용 pattern_in/out false_path 제거 — G3에 없는 포트라 남기면
#     빌드마다 크리티컬 워닝이 "정상"이 되어, 진짜 제약 사고를 가리는 소음이 된다
#     (SPI 핀 false_path는 g3_chip_pins.xdc 소유). 리뷰 wf_16617fb7 발견 #2.
#  2. max_delay를 40ns(25MHz 1주기)가 아니라 13.333ns(75MHz 1주기)로 —
#     사다리 전 단 공통 하한. pay CDC(합성 프리앰블 예고)는 경로 지연이
#     clk_sample 1주기를 넘으면 pay_s가 한 사이클 늦어져 PAY_LEAD 유도
#     (flash_spi_ctrl 헤더)의 전제가 깨진다. 40ns를 그대로 두면 75MHz에서
#     라우터가 3주기짜리 경로를 합법으로 깔아도 타이밍 리포트가 침묵한다.
#     25/45MHz 빌드에 과잉 제약이지만 -datapath_only 13.3ns는 라우팅에 부담 없음.
#     리뷰 wf_16617fb7 발견 #3~5.
#
# 크로싱 구조(2FF·준정적)는 g0_cdc.xdc 헤더 설명과 동일. get_pins 미매치는
# 하드 에러 — 계층 이름 변경 사고를 침묵 대신 빌드 실패로 노출 (-quiet 금지).

set clk_core_c   [get_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ */u_mmcm/u_mmcm/CLKOUT0}]]
set clk_sample_c [get_clocks -of_objects [get_pins -hierarchical -filter {NAME =~ */u_mmcm/u_mmcm/CLKOUT1}]]

set_max_delay -datapath_only -from $clk_core_c -to $clk_sample_c 13.333
set_max_delay -datapath_only -from $clk_sample_c -to $clk_core_c 13.333

# flash_rx.cap의 IOB=TRUE는 루프백(핀 직결) 전제 — 실칩 top에서는 진짜 캡처가
# flash_top_spi.cap_miso(IOB)이고 u_rx.cap은 심 뒤의 내부 파이프 단이라 속성이
# 무의미하다(Place 30-73 크리티컬 워닝). flash_rx 무수정 재사용(R7 자산 보존)의
# 부산물이므로 RTL이 아니라 여기서 해제한다. 미매치 시 하드 에러 = 계층 변경 감지.
set_property IOB FALSE [get_cells -hierarchical -filter {NAME =~ */u_rx/cap_reg}]
