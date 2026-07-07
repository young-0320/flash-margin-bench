`timescale 1ns / 1ps
// core_top.v — core 블록 최상위 (fpga/rtl/core/): MMCM 위상 제어 + AXI-Lite 레지스터
//
// 결선만 한다 — 규약 집행은 core_axil_regs(게이팅·sticky), 핸드셰이크는
// core_phase_ctrl, 프리미티브는 core_mmcm에 있다.
//
// 통합(블록 디자인) 전제:
//  - s_axi_*는 clk_core 동기 — Zynq GP 포트/인터커넥트 ACLK에 이 모듈의
//    clk_core 출력을 물린다 (계약 §1: 제어 전 도메인 clk_core, CDC 없음)
//  - aresetn은 clk_core 동기 해제 (proc_sys_reset, slowest_sync_clk=clk_core)
//  - mmcm_rst는 평시 0 고정 (재로크 필요 시에만)
//  - clk_sample은 flash 블록 MISO 캡처 경로 전용 (계약 §1 A안)

module core_top (
    input  wire        clk125,          // 보드 125MHz, K17 (계약 §5)
    input  wire        mmcm_rst,        // 비동기 high
    input  wire        aresetn,         // clk_core 동기, active low

    output wire        clk_core,
    output wire        clk_sample,
    output wire        mmcm_locked,

    // AXI4-Lite slave (clk_core 동기)
    input  wire [5:0]  s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output wire        s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [5:0]  s_axi_araddr,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output wire        s_axi_rvalid,
    input  wire        s_axi_rready,

    // flash 경계 (contract §2, 전부 clk_core 동기)
    output wire        meas_start,
    input  wire        meas_busy,
    input  wire        meas_done,
    input  wire        meas_timeout,    // §2 추가 제안 신호 (R10)
    input  wire        cfg_err,         // §2 추가 제안 신호 (R11)
    input  wire [31:0] err_bits,
    input  wire [31:0] err_reads,
    output wire [11:0] log_rd_addr,
    input  wire [15:0] log_rd_data,
    output wire [15:0] cfg_n_reads,
    output wire [15:0] cfg_burst_bits
);

    wire        psen, psincdec, psdone;
    wire        ps_busy;
    wire signed [31:0] phase_pos;
    wire        phase_cmd, phase_incdec;

    core_mmcm u_mmcm (
        .clk_in_125 (clk125),
        .rst        (mmcm_rst),
        .clk_core   (clk_core),
        .clk_sample (clk_sample),
        .locked     (mmcm_locked),
        .psen       (psen),
        .psincdec   (psincdec),
        .psdone     (psdone)
    );

    core_phase_ctrl u_phase_ctrl (
        .clk        (clk_core),
        .rstn       (aresetn),
        .cmd_valid  (phase_cmd),
        .cmd_incdec (phase_incdec),
        .psen       (psen),
        .psincdec   (psincdec),
        .psdone     (psdone),
        .ps_busy    (ps_busy),
        .phase_pos  (phase_pos)
    );

    core_axil_regs u_regs (
        .clk            (clk_core),
        .rstn           (aresetn),

        .s_axi_awaddr   (s_axi_awaddr),
        .s_axi_awvalid  (s_axi_awvalid),
        .s_axi_awready  (s_axi_awready),
        .s_axi_wdata    (s_axi_wdata),
        .s_axi_wstrb    (s_axi_wstrb),
        .s_axi_wvalid   (s_axi_wvalid),
        .s_axi_wready   (s_axi_wready),
        .s_axi_bresp    (s_axi_bresp),
        .s_axi_bvalid   (s_axi_bvalid),
        .s_axi_bready   (s_axi_bready),
        .s_axi_araddr   (s_axi_araddr),
        .s_axi_arvalid  (s_axi_arvalid),
        .s_axi_arready  (s_axi_arready),
        .s_axi_rdata    (s_axi_rdata),
        .s_axi_rresp    (s_axi_rresp),
        .s_axi_rvalid   (s_axi_rvalid),
        .s_axi_rready   (s_axi_rready),

        .meas_start     (meas_start),
        .meas_busy      (meas_busy),
        .meas_done      (meas_done),
        .meas_timeout   (meas_timeout),
        .cfg_err        (cfg_err),
        .err_bits       (err_bits),
        .err_reads      (err_reads),
        .log_rd_addr    (log_rd_addr),
        .log_rd_data    (log_rd_data),
        .cfg_n_reads    (cfg_n_reads),
        .cfg_burst_bits (cfg_burst_bits),

        .phase_cmd      (phase_cmd),
        .phase_incdec   (phase_incdec),
        .ps_busy        (ps_busy),
        .phase_pos      (phase_pos),
        .mmcm_locked    (mmcm_locked)
    );

endmodule
