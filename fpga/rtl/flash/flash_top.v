`timescale 1ns / 1ps
// flash_top.v — flash 블록 최상위 (G0 루프백 프런트엔드, 계약 R7)
//
// 패턴 출력 핀 → 점퍼 → 입력 핀 경로가 실칩 자리를 대신한다. 계약 §2 인터페이스는
// 실칩 전환 시에도 불변 — core는 이 블록이 무엇을 측정하는지 모른다.
//
// CDC는 전부 이 블록 소유 (계약 1-1):
//  - run   (clk_core → clk_sample, 2FF): RX 무장/해제
//  - rx_done (clk_sample → clk_core, 2FF): 집계 완료
//  - err_bits/err_reads: 멀티비트지만 rx_done 이전에 멈춘 준정적 값 — done 관측
//    후에만 읽힌다는 프로토콜(R3)이 안전성의 근거. 동기화기 불요
//  - e_i 버퍼: 듀얼 클럭 BRAM, 동시 접근은 R3가 배제
//
// 통합(top+XDC) 시: pattern_out → JE1(V12), pattern_in ← JE2(W16),
// clk_core/clk_sample 도메인 간 set_max_delay(준정적 경로) 제약은 XDC 단계에서.

module flash_top (
    input  wire        clk_core,
    input  wire        clk_sample,
    // X_INTERFACE_*: BD 모듈 참조용 극성 명시 (proc_sys_reset peripheral_aresetn 연결)
    (* X_INTERFACE_INFO = "xilinx.com:signal:reset:1.0 rstn RST" *)
    (* X_INTERFACE_PARAMETER = "POLARITY ACTIVE_LOW" *)
    input  wire        rstn,            // clk_core 동기

    // 계약 §2 (전부 clk_core 동기)
    input  wire        meas_start,
    output wire        meas_busy,
    output wire        meas_done,
    output wire        meas_timeout,    // §2 추인 대상 신호 (R10)
    output wire        cfg_err,         // §2 추인 대상 신호 (R11)
    output wire [31:0] err_bits,
    output wire [31:0] err_reads,
    input  wire [11:0] log_rd_addr,
    output wire [15:0] log_rd_data,
    input  wire [15:0] cfg_n_reads,
    input  wire [15:0] cfg_burst_bits,

    // 루프백 핀
    output wire        pattern_out,     // JE1 (V12)
    input  wire        pattern_in       // JE2 (W16)
);

    wire        run, run_s;
    wire        rx_done, rx_done_s;
    wire [15:0] n_lat, b_lat;
    wire        log_we;
    wire [11:0] log_waddr;
    wire [15:0] log_wdata;

    flash_sync2 u_sync_run  (.clk(clk_sample), .d(run),     .q(run_s));
    flash_sync2 u_sync_done (.clk(clk_core),   .d(rx_done), .q(rx_done_s));

    flash_ctrl u_ctrl (
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
        .pattern_out    (pattern_out)
    );

    flash_rx u_rx (
        .clk_sample (clk_sample),
        .din_pin    (pattern_in),
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
