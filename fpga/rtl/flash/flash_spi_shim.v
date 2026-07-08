`timescale 1ns / 1ps
// flash_spi_shim.v — clk_sample 도메인 프레이밍 심: flash_rx를 무수정 재사용하기
// 위한 어댑터. 루프백에서는 프리앰블(1×4)이 칩 대신 배선을 타고 왔지만, SPI
// 칩은 프리앰블을 보내줄 수 없다 — 대신 마스터의 pay(데이터 창 예고, 2FF 동기
// 완료본)를 받아 로컬에서 1×4를 합성해 앞에 붙이고, 그 뒤 캡처된 MISO로 먹스.
//
// pay_s가 0인 구간은 0을 출력 — cmd/addr/dummy 40사이클 + CS 갭이 flash_rx의
// 0-run(≥8) 자격 구간을 자동 충족한다. MISO의 Hi-Z 구간은 먹스가 차단하므로
// RX에 도달하지 않는다(핀 풀다운은 XDC에서 보험으로 추가).
//
// 정렬: 프리앰블 첫 1(=t0)과 실제 페이로드 첫 샘플의 간격이 flash_rx의 3후보
// 창 {t0+3, t0+4, t0+5}에 들어오도록 pay 상승 시점(PAY_LEAD)을 마스터가 조정.
// 출력이 레지스터라 프리앰블·MISO 두 경로의 지연이 같고, RX 내부 캡처 사슬
// (cap→meta→d)은 양쪽에 공통이라 정렬에서 상쇄된다.

module flash_spi_shim (
    input  wire clk_sample,
    input  wire pay_s,       // 데이터 창 예고 (2FF 동기 완료)
    input  wire cap_miso,    // IOB 캡처 완료된 MISO (top 소유 — 측정 그 자체)
    output reg  din          // → flash_rx.din_pin
);

    reg [2:0] pcnt;

    always @(posedge clk_sample) begin
        if (!pay_s) begin
            pcnt <= 3'd0;
            din  <= 1'b0;
        end else if (pcnt < 3'd4) begin
            pcnt <= pcnt + 3'd1;
            din  <= 1'b1;               // 합성 프리앰블
        end else
            din  <= cap_miso;           // 페이로드
    end

endmodule
