`timescale 1ns / 1fs
// tb_edge_a2.v — 수정안 #4 인수 기준 A2: 에지 계수기 시뮬레이션 (flash_top_spi 경로)
//
// 실칩과 같은 경로(SPI 마스터 + flash_spi_shim 의 합성 프리앰블 + flash_rx)에 가짜 플래시를
// 물리고, 상승 · 하강 전이의 도착 시각(평균 · 지터)을 따로 넣는다. 샘플 클럭 위상을 쓸면서
// START 마다 읽기별 e_i 와 정렬별 여섯 값을 CSV 로 내보낸다. 이 TB 는 값을 내고 R8 만 검사한다 —
// 짝 고르기 · 방향 해석 · 주입값 회수는 run_a2.py 가 한다 (해석은 호스트 몫, R14).
//
// 위상: clk_sample 은 clk_core 를 ph_fs 만큼 늦춘 복제다 (MMCM 위상 시프트 모사, tb_flash_spi_smoke
//   와 같은 방식). 전이 쪽을 미는 대신 샘플 클럭을 미는 이유 — 실칩의 t0 는 pay 가 clk_sample 로
//   건너오는 시점이 정하므로, 샘플 클럭을 밀어야 정렬 번호의 이동이 재현된다.
// 가짜 플래시: 0x0B, SCLK 하강(= clk_core 상승 에지)에서 다음 비트를 런치한다. 값이 바뀌면
//   상승은 rise_fs + N(0, sig_r_fs), 하강은 fall_fs + N(0, sig_f_fs) 뒤에 선이 바뀐다.
//   쪽은 와이어 주소에서 얻고, 2,048비트 뒤에는 실칩처럼 다음 쪽의 첫 비트(1)를 낸다.
//   CS 가 오르면 선은 유휴 값으로 돌아간다 (idle_hi=0: 풀다운 0, 1: 1 로 남는다고 가정).
// 정답(truth): 전이마다 「런치 뒤 첫 셔터보다 먼저 왔는가」(지연 < 위상)와 「둘째 셔터보다 먼저
//   왔는가」(지연 < 위상 + 1UI)를 TB 가 알고 있다. 프레임마다 방향별 개수를 CSV 에 같이 싣는다 —
//   해석이 읽기 단위로 정확히 맞는지 대조하는 데 쓴다.
//   지연은 홀수 fs, 위상은 짝수 fs 라 선의 변화와 셔터가 같은 시각이 되는 일은 없다.
// lead: 1 이면 가짜 칩이 데이터를 SCLK 한 클럭 일찍 낸다. 실물의 t0 이동은 pay 가 동기화기에
//   닿는 경로 지연 δ 가 정하는데(위상 = δ 에서 한 칸), RTL 시뮬레이션은 δ = 0 이라 이동이 늘
//   위상 0 에 있다. DUT 가 보는 것은 (도착 − δ) 와 (위상 − δ) 뿐이므로, δ 를 넣는 대신 도착을
//   δ 만큼 당긴 칩을 넣으면 같은 조건이다 — 당긴 도착이 0 아래로 가면 lead = 1, 지연 + 1UI 로 준다.
//
// 실행: sim/a2/run_a2.py 가 컴파일 · 조건별 실행 · 분석을 한다. 단독 실행 예 —
//   iverilog -g2005 -o /tmp/a2.vvp tb_edge_a2.v ../smoke/unisim_stub.v ../../fpga/rtl/flash/*.v
//   vvp /tmp/a2.vvp +out=/tmp/a2.csv +nph=8 +n=1
// 성공 기준: 마지막 줄 "PASS: all checks passed" (R8 ①-⑥ · TIMEOUT 없음 · dead 면 e1_c == e_c)

module tb_edge_a2;

    // ---- 조건 (plusarg) ----
    integer rise_fs    = 8_000_000;   // 상승 전이 평균 도착 (런치 clk_core 에지 기준)
    integer fall_fs    = 8_500_000;   // 하강 전이 평균 도착
    integer sig_r_fs   = 8_000;       // 상승 지터 σ
    integer sig_f_fs   = 20_000;      // 하강 지터 σ
    integer ph0_fs     = 0;           // 첫 위상 (짝수 fs)
    integer step_fs    = 15_872;      // 위상 간격 (짝수 fs) — MMCM 한 칸 15.873ps 에 가장 가까운 짝수
    integer nph        = 2520;        // 위상 점 수
    integer n_reads    = 1;
    integer b_bits     = 2048;
    integer base       = 0;           // BASE_SECTOR
    integer seed       = 1;
    integer lead       = 0;
    integer idle_hi    = 0;
    integer dead       = 0;           // MISO 0 고정 (극성 검사)
    reg [1023:0] out_path;
    integer fd;

    reg clk_core = 0;
    always #20 clk_core = ~clk_core;   // 25MHz

    integer ph_fs = 0;
    real    phase_ns = 0.0;
    reg     clk_sample = 0;
    always @(clk_core) clk_sample <= #(phase_ns) clk_core;

    reg         rstn = 0;
    reg         meas_start = 0;
    reg  [15:0] cfg_n = 16'd1, cfg_b = 16'd2048;
    reg  [10:0] cfg_bs = 11'd0;
    reg  [11:0] log_addr = 0;
    wire        busy, done, tmo, cerr;
    wire [31:0] err_bits, err_reads;
    wire [15:0] log_data;
    wire [95:0] log_cand;
    wire        cs_n, sclk, mosi;
    reg         miso = 0;

    flash_top_spi dut (
        .clk_core(clk_core), .clk_sample(clk_sample), .rstn(rstn),
        .meas_start(meas_start), .meas_busy(busy), .meas_done(done),
        .meas_timeout(tmo), .cfg_err(cerr),
        .err_bits(err_bits), .err_reads(err_reads),
        .log_rd_addr(log_addr), .log_rd_data(log_data), .log_rd_cand(log_cand),
        .cfg_n_reads(cfg_n), .cfg_burst_bits(cfg_b), .cfg_base_sector(cfg_bs),
        .spi_cs_n(cs_n), .spi_sclk(sclk), .spi_mosi(mosi), .spi_miso(miso)
    );

    // ---- 가짜 플래시 ----
    integer     s_cnt;
    reg  [31:0] s_sh;
    reg  [15:0] s_page;
    reg  [14:0] s_lfsr;
    integer     s_nbit;
    reg         s_drive = 0;
    reg         line_val = 0;          // 마지막으로 런치한 값 (도착 전 포함)
    integer     fr = 0;                // START 안의 프레임 번호
    reg  [15:0] t_page [0:2047];
    integer     t_r_int   [0:2047];    // 쪽 안 상승 전이 수 (비트 1..B−1 로 들어가는 것)
    integer     t_f_int   [0:2047];
    integer     t_ra0     [0:2047];    // 그중 런치 뒤 첫 셔터보다 먼저 온 것 (지연 < 위상)
    integer     t_fa0     [0:2047];
    integer     t_ra1     [0:2047];    // 둘째 셔터보다 먼저 온 것 (지연 < 위상 + 1UI)
    integer     t_fa1     [0:2047];
    integer     t_head_dir[0:2047];    // 쪽 머리(유휴 → 비트 0): 0 없음 · 1 상승 · 2 하강
    integer     t_head_a0 [0:2047];
    integer     t_head_a1 [0:2047];
    integer     t_end_dir [0:2047];    // 쪽 끝(비트 B−1 → 다음 쪽 첫 비트)
    integer     t_end_a0  [0:2047];
    integer     t_end_a1  [0:2047];

    // 들어가는 비트 번호 m (0 = 쪽 머리, B = 쪽 끝 다음, 그 뒤는 비교 창 밖) 의 값 nb 를 런치
    task launch(input nb, input integer m);
        integer dly;
        reg     a0, a1;
    begin
        if (nb !== line_val) begin
            if (nb) dly = rise_fs + ((sig_r_fs != 0) ? $dist_normal(seed, 0, sig_r_fs) : 0);
            else    dly = fall_fs + ((sig_f_fs != 0) ? $dist_normal(seed, 0, sig_f_fs) : 0);
            dly = dly | 1;
            a0 = (dly < ph_fs);
            a1 = (dly < ph_fs + 40_000_000);
            miso <= #(dly * 1.0e-6) nb;
            line_val = nb;
            if (m == 0) begin
                t_head_dir[fr] = nb ? 1 : 2; t_head_a0[fr] = a0; t_head_a1[fr] = a1;
            end else if (m == b_bits) begin
                t_end_dir[fr] = nb ? 1 : 2;  t_end_a0[fr] = a0;  t_end_a1[fr] = a1;
            end else if (m < b_bits) begin
                if (nb) begin
                    t_r_int[fr] = t_r_int[fr] + 1;
                    if (a0) t_ra0[fr] = t_ra0[fr] + 1;
                    if (a1) t_ra1[fr] = t_ra1[fr] + 1;
                end else begin
                    t_f_int[fr] = t_f_int[fr] + 1;
                    if (a0) t_fa0[fr] = t_fa0[fr] + 1;
                    if (a1) t_fa1[fr] = t_fa1[fr] + 1;
                end
            end
        end
    end
    endtask

    always @(negedge cs_n) begin s_cnt = 0; s_drive = 0; end
    always @(posedge cs_n) begin
        if (s_drive) begin
            // 유휴 값으로 (창 밖 — 마지막 비교 샘플은 CS↑ 3사이클 전)
            miso <= #(5.000001) (idle_hi ? 1'b1 : 1'b0);
            line_val = idle_hi ? 1'b1 : 1'b0;
            fr = fr + 1;
        end
        s_drive = 0;
    end

    always @(posedge sclk) if (!cs_n) begin
        s_sh <= {s_sh[30:0], mosi};
        if (s_cnt < 41) s_cnt <= s_cnt + 1;
    end

    always @(negedge sclk) if (!cs_n && !dead) begin
        if (s_cnt == 32 && !s_drive) s_page = s_sh[23:8];
        if (s_cnt == 40 - lead && !s_drive) begin
            // 방출 컨벤션 = flash_prbs15: 첫 비트 = seed[14] = 1
            s_lfsr  = {1'b1, s_page[13:0]};
            s_nbit  = 0;
            s_drive = 1'b1;
            t_page[fr] = s_page;
            t_r_int[fr] = 0; t_f_int[fr] = 0;
            t_ra0[fr] = 0; t_fa0[fr] = 0; t_ra1[fr] = 0; t_fa1[fr] = 0;
            t_head_dir[fr] = 0; t_head_a0[fr] = 0; t_head_a1[fr] = 0;
            t_end_dir[fr] = 0;  t_end_a0[fr] = 0;  t_end_a1[fr] = 0;
            launch(s_lfsr[14], 0);
        end else if (s_drive) begin
            s_nbit = s_nbit + 1;
            if (s_nbit % 2048 == 0) begin
                s_page = s_page + 16'd1;           // 다음 쪽으로 이어 읽기
                s_lfsr = {1'b1, s_page[13:0]};
            end else
                s_lfsr = {s_lfsr[13:0], s_lfsr[14] ^ s_lfsr[13]};
            launch(s_lfsr[14], s_nbit);
        end
    end

    // ---- 호스트 ----
    integer errors = 0;
    integer n_starts = 0, n_rows = 0, n_tmo = 0, viol_r8 = 0, viol_dead = 0;

    reg done_seen, tmo_seen;
    task start_and_wait;
        integer g, guard;
    begin
        fr = 0;
        @(negedge clk_core); meas_start = 1;
        @(negedge clk_core); meas_start = 0;
        done_seen = 0; tmo_seen = 0; g = 0;
        guard = 2 * n_reads * (b_bits + 64) + 200;
        while (!done_seen && g < guard) begin
            @(negedge clk_core);
            if (done) begin done_seen = 1; tmo_seen = tmo; end
            if (cerr) begin errors = errors + 1; $display("FAIL: cfg_err"); g = guard; end
            g = g + 1;
        end
        if (!done_seen) begin errors = errors + 1;
            $display("FAIL: done not seen (ph_fs=%0d)", ph_fs); end
        if (tmo_seen) n_tmo = n_tmo + 1;
    end
    endtask

    integer ip, k, c, c2, dd, d1, d2, mn;
    reg [31:0] r8_sum, r8_cnt;
    reg [15:0] ei;
    reg [15:0] ec [0:2];
    reg [15:0] e1c [0:2];

    initial begin
        if ($value$plusargs("rise_fs=%d", rise_fs)) ;
        if ($value$plusargs("fall_fs=%d", fall_fs)) ;
        if ($value$plusargs("sig_r_fs=%d", sig_r_fs)) ;
        if ($value$plusargs("sig_f_fs=%d", sig_f_fs)) ;
        if ($value$plusargs("ph0_fs=%d", ph0_fs)) ;
        if ($value$plusargs("step_fs=%d", step_fs)) ;
        if ($value$plusargs("nph=%d", nph)) ;
        if ($value$plusargs("n=%d", n_reads)) ;
        if ($value$plusargs("b=%d", b_bits)) ;
        if ($value$plusargs("base=%d", base)) ;
        if ($value$plusargs("seed=%d", seed)) ;
        if ($value$plusargs("lead=%d", lead)) ;
        if ($value$plusargs("idle_hi=%d", idle_hi)) ;
        if ($value$plusargs("dead=%d", dead)) ;
        if (!$value$plusargs("out=%s", out_path)) begin
            $display("FAIL: +out=<csv> 가 필요하다"); $finish;
        end
        if ((ph0_fs % 2) != 0 || (step_fs % 2) != 0) begin
            $display("FAIL: 위상은 짝수 fs 여야 한다 (지연은 홀수 fs)"); $finish;
        end
        fd = $fopen(out_path, "w");
        $fwrite(fd, "ph_fs,start,read_idx,page,e_i,e_c0,e_c1,e_c2,e1_c0,e1_c1,e1_c2,err_bits,err_reads,timeout,");
        $fwrite(fd, "t_r_int,t_f_int,t_ra0,t_fa0,t_ra1,t_fa1,t_head_dir,t_head_a0,t_head_a1,t_end_dir,t_end_a0,t_end_a1\n");

        cfg_n = n_reads[15:0]; cfg_b = b_bits[15:0]; cfg_bs = base[10:0];
        if (idle_hi) begin miso = 1; line_val = 1; end

        #200; @(negedge clk_core); rstn = 1; #200;

        for (ip = 0; ip < nph; ip = ip + 1) begin
            ph_fs = (ph0_fs + ip * step_fs) % 40_000_000;
            phase_ns = ph_fs * 1.0e-6;
            repeat (6) @(negedge clk_core);       // 위상 변경 뒤 clk_sample 정착
            start_and_wait;
            n_starts = n_starts + 1;

            r8_sum = 0; r8_cnt = 0;
            for (k = 0; k < n_reads; k = k + 1) begin
                log_addr = k[11:0];
                @(negedge clk_core); @(negedge clk_core);
                ei = log_data;
                for (c = 0; c < 3; c = c + 1) begin
                    ec[c]  = log_cand[32*c +: 16];
                    e1c[c] = log_cand[32*c + 16 +: 16];
                end
                // R8 ①-⑥
                r8_sum = r8_sum + ei;
                if (ei != 0) r8_cnt = r8_cnt + 1;
                if (ei > b_bits) viol_r8 = viol_r8 + 1;                      // ③
                mn = ec[0];
                if (ec[1] < mn) mn = ec[1];
                if (ec[2] < mn) mn = ec[2];
                if (mn != ei) viol_r8 = viol_r8 + 1;                         // ④
                for (c = 0; c < 3; c = c + 1) begin
                    if (e1c[c] > ec[c]) viol_r8 = viol_r8 + 1;               // ⑤
                    if (dead && e1c[c] != ec[c]) viol_dead = viol_dead + 1;
                end
                for (c = 0; c < 3; c = c + 1)
                    for (c2 = c + 1; c2 < 3; c2 = c2 + 1) begin              // ⑥
                        d1 = ec[c];  d1 = d1 - 2 * e1c[c];
                        d2 = ec[c2]; d2 = d2 - 2 * e1c[c2];
                        dd = d1 - d2;
                        if (dd < 0) dd = -dd;
                        if (dd > c2 - c) viol_r8 = viol_r8 + 1;
                    end
                $fwrite(fd, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,",
                        ph_fs, ip, k, dead ? (base * 16 + k) : t_page[k], ei,
                        ec[0], ec[1], ec[2], e1c[0], e1c[1], e1c[2], err_bits, err_reads, tmo_seen);
                if (dead)
                    $fwrite(fd, "0,0,0,0,0,0,0,0,0,0,0,0\n");
                else
                    $fwrite(fd, "%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d,%0d\n",
                            t_r_int[k], t_f_int[k], t_ra0[k], t_fa0[k], t_ra1[k], t_fa1[k],
                            t_head_dir[k], t_head_a0[k], t_head_a1[k],
                            t_end_dir[k], t_end_a0[k], t_end_a1[k]);
                n_rows = n_rows + 1;
            end
            if (r8_sum != err_bits)  viol_r8 = viol_r8 + 1;                  // ①
            if (r8_cnt != err_reads) viol_r8 = viol_r8 + 1;                  // ②
        end
        $fclose(fd);

        $display("A2 TB: starts=%0d reads=%0d timeouts=%0d r8_violations=%0d dead_violations=%0d",
                 n_starts, n_rows, n_tmo, viol_r8, viol_dead);
        if (viol_r8 != 0 || viol_dead != 0 || n_tmo != 0) errors = errors + 1;
        if (errors == 0) $display("\nPASS: all checks passed");
        else             $display("\nFAIL: %0d errors", errors);
        $finish;
    end

endmodule
