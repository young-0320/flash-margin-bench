`timescale 1ns / 1ps
// tb_flash_smoke.v — flash_top(G0 루프백 프런트엔드) 스모크 테스트
//
// 검증 항목:
//  - 위상 스윕(0.5~39.5ns)·경로지연 스윕(0.2~63ns)에서 에러 0 — 정수 정렬 d가
//    바뀌어도 버스트별 프레이밍 재정렬이 절벽(BER 0.5)을 만들지 않음 (최대 난제)
//  - 단일 비트 오염 주입 → e_i=1·err_bits=1·err_reads=1 정확 계수
//  - R8 무결성(Σe_i=err_bits, count=err_reads, e_i≤B)을 TB가 직접 집행
//  - R11 거부 3종(N=0, B<8, B%8≠0): cfg_err 펄스, busy·done 없음
//  - R10 워치독(루프백 단선): T_max에 done+timeout 동시 펄스, 이후 정상 복구
//  - N=2,048 풀 버퍼 경계
//
// 실행 (이 디렉터리에서 — unisim_stub은 flash_top_spi의 ODDR 때문에 필요):
//   iverilog -g2005 -o /tmp/tb_flash.vvp tb_flash_smoke.v unisim_stub.v \
//     ../../fpga/rtl/flash/*.v && vvp /tmp/tb_flash.vvp
// 성공 기준: 마지막 줄 "PASS: all checks passed"

module tb_flash_smoke;

    reg clk_core = 0;
    always #20 clk_core = ~clk_core;   // 25MHz

    // clk_sample = clk_core의 위상 지연 복제 (MMCM 위상 시프트 모사)
    real phase_ns = 0.1;
    reg  clk_sample = 0;
    always @(clk_core) clk_sample <= #(phase_ns) clk_core;

    // 루프백 배선 (전파 지연 + 오염 주입 + 단선 스위치)
    real delay_ns = 1.0;
    wire pattern_out;
    reg  pat_del = 0;
    always @(pattern_out) pat_del <= #(delay_ns) pattern_out;
    reg  inj = 0, brk = 0;
    wire pattern_in = brk ? 1'b0 : (pat_del ^ inj);

    reg         rstn = 0;
    reg         meas_start = 0;
    reg  [15:0] cfg_n = 16'd4, cfg_b = 16'd64;
    reg  [11:0] log_addr = 0;
    wire        busy, done, tmo, cerr;
    wire [31:0] err_bits, err_reads;
    wire [15:0] log_data;

    flash_top dut (
        .clk_core(clk_core), .clk_sample(clk_sample), .rstn(rstn),
        .meas_start(meas_start), .meas_busy(busy), .meas_done(done),
        .meas_timeout(tmo), .cfg_err(cerr),
        .err_bits(err_bits), .err_reads(err_reads),
        .log_rd_addr(log_addr), .log_rd_data(log_data),
        .cfg_n_reads(cfg_n), .cfg_burst_bits(cfg_b),
        .pattern_out(pattern_out), .pattern_in(pattern_in)
    );

    integer errors = 0;
    task expect(input [239:0] name, input [31:0] got, input [31:0] want);
    begin
        if (got !== want) begin
            errors = errors + 1;
            $display("FAIL %0s: got %0d want %0d (t=%0t)", name, got, want, $time);
        end
    end
    endtask

    reg tmo_seen, cerr_seen, done_seen;
    // cfg_err은 1사이클 펄스 — 폴링 루프 시작 전에 지나갈 수 있어 상시 포집
    // (실물에서는 core의 CFG_ERR sticky가 이 역할)
    always @(negedge clk_core) if (cerr) cerr_seen = 1;
    task start_meas(input [15:0] n, input [15:0] b);
    begin
        cfg_n = n; cfg_b = b;
        @(negedge clk_core); meas_start = 1;
        @(negedge clk_core); meas_start = 0;
    end
    endtask

    task wait_done(input integer guard_cycles);   // done 펄스 포집 (timeout 동시 기록)
    integer g;
    begin
        done_seen = 0; tmo_seen = 0; g = 0;
        while (!done_seen && g < guard_cycles) begin
            @(negedge clk_core);
            if (done) begin done_seen = 1; tmo_seen = tmo; end
            g = g + 1;
        end
        if (!done_seen) begin errors = errors + 1;
            $display("FAIL: done not seen within %0d cycles (t=%0t)", guard_cycles, $time);
        end
    end
    endtask

    reg [15:0] ei;
    task read_ei(input [11:0] a);
    begin
        log_addr = a;
        @(negedge clk_core); @(negedge clk_core);
        ei = log_data;
    end
    endtask

    // R8 무결성 + 기대 총합 검사 (호스트 측 검사를 TB가 리허설)
    reg [31:0] r8_sum, r8_cnt;
    integer k;
    task check_r8(input [15:0] n, input [15:0] b,
                  input [31:0] want_bits, input [31:0] want_reads);
    begin
        r8_sum = 0; r8_cnt = 0;
        for (k = 0; k < n; k = k + 1) begin
            read_ei(k[11:0]);
            r8_sum = r8_sum + ei;
            if (ei != 0) r8_cnt = r8_cnt + 1;
            if (ei > b) begin errors = errors + 1;
                $display("FAIL R8-3: e[%0d]=%0d > B=%0d", k, ei, b); end
        end
        expect("R8-1 sum==ERR_BITS", r8_sum, err_bits);
        expect("R8-2 cnt==ERR_READS", r8_cnt, err_reads);
        expect("ERR_BITS", err_bits, want_bits);
        expect("ERR_READS", err_reads, want_reads);
    end
    endtask

    task clean_run(input [15:0] n, input [15:0] b);   // 에러 0 기대 측정 1회
    begin
        start_meas(n, b);
        wait_done(32'd2 * n * (b + 16'd64) + 32'd100);
        expect("no TIMEOUT", tmo_seen, 0);
        check_r8(n, b, 32'd0, 32'd0);
    end
    endtask

    real ph;
    integer di;
    real dlys [0:4];

    initial begin
        #200; @(negedge clk_core); rstn = 1; #200;

        $display("== 1. 기본 클린 런 ==");
        clean_run(16'd4, 16'd64);

        $display("== 2. 위상 스윕 0.5~39.5ns — 프레이밍 재정렬 (절벽 금지) ==");
        for (ph = 0.5; ph < 40.0; ph = ph + 3.0) begin
            phase_ns = ph;
            #100;
            clean_run(16'd2, 16'd64);
            if (errors != 0) $display("  (phase=%0.1fns에서 실패)", ph);
        end
        phase_ns = 0.1;

        $display("== 3. 경로 지연 스윕 (1UI 초과 포함) ==");
        dlys[0] = 0.2; dlys[1] = 15.0; dlys[2] = 39.9; dlys[3] = 41.0; dlys[4] = 63.0;
        phase_ns = 10.0;
        for (di = 0; di < 5; di = di + 1) begin
            delay_ns = dlys[di];
            #200;
            clean_run(16'd2, 16'd64);
            if (errors != 0) $display("  (delay=%0.1fns에서 실패)", dlys[di]);
        end
        delay_ns = 1.0; phase_ns = 0.1;

        $display("== 4. B=2048 (계약 기본 버스트) ==");
        clean_run(16'd2, 16'd2048);

        $display("== 5. 단일 비트 오염 주입 → 정확 계수 ==");
        start_meas(16'd4, 16'd64);
        // 버스트 2 페이로드 중앙에서 clk_sample 1주기만 라인 반전
        wait (dut.u_ctrl.state == 3'd3 && dut.u_ctrl.tx_idx == 12'd2
              && dut.u_ctrl.cyc == 17'd20);
        @(posedge clk_sample); inj <= 1;
        @(posedge clk_sample); inj <= 0;
        wait_done(32'd2000);
        expect("inj: no TIMEOUT", tmo_seen, 0);
        read_ei(12'd2);  expect("inj: e[2]==1", ei, 16'd1);
        read_ei(12'd1);  expect("inj: e[1]==0", ei, 16'd0);
        check_r8(16'd4, 16'd64, 32'd1, 32'd1);

        $display("== 6. R11 거부 3종 — cfg_err 펄스, busy/done 없음 ==");
        cerr_seen = 0;
        start_meas(16'd0, 16'd64);                       // N=0
        for (k = 0; k < 50; k = k + 1) begin
            @(negedge clk_core);
            if (busy || done) begin errors = errors + 1;
                $display("FAIL R11: busy/done on reject"); end
        end
        expect("R11 N=0 cfg_err", cerr_seen, 1);
        cerr_seen = 0; start_meas(16'd4, 16'd4);         // B<8
        for (k = 0; k < 50; k = k + 1) @(negedge clk_core);
        expect("R11 B=4 cfg_err", cerr_seen, 1);
        cerr_seen = 0; start_meas(16'd4, 16'd100);       // B%8!=0
        for (k = 0; k < 50; k = k + 1) @(negedge clk_core);
        expect("R11 B=100 cfg_err", cerr_seen, 1);
        clean_run(16'd4, 16'd64);                        // 거부 후 정상 복구

        $display("== 7. R10 워치독 — 루프백 단선 ==");
        brk = 1;
        start_meas(16'd2, 16'd64);
        wait_done(32'd2 * 2 * (64 + 64) + 32'd200);      // T_max=512사이클 부근
        expect("R10 TIMEOUT with done", tmo_seen, 1);
        @(negedge clk_core);
        expect("R10 busy dropped", busy, 0);
        brk = 0; #500;
        clean_run(16'd2, 16'd64);                        // 강제 종료 후 정상 복구

        $display("== 8. N=2048 풀 버퍼 (B=8) ==");
        clean_run(16'd2048, 16'd8);

        if (errors == 0) $display("\nPASS: all checks passed");
        else             $display("\nFAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #50_000_000;
        $display("FAIL: global timeout — testbench hung");
        $finish;
    end

endmodule
