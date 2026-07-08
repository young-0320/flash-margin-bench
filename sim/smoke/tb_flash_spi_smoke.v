`timescale 1ns / 1ps
// tb_flash_spi_smoke.v — flash_top_spi(실칩 SPI 프런트엔드) 스모크 테스트
//
// 검증 항목:
//  - W25Q64 행동 모델(0x0B, mode 0, 계약 19의 PRBS-15 방출 컨벤션) 상대로
//    위상 스윕(0.5~39.5ns)·tCLQV 스윕(1~38ns)에서 에러 0 — 합성 프리앰블 정렬
//    (PAY_LEAD)이 flash_rx 3후보 창에 전 구간 들어옴 (이 프런트엔드의 최대 난제)
//  - 프레임 규격: cmd==0x0B·addr 하위 8비트 0·프레임당 SCLK = 40+B (슬레이브 검사)
//  - 주소→시드 정합은 암묵 검증: 마스터가 페이지를 잘못 보내면 슬레이브가 다른
//    PRBS를 내보내 에러 0이 불가능
//  - 단일 비트 오염 주입 → e_i=1·err_bits=1·err_reads=1 정확 계수 + R8
//  - R11 거부 3종, R10 워치독(rx_done 강제 차단), 이후 정상 복구
//  - 무칩/단선 서명: MISO 풀다운 고정 0 → TIMEOUT 없이 완주 + 대량 에러
//    (에러 수 = 기대 PRBS의 1 개수. 루프백의 단선=TIMEOUT과 다름 — 합성
//    프리앰블이 항상 프레이밍을 성립시키기 때문. 현장 판독 주의, 로그 11)
//  - N=2,048 풀 버퍼 경계
//
// 실행 (이 디렉터리에서):
//   iverilog -g2005 -o /tmp/tb_flash_spi.vvp tb_flash_spi_smoke.v unisim_stub.v \
//     ../../fpga/rtl/flash/*.v && vvp /tmp/tb_flash_spi.vvp
// 성공 기준: 마지막 줄 "PASS: all checks passed"
//
// 한계(정직): tCLQV+배선 왕복이 1UI를 넘으면(75MHz 상향 시 가능) 정렬이 후보
// 창을 벗어난다 — 증상은 전 위상 BER 0.5. 그 경우 PAY_LEAD를 1 줄여 재보정.

module tb_flash_spi_smoke;

    reg clk_core = 0;
    always #20 clk_core = ~clk_core;   // 25MHz

    // clk_sample = clk_core의 위상 지연 복제 (MMCM 위상 시프트 모사)
    real phase_ns = 0.1;
    reg  clk_sample = 0;
    always @(clk_core) clk_sample <= #(phase_ns) clk_core;

    reg         rstn = 0;
    reg         meas_start = 0;
    reg  [15:0] cfg_n = 16'd4, cfg_b = 16'd64;
    reg  [11:0] log_addr = 0;
    wire        busy, done, tmo, cerr;
    wire [31:0] err_bits, err_reads;
    wire [15:0] log_data;
    wire        cs_n, sclk, mosi;

    // ---- MISO 배선: 슬레이브 tri-state + 풀다운 + 오염 주입 ----
    wire miso_line;
    pulldown (miso_line);
    reg  inj = 0;
    wire miso_pin = miso_line ^ inj;

    flash_top_spi dut (
        .clk_core(clk_core), .clk_sample(clk_sample), .rstn(rstn),
        .meas_start(meas_start), .meas_busy(busy), .meas_done(done),
        .meas_timeout(tmo), .cfg_err(cerr),
        .err_bits(err_bits), .err_reads(err_reads),
        .log_rd_addr(log_addr), .log_rd_data(log_data),
        .cfg_n_reads(cfg_n), .cfg_burst_bits(cfg_b),
        .spi_cs_n(cs_n), .spi_sclk(sclk), .spi_mosi(mosi), .spi_miso(miso_pin)
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

    // ---- W25Q64 행동 모델: 0x0B fast read (mode 0) ----
    // posedge에서 MOSI 수신, negedge에서 DO 전이(tCLQV 지연), 그 외 Hi-Z
    real        tclqv_ns = 8.0;
    reg         s_dead = 0;            // 무칩/단선 스위치
    reg  [5:0]  s_cnt;                 // 프로토콜 비트 카운터 (41 포화)
    reg  [31:0] s_sh;
    reg  [13:0] s_page;
    reg  [14:0] s_lfsr;
    reg         s_drive = 0, s_bit;
    reg         s_drive_d = 0, s_bit_d = 0;
    integer     s_edges;

    always @(negedge cs_n) begin s_cnt = 0; s_edges = 0; s_drive = 0; end
    always @(posedge cs_n) begin
        s_drive = 0;
        if (!s_dead && s_edges != 40 + cfg_b) begin
            errors = errors + 1;
            $display("FAIL slave: frame SCLK count %0d != %0d (t=%0t)",
                     s_edges, 40 + cfg_b, $time);
        end
    end

    always @(posedge sclk) if (!cs_n) begin
        s_sh    <= {s_sh[30:0], mosi};
        s_edges  = s_edges + 1;
        if (s_cnt < 6'd41) s_cnt <= s_cnt + 6'd1;
    end

    always @(negedge sclk) if (!cs_n) begin
        if (s_cnt == 6'd32 && !s_drive) begin
            if (s_sh[31:24] !== 8'h0B) begin errors = errors + 1;
                $display("FAIL slave: cmd %02x != 0B", s_sh[31:24]); end
            if (s_sh[7:0] !== 8'h00) begin errors = errors + 1;
                $display("FAIL slave: addr LSB %02x != 00", s_sh[7:0]); end
            s_page <= s_sh[21:8];
        end
        if (s_cnt == 6'd40 && !s_drive) begin
            if (!s_dead) begin
                // 방출 컨벤션 = flash_prbs15: dout = lfsr[14], 이후 시프트
                s_lfsr  <= {1'b1, s_page};
                s_bit   <= 1'b1;               // 첫 비트 = seed[14], 구조적 1
                s_drive <= 1'b1;
            end
        end else if (s_drive) begin
            s_bit  <= s_lfsr[13];              // 시프트 후 MSB = 현재 [13]
            s_lfsr <= {s_lfsr[13:0], s_lfsr[14] ^ s_lfsr[13]};
        end
    end

    always @(s_drive) s_drive_d <= #(tclqv_ns) s_drive;
    always @(s_bit)   s_bit_d   <= #(tclqv_ns) s_bit;
    assign miso_line = s_drive_d ? s_bit_d : 1'bz;

    // ---- 호스트 태스크 (tb_flash_smoke와 동일 골격) ----
    reg tmo_seen, cerr_seen, done_seen;
    always @(negedge clk_core) if (cerr) cerr_seen = 1;
    task start_meas(input [15:0] n, input [15:0] b);
    begin
        cfg_n = n; cfg_b = b;
        @(negedge clk_core); meas_start = 1;
        @(negedge clk_core); meas_start = 0;
    end
    endtask

    task wait_done(input integer guard_cycles);
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

    task clean_run(input [15:0] n, input [15:0] b);
    begin
        start_meas(n, b);
        wait_done(32'd2 * n * (b + 16'd64) + 32'd200);
        expect("no TIMEOUT", tmo_seen, 0);
        check_r8(n, b, 32'd0, 32'd0);
    end
    endtask

    real ph;
    integer di;
    real tclqvs [0:4];

    initial begin
        #200; @(negedge clk_core); rstn = 1; #200;

        $display("== 1. 기본 클린 런 ==");
        clean_run(16'd4, 16'd64);

        $display("== 2. 위상 스윕 0.5~39.5ns — 합성 프리앰블 정렬 (절벽 금지) ==");
        for (ph = 0.5; ph < 40.0; ph = ph + 3.0) begin
            phase_ns = ph;
            #100;
            clean_run(16'd2, 16'd64);
            if (errors != 0) $display("  (phase=%0.1fns에서 실패)", ph);
        end
        phase_ns = 0.1;

        $display("== 3. tCLQV 스윕 (칩 출력 지연, <1UI) ==");
        tclqvs[0] = 1.0; tclqvs[1] = 8.0; tclqvs[2] = 15.0;
        tclqvs[3] = 25.0; tclqvs[4] = 38.0;
        phase_ns = 10.0;
        for (di = 0; di < 5; di = di + 1) begin
            tclqv_ns = tclqvs[di];
            #200;
            clean_run(16'd2, 16'd64);
            if (errors != 0) $display("  (tCLQV=%0.1fns에서 실패)", tclqvs[di]);
        end
        tclqv_ns = 8.0; phase_ns = 0.1;

        $display("== 4. B=2048 (계약 기본 버스트 = 1페이지) ==");
        clean_run(16'd2, 16'd2048);

        $display("== 5. 단일 비트 오염 주입 → 정확 계수 ==");
        start_meas(16'd4, 16'd64);
        // 읽기 2 페이로드 중앙(cyc 60 ≈ 데이터 비트 19)에서 clk_sample 1주기 반전
        wait (dut.u_ctrl.state == 3'd2 && dut.u_ctrl.idx == 12'd2
              && dut.u_ctrl.cyc == 17'd60);
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

        $display("== 7. R10 워치독 — rx_done 강제 차단 ==");
        force dut.u_rx.rx_done = 1'b0;
        start_meas(16'd2, 16'd64);
        wait_done(32'd2 * 2 * (64 + 64) + 32'd200);      // T_max=512사이클 부근
        expect("R10 TIMEOUT with done", tmo_seen, 1);
        @(negedge clk_core);
        expect("R10 busy dropped", busy, 0);
        expect("R10 CS released", cs_n, 1);
        release dut.u_rx.rx_done;
        #500;
        clean_run(16'd2, 16'd64);                        // 강제 종료 후 정상 복구

        $display("== 8. 무칩/단선 서명 — TIMEOUT 없이 완주 + 대량 에러 ==");
        // 라인 0 고정이면 에러 수 = 기대 PRBS의 1 개수 — 시드 초반이 희소해
        // 짧은 B에선 작게 나온다. B=2048(수열 포화)로 서명을 견고하게 검사.
        s_dead = 1;
        start_meas(16'd2, 16'd2048);
        wait_done(32'd2 * 2 * (2048 + 64) + 32'd200);
        expect("dead: no TIMEOUT", tmo_seen, 0);
        if (err_bits < 32'd1024) begin errors = errors + 1;  // 2읽기×2048비트의 ≥25%
            $display("FAIL dead: err_bits=%0d too low (단선 서명 아님)", err_bits);
        end
        s_dead = 0; #500;
        clean_run(16'd2, 16'd64);

        $display("== 9. N=2048 풀 버퍼 (B=8) ==");
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
