`timescale 1ns / 1ps
// Cocotb-only wrapper. The licensed Winbond source stays outside this repository;
// define WINBOND_MODEL and add W25Q64JV.v to the compile sources to enable it.

module flash_spi_cocotb_top;
    reg         clk_core = 1'b0;
    reg         clk_sample = 1'b0;
    reg         rstn = 1'b0;
    reg         meas_start = 1'b0;
    reg  [15:0] cfg_n_reads = 16'd4;
    reg  [15:0] cfg_burst_bits = 16'd64;
    reg  [11:0] log_rd_addr = 12'd0;
    reg         spi_miso = 1'b0;          // cocotb/manual model input
    reg         use_vendor_model = 1'b0;
    reg         use_timing_probe = 1'b0;
    reg         timing_probe_cs_n = 1'b1;
    reg         timing_probe_clk = 1'b0;
    reg         timing_probe_dio = 1'b0;
    reg  [15:0] vendor_extra_delay_ns = 16'd0;
    reg         block_rx_done = 1'b0;
    reg  [7:0]  vendor_command_xor_mask = 8'd0;
    reg         force_vendor_miso_low = 1'b0;

    wire        meas_busy;
    wire        meas_done;
    wire        meas_timeout;
    wire        cfg_err;
    wire [31:0] err_bits;
    wire [31:0] err_reads;
    wire [15:0] log_rd_data;
    wire        spi_cs_n;
    wire        spi_sclk;
    wire        spi_mosi;
    wire        dut_miso;

`ifdef WINBOND_MODEL
    tri model_dio;
    tri model_do;
    tri model_wpn;
    tri model_holdn;
    reg delayed_model_do = 1'bz;
    reg [3:0] vendor_command_bit_number = 4'd0;
    wire model_cs_n;
    wire model_clk;

    // W1-only command fault injection. The counter advances after each model
    // sample edge, so bit 7 is selected for the first command clock and bit 0
    // for the eighth. Address, dummy, and payload clocks are left untouched.
    always @(negedge spi_cs_n or posedge spi_sclk) begin
        if (!spi_cs_n && spi_sclk) begin
            if (vendor_command_bit_number < 4'd8)
                vendor_command_bit_number <= vendor_command_bit_number + 4'd1;
        end else begin
            vendor_command_bit_number <= 4'd0;
        end
    end

    wire vendor_command_fault_bit =
        (vendor_command_bit_number < 4'd8) ?
        vendor_command_xor_mask[7 - vendor_command_bit_number] : 1'b0;
    wire vendor_model_mosi = spi_mosi ^ vendor_command_fault_bit;

    assign model_dio = use_timing_probe ? timing_probe_dio : vendor_model_mosi;
    // Keep the official model completely idle during the synthetic-model tests.
    // This also prevents startup/X transitions from polluting its one-shot
    // dynamic clock-period measurement before the vendor test begins.
    assign model_cs_n = use_timing_probe ? timing_probe_cs_n :
                        (use_vendor_model ? spi_cs_n : 1'b1);
    assign model_clk = use_timing_probe ? timing_probe_clk :
                       ((use_vendor_model && !spi_cs_n) ? spi_sclk : 1'b0);
    pullup (model_wpn);
    pullup (model_holdn);

    // A reduced memory depth keeps simulation startup small while retaining
    // pages 255 and 256 for F3's address-byte carry boundary check.
    W25Q64JV #(.NUM_PAGES(512)) u_flash (
        .CSn   (model_cs_n),
        .CLK   (model_clk),
        .DIO   (model_dio),
        .DO    (model_do),
        .WPn   (model_wpn),
        .HOLDn (model_holdn)
    );

    // F5-only transport delay.  The official model still generates the data
    // and retains its built-in tCLQV=6ns; this adds the board/path component
    // after DO so cocotb can cross the 1-UI alignment boundary at runtime.
    always @(model_do or vendor_extra_delay_ns)
        delayed_model_do <= #(vendor_extra_delay_ns) model_do;

    wire vendor_model_present = 1'b1;
    wire vendor_timing_error = u_flash.timing_error;
    wire [7:0] vendor_mem_page0_byte0 = u_flash.memory[0];
    wire [7:0] vendor_mem_page0_byte1 = u_flash.memory[1];
    wire [7:0] vendor_mem_page1_byte0 = u_flash.memory[256];
    wire [7:0] vendor_mem_page1_byte1 = u_flash.memory[257];
    wire vendor_invalid_opcode_seen = u_flash.vendor_invalid_opcode_seen;
    wire [7:0] vendor_invalid_opcode = u_flash.vendor_invalid_opcode;
    wire [31:0] vendor_invalid_opcode_count = u_flash.vendor_invalid_opcode_count;
    assign dut_miso = force_vendor_miso_low ? 1'b0 :
                      (use_vendor_model ? delayed_model_do : spi_miso);
`else
    wire vendor_model_present = 1'b0;
    wire vendor_timing_error = 1'b0;
    wire [7:0] vendor_mem_page0_byte0 = 8'd0;
    wire [7:0] vendor_mem_page0_byte1 = 8'd0;
    wire [7:0] vendor_mem_page1_byte0 = 8'd0;
    wire [7:0] vendor_mem_page1_byte1 = 8'd0;
    wire vendor_invalid_opcode_seen = 1'b0;
    wire [7:0] vendor_invalid_opcode = 8'd0;
    wire [31:0] vendor_invalid_opcode_count = 32'd0;
    assign dut_miso = spi_miso;
`endif

    flash_top_spi u_dut (
        .clk_core       (clk_core),
        .clk_sample     (clk_sample),
        .rstn           (rstn),
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
        .spi_cs_n       (spi_cs_n),
        .spi_sclk       (spi_sclk),
        .spi_mosi       (spi_mosi),
        .spi_miso       (dut_miso)
    );

    // F7-only fault hook. Blocking the synchronized completion path leaves
    // the production controller running until its R10 watchdog terminates it.
    always @(block_rx_done) begin
        if (block_rx_done)
            force u_dut.rx_done_s = 1'b0;
        else
            release u_dut.rx_done_s;
    end

    wire        test_rx_done_s = u_dut.rx_done_s;
    wire [31:0] test_wd_cnt = u_dut.u_ctrl.wd_cnt;
    wire        test_log_we = u_dut.log_we;
    wire [11:0] test_log_waddr = u_dut.log_waddr;
    wire [15:0] test_log_wdata = u_dut.log_wdata;
endmodule
