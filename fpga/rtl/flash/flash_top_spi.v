`timescale 1ns / 1ps
// flash_top_spi.v — flash 블록 최상위 (실칩 SPI 프런트엔드, 계약 R7)
//
// flash_top(루프백)과 계약 §2 인터페이스가 완전히 동일 — core·스윕 C·계약은
// 무수정으로 이 블록과 맞물린다(로그 10 가정 1: 루프백 top과 병존, 빌드 스크립트가
// 선택). 교체된 것은 프런트엔드뿐:
//   TX: flash_ctrl(패턴 방출) → flash_spi_ctrl(0x0B 시퀀서) + ODDR SCLK(R9)
//   RX 입력: 루프백 핀 → IOB 캡처 MISO + flash_spi_shim(프리앰블 합성)
//   flash_rx(±1 프레이밍 3후보 재정렬)·flash_logbuf는 그대로 재사용.
//
// CDC는 전부 이 블록 소유 (계약 1-1):
//  - run, pay (clk_core → clk_sample, 2FF) / rx_done (clk_sample → clk_core, 2FF)
//  - err_*·e_i 버퍼: 루프백과 동일한 준정적 근거 (R3)
//
// 통합(top+XDC) 시: JB 핀 = 로그 9 표 그대로 (CS V8 / MOSI W8 / MISO U7 /
// SCLK V7), MISO에 PULLDOWN, clk 도메인 간 set_max_delay는 루프백 XDC 준용.

module flash_top_spi #(
    parameter PAY_LEAD = 5   // 클럭별 재보정 훅 (flash_spi_ctrl 헤더 — 75MHz 임계)
) (
    input  wire        clk_core,
    input  wire        clk_sample,
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rstn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        rstn,            // clk_core 동기

    // 계약 §2 (전부 clk_core 동기)
    input  wire        meas_start,
    output wire        meas_busy,
    output wire        meas_done,
    output wire        meas_timeout,
    output wire        cfg_err,
    output wire [31:0] err_bits,
    output wire [31:0] err_reads,
    input  wire [11:0] log_rd_addr,
    output wire [15:0] log_rd_data,
    input  wire [15:0] cfg_n_reads,
    input  wire [15:0] cfg_burst_bits,

    // SPI 핀 (JB — 로그 9 핀 표)
    output wire        spi_cs_n,
    output wire        spi_sclk,
    output wire        spi_mosi,
    input  wire        spi_miso
);

    wire        run, run_s;
    wire        rx_done, rx_done_s;
    wire        pay, pay_s;
    wire        sclk_en;
    wire [15:0] n_lat, b_lat;
    wire        log_we;
    wire [11:0] log_waddr;
    wire [15:0] log_wdata;
    wire        din;

    flash_sync2 u_sync_run  (.clk(clk_sample), .d(run),     .q(run_s));
    flash_sync2 u_sync_pay  (.clk(clk_sample), .d(pay),     .q(pay_s));
    flash_sync2 u_sync_done (.clk(clk_core),   .d(rx_done), .q(rx_done_s));

    flash_spi_ctrl #(.PAY_LEAD(PAY_LEAD)) u_ctrl (
        .clk            (clk_core),
        .rstn           (rstn),
        .meas_start     (meas_start),
        .cfg_n_reads    (cfg_n_reads),
        .cfg_burst_bits (cfg_burst_bits),
        .meas_busy      (meas_busy),
        .meas_done      (meas_done),
        .meas_timeout   (meas_timeout),
        .cfg_err        (cfg_err),
        .run            (run),
        .rx_done_s      (rx_done_s),
        .n_lat          (n_lat),
        .b_lat          (b_lat),
        .spi_cs_n       (spi_cs_n),
        .spi_mosi       (spi_mosi),
        .sclk_en        (sclk_en),
        .pay            (pay)
    );

    // R9: SCLK = clk_core 무분주 포워딩. D1=0/D2=en — 상승 에지가 사이클 중앙에
    // 와서 에지 런치되는 MOSI·CS에 반주기 셋업/홀드 확보 (mode 0, 유휴 low)
    ODDR #(
        .DDR_CLK_EDGE ("SAME_EDGE"),
        .INIT         (1'b0),
        .SRTYPE       ("SYNC")
    ) u_sclk_oddr (
        .Q  (spi_sclk),
        .C  (clk_core),
        .CE (1'b1),
        .D1 (1'b0),
        .D2 (sclk_en),
        .R  (1'b0),
        .S  (1'b0)
    );

    // MISO 캡처 플롭 — 측정 그 자체 (루프백의 flash_rx cap과 같은 역할, IOB 배치)
    (* IOB = "TRUE" *) reg cap_miso;
    always @(posedge clk_sample) cap_miso <= spi_miso;

    flash_spi_shim u_shim (
        .clk_sample (clk_sample),
        .pay_s      (pay_s),
        .cap_miso   (cap_miso),
        .din        (din)
    );

    flash_rx u_rx (
        .clk_sample (clk_sample),
        .din_pin    (din),
        .run_s      (run_s),
        .n_lat      (n_lat),
        .b_lat      (b_lat),
        .rx_done    (rx_done),
        .err_bits   (err_bits),
        .err_reads  (err_reads),
        .log_we     (log_we),
        .log_waddr  (log_waddr),
        .log_wdata  (log_wdata)
    );

    flash_logbuf u_logbuf (
        .wclk  (clk_sample),
        .we    (log_we),
        .waddr (log_waddr),
        .wdata (log_wdata),
        .rclk  (clk_core),
        .raddr (log_rd_addr),
        .rdata (log_rd_data)
    );

endmodule
