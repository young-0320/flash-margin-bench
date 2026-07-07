`timescale 1ns / 1ps
// tb_core_smoke.v — core_top 스모크 테스트 (iverilog + unisim_stub)
// 검증 항목: ID·리셋값 / 위상 INC·DEC·PHASE_POS / busy 중 CTRL 무시(R4) /
// 다중 비트 CTRL 거부+CMD_ERR / START-BUSY-DONE·sticky(R5) / ERR·LOG 창 /
// CFG_ERR·TIMEOUT sticky와 유효 START 클리어(R10·R11)
//
// 실행 (이 디렉터리에서):
//   iverilog -g2005 -o /tmp/tb_core_smoke.vvp tb_core_smoke.v unisim_stub.v \
//     ../../fpga/rtl/core/*.v && vvp /tmp/tb_core_smoke.vvp
// 마지막 줄 "PASS: all checks passed" 가 성공 기준. cocotb 회귀(sim/tb/)가 서면
// 이 TB는 그쪽으로 흡수·폐기 가능 — 그전까지 core 수정 시 최소 회귀로 사용.

module tb_core_smoke;

    // 레지스터 오프셋
    localparam [5:0] R_ID = 6'h00, R_CTRL = 6'h04, R_STATUS = 6'h08,
                     R_NREADS = 6'h0C, R_BURST = 6'h10, R_PHASE = 6'h14,
                     R_ERRB = 6'h18, R_ERRR = 6'h1C, R_LADDR = 6'h20, R_LDATA = 6'h24;
    // STATUS 비트
    localparam B_MBUSY = 0, B_DONE = 1, B_PSBUSY = 2, B_LOCK = 3, B_TMO = 4, B_CERR = 5,
               B_CMDERR = 6;

    reg clk125 = 0;
    always #4 clk125 = ~clk125;

    reg aresetn = 0;

    // AXI 마스터 신호
    reg  [5:0]  awaddr = 0;  reg awvalid = 0;
    reg  [31:0] wdata = 0;   reg [3:0] wstrb = 0; reg wvalid = 0;
    reg  bready = 0;
    reg  [5:0]  araddr = 0;  reg arvalid = 0;
    reg  rready = 0;
    wire awready, wready, bvalid, arready, rvalid;
    wire [1:0] bresp, rresp;
    wire [31:0] rdata;

    // flash 경계
    wire        meas_start;
    reg         fl_busy = 0, fl_done = 0, fl_timeout = 0, fl_cfg_err = 0;
    reg  [31:0] fl_err_bits = 32'd42, fl_err_reads = 32'd7;
    wire [11:0] log_rd_addr;
    reg  [15:0] fl_log_data = 0;
    wire [15:0] cfg_n_reads, cfg_burst_bits;
    wire clk_core, clk_sample, mmcm_locked;

    core_top dut (
        .clk125(clk125), .mmcm_rst(1'b0), .aresetn(aresetn),
        .clk_core(clk_core), .clk_sample(clk_sample), .mmcm_locked(mmcm_locked),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid), .s_axi_awready(awready),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid), .s_axi_wready(wready),
        .s_axi_bresp(bresp), .s_axi_bvalid(bvalid), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid), .s_axi_arready(arready),
        .s_axi_rdata(rdata), .s_axi_rresp(rresp), .s_axi_rvalid(rvalid), .s_axi_rready(rready),
        .meas_start(meas_start), .meas_busy(fl_busy), .meas_done(fl_done),
        .meas_timeout(fl_timeout), .cfg_err(fl_cfg_err),
        .err_bits(fl_err_bits), .err_reads(fl_err_reads),
        .log_rd_addr(log_rd_addr), .log_rd_data(fl_log_data),
        .cfg_n_reads(cfg_n_reads), .cfg_burst_bits(cfg_burst_bits)
    );

    // ── flash 목: 계약 §2 타이밍 준수 ──
    // mode 0=정상, 1=R11 거부(cfg_err), 2=워치독(done+timeout)
    integer fl_mode = 0;
    integer fl_cnt = 0;
    reg fl_running = 0;
    always @(posedge clk_core) begin
        fl_done <= 0; fl_timeout <= 0; fl_cfg_err <= 0;
        fl_log_data <= {4'd0, log_rd_addr};   // 주소 제시 다음 사이클 유효
        if (meas_start && !fl_running) begin
            if (fl_mode == 1) fl_cfg_err <= 1;         // busy·done 발행 없음 (R11)
            else begin fl_running <= 1; fl_busy <= 1; fl_cnt <= 0; end
        end else if (fl_running) begin
            fl_cnt <= fl_cnt + 1;
            if (fl_cnt == 40) begin
                fl_busy <= 0; fl_running <= 0; fl_done <= 1;
                if (fl_mode == 2) fl_timeout <= 1;
            end
        end
    end

    // ── AXI-Lite BFM ──
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
    task expect(input [127:0] name, input [31:0] got, input [31:0] want);
    begin
        if (got !== want) begin
            errors = errors + 1;
            $display("FAIL %0s: got 0x%08h want 0x%08h (t=%0t)", name, got, want, $time);
        end else
            $display("  ok %0s = 0x%08h", name, got);
    end
    endtask

    task poll_status_bit_clear(input integer bitpos);   // 해당 비트 0까지 폴링
    begin
        rd_val = 32'hFFFFFFFF;
        while (rd_val[bitpos]) axi_read(R_STATUS);
    end
    endtask

    task poll_status_bit_set(input integer bitpos);
    begin
        rd_val = 0;
        while (!rd_val[bitpos]) axi_read(R_STATUS);
    end
    endtask

    initial begin
        // 리셋: MMCM lock(스텁 500ns) 후 해제
        #700;
        @(negedge clk_core); aresetn = 1;
        #100;

        $display("== 1. ID / 리셋값 ==");
        axi_read(R_ID);      expect("ID", rd_val, 32'h4D42_0100);
        axi_read(R_NREADS);  expect("N_READS reset", rd_val, 32'd100);
        axi_read(R_BURST);   expect("BURST_BITS reset", rd_val, 32'd2048);
        axi_read(R_STATUS);  expect("STATUS idle+locked", rd_val, 32'h0000_0008);
        axi_read(R_PHASE);   expect("PHASE_POS reset", rd_val, 32'd0);

        $display("== 2. 위상 INC/DEC + PS_BUSY ==");
        axi_write(R_CTRL, 32'h2);            // PHASE_INC
        axi_read(R_STATUS);
        if (!rd_val[B_PSBUSY]) begin errors = errors + 1; $display("FAIL PS_BUSY not set"); end
        poll_status_bit_clear(B_PSBUSY);
        axi_read(R_PHASE);   expect("PHASE_POS after INC", rd_val, 32'd1);

        // busy 중 명령 무시 (R4)
        axi_write(R_CTRL, 32'h2);            // INC 수락
        axi_write(R_CTRL, 32'h2);            // ps_busy 중 → 무시돼야 함
        poll_status_bit_clear(B_PSBUSY);
        axi_read(R_PHASE);   expect("R4: busy-ignored INC", rd_val, 32'd2);
        axi_read(R_STATUS);  expect("R4 ignore is silent", (rd_val >> B_CMDERR) & 1, 0);

        axi_write(R_CTRL, 32'h4); poll_status_bit_clear(B_PSBUSY);
        axi_write(R_CTRL, 32'h4); poll_status_bit_clear(B_PSBUSY);
        axi_write(R_CTRL, 32'h4); poll_status_bit_clear(B_PSBUSY);
        axi_read(R_PHASE);   expect("PHASE_POS signed -1", rd_val, 32'hFFFF_FFFF);

        // 다중 비트 명령: 실행 거부 + CMD_ERR (시끄러운 거부)
        axi_write(R_CTRL, 32'h6);            // INC+DEC 동시
        axi_read(R_STATUS);  expect("multi-bit CTRL rejected", rd_val[B_PSBUSY], 0);
        expect("CMD_ERR set", (rd_val >> B_CMDERR) & 1, 1);
        axi_read(R_PHASE);   expect("PHASE_POS unchanged", rd_val, 32'hFFFF_FFFF);
        axi_write(R_CTRL, 32'h0);            // 0 쓰기 = no-op, 에러 아님
        axi_write(R_CTRL, 32'h2); poll_status_bit_clear(B_PSBUSY);
        axi_write(R_CTRL, 32'h4); poll_status_bit_clear(B_PSBUSY);  // 위상 원복
        axi_read(R_STATUS);  expect("CMD_ERR sticky until reset", (rd_val >> B_CMDERR) & 1, 1);

        $display("== 3. 측정 START/BUSY/DONE + 결과 ==");
        axi_write(R_NREADS, 32'd8);
        axi_read(R_NREADS);  expect("N_READS write", rd_val, 32'd8);
        expect("cfg_n_reads wire", cfg_n_reads, 16'd8);
        axi_write(R_CTRL, 32'h1);            // MEAS_START
        axi_read(R_STATUS);
        if (!rd_val[B_MBUSY]) begin errors = errors + 1; $display("FAIL MEAS_BUSY not set"); end
        axi_write(R_CTRL, 32'h2);            // meas_busy 중 위상 명령 → 무시 (R2/R4)
        poll_status_bit_set(B_DONE);
        expect("STATUS after done", rd_val & 32'h3F, 32'h0000_000A);  // DONE+LOCKED
        axi_read(R_PHASE);   expect("R2: phase cmd during meas ignored", rd_val, 32'hFFFF_FFFF);
        axi_read(R_ERRB);    expect("ERR_BITS", rd_val, 32'd42);
        axi_read(R_ERRR);    expect("ERR_READS", rd_val, 32'd7);

        $display("== 4. LOG 창 ==");
        axi_write(R_LADDR, 32'd5);
        axi_read(R_LDATA);   expect("LOG_DATA[5]", rd_val, 32'd5);
        axi_write(R_LADDR, 32'd1723);
        axi_read(R_LADDR);   expect("LOG_ADDR readback", rd_val, 32'd1723);
        axi_read(R_LDATA);   expect("LOG_DATA[1723]", rd_val, 32'd1723);
        axi_read(R_LDATA);   expect("read no side-effect", rd_val, 32'd1723);

        $display("== 5. R5: 다음 START가 DONE 클리어 ==");
        axi_write(R_CTRL, 32'h1);
        axi_read(R_STATUS);
        if (rd_val[B_DONE]) begin errors = errors + 1; $display("FAIL DONE not cleared by START"); end
        poll_status_bit_set(B_DONE);

        $display("== 6. R11: CFG_ERR — 거부·sticky·유효 START 클리어 ==");
        fl_mode = 1;
        axi_write(R_CTRL, 32'h1);            // 거부됨: busy/done 없음
        #200;
        axi_read(R_STATUS);
        expect("CFG_ERR sticky", (rd_val >> B_CERR) & 1, 1);
        expect("no busy on reject", (rd_val >> B_MBUSY) & 1, 0);
        expect("DONE cleared, no new done", (rd_val >> B_DONE) & 1, 0);
        fl_mode = 0;
        axi_write(R_CTRL, 32'h1);            // 유효 START
        poll_status_bit_set(B_DONE);
        expect("CFG_ERR cleared by valid START", (rd_val >> B_CERR) & 1, 0);

        $display("== 7. R10: TIMEOUT — sticky·유효 START 클리어 ==");
        fl_mode = 2;
        axi_write(R_CTRL, 32'h1);
        poll_status_bit_set(B_DONE);
        expect("TIMEOUT sticky", (rd_val >> B_TMO) & 1, 1);
        fl_mode = 0;
        axi_write(R_CTRL, 32'h1);
        poll_status_bit_set(B_DONE);
        expect("TIMEOUT cleared by valid START", (rd_val >> B_TMO) & 1, 0);

        if (errors == 0) $display("\nPASS: all checks passed");
        else             $display("\nFAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #500000;
        $display("FAIL: timeout — testbench hung");
        $finish;
    end

endmodule
