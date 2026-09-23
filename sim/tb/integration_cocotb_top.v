`timescale 1ns / 1ps

// Core + loopback flash integration wrapper for I1-I3.
module integration_cocotb_top;
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

    wire clk_core, clk_sample, mmcm_locked;
    wire meas_start, meas_busy, meas_done, meas_timeout, cfg_err;
    wire [31:0] err_bits, err_reads;
    wire [11:0] log_rd_addr;
    wire [15:0] log_rd_data, cfg_n_reads, cfg_burst_bits;
    wire pattern_out;
    reg  pattern_del = 1'b0;
    wire pattern_in = pattern_del;

    // Small transport delay models a real jumper without changing the
    // protocol. The actual loopback data path remains flash_top's RTL.
    always @(pattern_out) pattern_del <= #1.0 pattern_out;

    core_top u_core (
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

    flash_top u_flash (
        .clk_core(clk_core), .clk_sample(clk_sample), .rstn(aresetn),
        .meas_start(meas_start), .meas_busy(meas_busy), .meas_done(meas_done),
        .meas_timeout(meas_timeout), .cfg_err(cfg_err), .err_bits(err_bits),
        .err_reads(err_reads), .log_rd_addr(log_rd_addr),
        .log_rd_data(log_rd_data), .cfg_n_reads(cfg_n_reads),
        .cfg_burst_bits(cfg_burst_bits), .pattern_out(pattern_out),
        .pattern_in(pattern_in)
    );
endmodule
