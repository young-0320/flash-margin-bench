`timescale 1ns / 1ps

// Cocotb wrapper for the core_top register/reset contract (C1-C6).
// The flash-side inputs are held idle; C1 only reads the AXI-Lite state.
module core_cocotb_top;
    reg clk125 = 1'b0;
    always #4 clk125 = ~clk125;

    reg aresetn = 1'b0;

    reg  [5:0]  s_axi_awaddr = 6'd0;
    reg         s_axi_awvalid = 1'b0;
    wire        s_axi_awready;
    reg  [31:0] s_axi_wdata = 32'd0;
    reg  [3:0]  s_axi_wstrb = 4'd0;
    reg         s_axi_wvalid = 1'b0;
    wire        s_axi_wready;
    wire [1:0]  s_axi_bresp;
    wire        s_axi_bvalid;
    reg         s_axi_bready = 1'b0;

    reg  [5:0]  s_axi_araddr = 6'd0;
    reg         s_axi_arvalid = 1'b0;
    wire        s_axi_arready;
    wire [31:0] s_axi_rdata;
    wire [1:0]  s_axi_rresp;
    wire        s_axi_rvalid;
    reg         s_axi_rready = 1'b0;

    reg         meas_busy = 1'b0;
    reg         meas_done = 1'b0;
    reg         meas_timeout = 1'b0;
    reg         cfg_err = 1'b0;
    reg  [31:0] err_bits = 32'd0;
    reg  [31:0] err_reads = 32'd0;
    wire [11:0] log_rd_addr;
    reg  [15:0] log_rd_data = 16'd0;
    wire [15:0] cfg_n_reads;
    wire [15:0] cfg_burst_bits;

    wire clk_core;
    wire clk_sample;
    wire mmcm_locked;
    wire meas_start;

    core_top dut (
        .clk125(clk125), .mmcm_rst(1'b0), .aresetn(aresetn),
        .clk_core(clk_core), .clk_sample(clk_sample), .mmcm_locked(mmcm_locked),
        .s_axi_awaddr(s_axi_awaddr), .s_axi_awvalid(s_axi_awvalid),
        .s_axi_awready(s_axi_awready), .s_axi_wdata(s_axi_wdata),
        .s_axi_wstrb(s_axi_wstrb), .s_axi_wvalid(s_axi_wvalid),
        .s_axi_wready(s_axi_wready), .s_axi_bresp(s_axi_bresp),
        .s_axi_bvalid(s_axi_bvalid), .s_axi_bready(s_axi_bready),
        .s_axi_araddr(s_axi_araddr), .s_axi_arvalid(s_axi_arvalid),
        .s_axi_arready(s_axi_arready), .s_axi_rdata(s_axi_rdata),
        .s_axi_rresp(s_axi_rresp), .s_axi_rvalid(s_axi_rvalid),
        .s_axi_rready(s_axi_rready), .meas_start(meas_start),
        .meas_busy(meas_busy), .meas_done(meas_done),
        .meas_timeout(meas_timeout), .cfg_err(cfg_err), .err_bits(err_bits),
        .err_reads(err_reads), .log_rd_addr(log_rd_addr),
        .log_rd_data(log_rd_data), .cfg_n_reads(cfg_n_reads),
        .cfg_burst_bits(cfg_burst_bits)
    );
endmodule
