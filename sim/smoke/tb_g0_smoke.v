`timescale 1ns / 1ps
// tb_g0_smoke.v — core_top + flash_top 통합 스모크 (G0 전체 PL 데이터 경로 리허설)
//
// 계약 §3 호스트 스텝 시퀀스를 AXI로 그대로 실행:
//   PHASE_INC → PS_BUSY 폴 → MEAS_START → MEAS_DONE 폴 → ERR_*·e_i 회수 (R8)
// 추인 대상 신호 2개(meas_timeout·cfg_err)가 실제 flash 판정 → core sticky까지
// 이어지는 사슬을 처음으로 끝에서 끝까지 검증한다.
// MMCM은 unisim_stub(clk_core=clk_sample, 위상 0) — 위상별 동작은 tb_flash_smoke가,
// 실물 위상 시프트는 G0 브링업이 담당.
//
// 실행 (이 디렉터리에서):
//   iverilog -g2005 -o /tmp/tb_g0.vvp tb_g0_smoke.v unisim_stub.v \
//     ../../fpga/rtl/core/*.v ../../fpga/rtl/flash/*.v && vvp /tmp/tb_g0.vvp
// 성공 기준: 마지막 줄 "PASS: all checks passed"

module tb_g0_smoke;

    localparam [5:0] R_ID = 6'h00, R_CTRL = 6'h04, R_STATUS = 6'h08,
                     R_NREADS = 6'h0C, R_BURST = 6'h10, R_PHASE = 6'h14,
                     R_ERRB = 6'h18, R_ERRR = 6'h1C, R_LADDR = 6'h20, R_LDATA = 6'h24;
    localparam B_MBUSY = 0, B_DONE = 1, B_PSBUSY = 2, B_LOCK = 3, B_TMO = 4,
               B_CERR = 5, B_CMDERR = 6;

    reg clk125 = 0;
    always #4 clk125 = ~clk125;
    reg aresetn = 0;

    // AXI 마스터
    reg  [5:0]  awaddr = 0;  reg awvalid = 0;
    reg  [31:0] wdata = 0;   reg [3:0] wstrb = 0; reg wvalid = 0;
    reg  bready = 0;
    reg  [5:0]  araddr = 0;  reg arvalid = 0;
    reg  rready = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;

    // core ↔ flash (계약 §2 + 추인 대상 2신호)
    wire clk_core, clk_sample, mmcm_locked;
    wire meas_start, meas_busy, meas_done, meas_timeout, cfg_err;
    wire [31:0] err_bits, err_reads;
    wire [11:0] log_rd_addr;
    wire [15:0] log_rd_data, cfg_n_reads, cfg_burst_bits;

    core_top u_core (
        .clk125(clk125), .mmcm_rst(1'b0), .aresetn(aresetn),
        .clk_core(clk_core), .clk_sample(clk_sample), .mmcm_locked(mmcm_locked),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .meas_start(meas_start), .meas_busy(meas_busy), .meas_done(meas_done),
        .meas_timeout(meas_timeout), .cfg_err(cfg_err),
        .err_bits(err_bits), .err_reads(err_reads),
        .log_rd_addr(log_rd_addr), .log_rd_data(log_rd_data),
        .cfg_n_reads(cfg_n_reads), .cfg_burst_bits(cfg_burst_bits)
    );

    // 루프백 배선: 1ns 전파 지연 + 단선 스위치
    wire pattern_out;
    reg  pat_del = 0, brk = 0;
    always @(pattern_out) pat_del <= #1.0 pattern_out;
    wire pattern_in = brk ? 1'b0 : pat_del;

    flash_top u_flash (
        .clk_core(clk_core), .clk_sample(clk_sample), .rstn(aresetn),
        .meas_start(meas_start), .meas_busy(meas_busy), .meas_done(meas_done),
        .meas_timeout(meas_timeout), .cfg_err(cfg_err),
        .err_bits(err_bits), .err_reads(err_reads),
        .log_rd_addr(log_rd_addr), .log_rd_data(log_rd_data),
        .cfg_n_reads(cfg_n_reads), .cfg_burst_bits(cfg_burst_bits),
        .pattern_out(pattern_out), .pattern_in(pattern_in)
    );

    // ── AXI-Lite BFM (tb_core_smoke와 동일) ──
    task axi_write(input [5:0] addr, input [31:0] data);
    begin
        @(negedge clk_core);
        awaddr = addr; awvalid = 1; wdata = data; wstrb = 4'hF; wvalid = 1; bready = 1;
        @(posedge clk_core);
        while (!awready) @(posedge clk_core);
        @(negedge clk_core);
        awvalid = 0; wvalid = 0;
        @(posedge clk_core);
        while (!bvalid) @(posedge clk_core);
        @(negedge clk_core);
        bready = 0;
    end
    endtask

    reg [31:0] rd_val;
    task axi_read(input [5:0] addr);
    begin
        @(negedge clk_core);
        araddr = addr; arvalid = 1; rready = 1;
        @(posedge clk_core);
        while (!arready) @(posedge clk_core);
        @(negedge clk_core);
        arvalid = 0;
        @(posedge clk_core);
        while (!rvalid) @(posedge clk_core);
        rd_val = rdata;
        @(negedge clk_core);
        rready = 0;
    end
    endtask

    integer errors = 0;
    task expect(input [239:0] name, input [31:0] got, input [31:0] want);
    begin
        if (got !== want) begin
            errors = errors + 1;
            $display("FAIL %0s: got 0x%08h want 0x%08h (t=%0t)", name, got, want, $time);
        end
    end
    endtask

    task poll_bit_set(input integer bitpos);
    begin
        rd_val = 0;
        while (!rd_val[bitpos]) axi_read(R_STATUS);
    end
    endtask

    task poll_bit_clear(input integer bitpos);
    begin
        rd_val = 32'hFFFFFFFF;
        while (rd_val[bitpos]) axi_read(R_STATUS);
    end
    endtask

    // §3 호스트 스텝 1개: INC → 폴 → START → 폴 → 회수+R8 (에러 0 기대)
    reg [31:0] r8_sum, r8_cnt;
    integer k;
    task host_step(input [15:0] n);
    begin
        axi_write(R_CTRL, 32'h2);          // PHASE_INC
        poll_bit_clear(B_PSBUSY);
        axi_write(R_CTRL, 32'h1);          // MEAS_START
        poll_bit_set(B_DONE);
        expect("step STATUS clean", rd_val & 32'h7D, 32'h0000_0008);  // LOCKED만
        axi_read(R_ERRB);
        r8_sum = rd_val;
        axi_read(R_ERRR);
        r8_cnt = rd_val;
        expect("step ERR_BITS==0", r8_sum, 0);
        expect("step ERR_READS==0", r8_cnt, 0);
        r8_sum = 0; r8_cnt = 0;
        for (k = 0; k < n; k = k + 1) begin
            axi_write(R_LADDR, k);
            axi_read(R_LDATA);
            r8_sum = r8_sum + rd_val;
            if (rd_val != 0) r8_cnt = r8_cnt + 1;
        end
        expect("step R8 sum", r8_sum, 0);
        expect("step R8 cnt", r8_cnt, 0);
    end
    endtask

    initial begin
        #700;
        @(negedge clk_core); aresetn = 1;
        #100;

        $display("== 1. 브링업 스모크: ID ==");
        axi_read(R_ID); expect("ID", rd_val, 32'h4D42_0100);

        $display("== 2. 호스트 스텝 시퀀스 x3 (N=8, B=64) ==");
        axi_write(R_NREADS, 32'd8);
        axi_write(R_BURST, 32'd64);
        host_step(16'd8);
        host_step(16'd8);
        host_step(16'd8);
        axi_read(R_PHASE); expect("PHASE_POS==3", rd_val, 32'd3);

        $display("== 3. R11 사슬: flash 거부 → core CFG_ERR sticky ==");
        axi_write(R_NREADS, 32'd0);
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_CERR);
        expect("CFG_ERR: DONE cleared", (rd_val >> B_DONE) & 1, 0);
        expect("CFG_ERR: no busy", (rd_val >> B_MBUSY) & 1, 0);
        axi_write(R_NREADS, 32'd8);
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_DONE);
        expect("CFG_ERR cleared by valid START", (rd_val >> B_CERR) & 1, 0);

        $display("== 4. R10 사슬: 단선 → 워치독 → core TIMEOUT sticky ==");
        brk = 1;
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_TMO);                // T_max = 2*8*128 = 2,048 사이클
        expect("TIMEOUT: DONE also set", (rd_val >> B_DONE) & 1, 1);
        brk = 0; #500;
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_DONE);
        expect("TIMEOUT cleared by valid START", (rd_val >> B_TMO) & 1, 0);
        axi_read(R_ERRB); expect("recovery ERR_BITS==0", rd_val, 0);

        if (errors == 0) $display("\nPASS: all checks passed");
        else             $display("\nFAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #20_000_000;
        $display("FAIL: global timeout — testbench hung");
        $finish;
    end

endmodule
