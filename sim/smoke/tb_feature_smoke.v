`timescale 1ns / 1ps
// tb_feature_smoke.v — 수정안 #1(BASE_SECTOR) · #4(에지 계수기) 레지스터 경로 스모크
//
// FEATURE(0x38)가 알리는 두 기능을 AXI 레지스터 끝에서 끝까지 본다. 스택 둘:
//   g3 = core_top(HAS_BASE_SECTOR=1) + flash_top_spi + 내장 0x0B 슬레이브 (실칩 BD와 같은 결선)
//   g0 = core_top(기본) + flash_top (루프백 BD와 같은 결선)
//
// 검증 항목:
//  - ID 0x4D42_0100 그대로, FEATURE = 0x3(g3) · 0x1(g0), 0x3C는 0
//  - BASE_SECTOR(0x28) RW 11비트 · 리셋 0
//  - 수정안 #1 A2(시뮬 몫): 읽기 창 이동 — BASE_SECTOR 0 · 1 · 1,024 · 2,041 에서
//    ⑴ 와이어 주소(MOSI 디코드) = (BASE_SECTOR×16 + i)×256 이 모든 i 에서 성립
//    ⑵ 슬레이브가 와이어 주소의 쪽으로 PRBS 를 내보낼 때 오류 0 (시드가 주소를 따라옴)
//    start 래치(R12): 측정 도중 BASE_SECTOR 를 바꿔도 진행 중 측정은 그대로
//  - 수정안 #1 A3: 범위 거부 — 2,042/N=112 · 2,047/N=17 → STATUS.CFG_ERR, busy 상승 없음,
//    CS 프레임 없음, 이전 TIMEOUT sticky 유지. 경계 2,041/N=112 · 2,047/N=16 은 수락되고
//    마지막 읽기가 쪽 32,767 (주소 0x7FFF00) — 랩어라운드 없음
//  - 수정안 #4: LOG_C0-C2 로 읽은 여섯 값이 R8 ④⑤⑥ 을 전 읽기에서 만족, 단일 비트
//    오염(정답 1 자리 · 정답 0 자리)이 깨끗한 정렬의 (e_c, e1_c) = (1,1) · (1,0) 으로 나옴,
//    MISO 0 고정이면 모든 c 에서 e1_c == e_c (극성), N=1 START
//  - 루프백(g0): BASE_SECTOR 를 무시한다(범위 밖 값을 써도 거부 없음 · 오류 0), 여섯 값은 나온다
//
// 실행 (이 디렉터리에서):
//   iverilog -g2005 -o /tmp/tb_feature.vvp tb_feature_smoke.v unisim_stub.v \
//     ../../fpga/rtl/core/*.v ../../fpga/rtl/flash/*.v && vvp /tmp/tb_feature.vvp
// 성공 기준: 마지막 줄 "PASS: all checks passed"
// 위상별 여섯 값의 해석(수정안 #4 A2)은 sim/a2/ 가 따로 돌린다.

module tb_feature_smoke;

    localparam [5:0] R_ID = 6'h00, R_CTRL = 6'h04, R_STATUS = 6'h08,
                     R_NREADS = 6'h0C, R_BURST = 6'h10,
                     R_ERRB = 6'h18, R_ERRR = 6'h1C, R_LADDR = 6'h20, R_LDATA = 6'h24,
                     R_BSEC = 6'h28, R_LC0 = 6'h2C, R_LC1 = 6'h30, R_LC2 = 6'h34,
                     R_FEAT = 6'h38, R_SPARE = 6'h3C;
    localparam B_MBUSY = 0, B_DONE = 1, B_TMO = 4, B_CERR = 5;

    reg clk125 = 0;
    always #4 clk125 = ~clk125;
    reg aresetn = 0;

    // AXI 마스터 — sel 로 스택을 고른다 (0 = g3 실칩, 1 = g0 루프백)
    reg         sel = 0;
    reg  [5:0]  awaddr = 0;  reg awvalid = 0;
    reg  [31:0] wdata = 0;   reg [3:0] wstrb = 0; reg wvalid = 0;
    reg  bready = 0;
    reg  [5:0]  araddr = 0;  reg arvalid = 0;
    reg  rready = 0;
    wire awready3, wready3, bvalid3, arready3, rvalid3;
    wire awready0, wready0, bvalid0, arready0, rvalid0;
    wire [31:0] rdata3, rdata0;
    wire awready = sel ? awready0 : awready3;
    wire bvalid  = sel ? bvalid0  : bvalid3;
    wire arready = sel ? arready0 : arready3;
    wire rvalid  = sel ? rvalid0  : rvalid3;
    wire [31:0] rdata = sel ? rdata0 : rdata3;

    // ── 스택 g3: core_top + flash_top_spi ──
    wire clk_core, clk_sample3;
    wire st3, busy3, done3, tmo3, cerr3;
    wire [31:0] eb3, er3;
    wire [11:0] la3;
    wire [15:0] ld3, n3, b3;
    wire [95:0] lc3;
    wire [10:0] bs3;
    wire cs_n, sclk, mosi;

    core_top #(.HAS_BASE_SECTOR(1)) u_core3 (
        .clk125(clk125), .mmcm_rst(1'b0), .aresetn(aresetn),
        .clk_core(clk_core), .clk_sample(clk_sample3), .mmcm_locked(),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid & ~sel), .s_axi_awready(awready3),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid & ~sel), .s_axi_wready(wready3),
        .s_axi_bresp(), .s_axi_bvalid(bvalid3), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid & ~sel), .s_axi_arready(arready3),
        .s_axi_rdata(rdata3), .s_axi_rresp(), .s_axi_rvalid(rvalid3), .s_axi_rready(rready),
        .meas_start(st3), .meas_busy(busy3), .meas_done(done3),
        .meas_timeout(tmo3), .cfg_err(cerr3),
        .err_bits(eb3), .err_reads(er3),
        .log_rd_addr(la3), .log_rd_data(ld3), .log_rd_cand(lc3),
        .cfg_n_reads(n3), .cfg_burst_bits(b3), .cfg_base_sector(bs3)
    );

    wire miso_line;
    pulldown (miso_line);

    flash_top_spi u_fl3 (
        .clk_core(clk_core), .clk_sample(clk_sample3), .rstn(aresetn),
        .meas_start(st3), .meas_busy(busy3), .meas_done(done3),
        .meas_timeout(tmo3), .cfg_err(cerr3),
        .err_bits(eb3), .err_reads(er3),
        .log_rd_addr(la3), .log_rd_data(ld3), .log_rd_cand(lc3),
        .cfg_n_reads(n3), .cfg_burst_bits(b3), .cfg_base_sector(bs3),
        .spi_cs_n(cs_n), .spi_sclk(sclk), .spi_mosi(mosi), .spi_miso(miso_line)
    );

    // ── 스택 g0: core_top(기본 파라미터) + flash_top ──
    wire clk_core0, clk_sample0;
    wire st0, busy0, done0, tmo0, cerr0;
    wire [31:0] eb0, er0;
    wire [11:0] la0;
    wire [15:0] ld0, n0, b0;
    wire [95:0] lc0;
    wire [10:0] bs0;

    core_top u_core0 (
        .clk125(clk125), .mmcm_rst(1'b0), .aresetn(aresetn),
        .clk_core(clk_core0), .clk_sample(clk_sample0), .mmcm_locked(),
        .s_axi_awaddr(awaddr), .s_axi_awvalid(awvalid & sel), .s_axi_awready(awready0),
        .s_axi_wdata(wdata), .s_axi_wstrb(wstrb), .s_axi_wvalid(wvalid & sel), .s_axi_wready(wready0),
        .s_axi_bresp(), .s_axi_bvalid(bvalid0), .s_axi_bready(bready),
        .s_axi_araddr(araddr), .s_axi_arvalid(arvalid & sel), .s_axi_arready(arready0),
        .s_axi_rdata(rdata0), .s_axi_rresp(), .s_axi_rvalid(rvalid0), .s_axi_rready(rready),
        .meas_start(st0), .meas_busy(busy0), .meas_done(done0),
        .meas_timeout(tmo0), .cfg_err(cerr0),
        .err_bits(eb0), .err_reads(er0),
        .log_rd_addr(la0), .log_rd_data(ld0), .log_rd_cand(lc0),
        .cfg_n_reads(n0), .cfg_burst_bits(b0), .cfg_base_sector(bs0)
    );

    wire pattern_out;
    reg  pat_del = 0;
    always @(pattern_out) pat_del <= #1.0 pattern_out;

    flash_top u_fl0 (
        .clk_core(clk_core0), .clk_sample(clk_sample0), .rstn(aresetn),
        .meas_start(st0), .meas_busy(busy0), .meas_done(done0),
        .meas_timeout(tmo0), .cfg_err(cerr0),
        .err_bits(eb0), .err_reads(er0),
        .log_rd_addr(la0), .log_rd_data(ld0), .log_rd_cand(lc0),
        .cfg_n_reads(n0), .cfg_burst_bits(b0), .cfg_base_sector(bs0),
        .pattern_out(pattern_out), .pattern_in(pat_del)
    );

    integer errors = 0;
    task expect(input [239:0] name, input [31:0] got, input [31:0] want);
    begin
        if (got !== want) begin
            errors = errors + 1;
            $display("FAIL %0s: got 0x%08h want 0x%08h (t=%0t)", name, got, want, $time);
        end
    end
    endtask

    // ── 내장 슬레이브: 0x0B fast read (mode 0), 쪽은 와이어 주소에서만 얻는다 ──
    // tb_flash_spi_smoke 의 슬레이브와 같은 방출 컨벤션. 다른 점: 주소 24비트를 프레임마다
    // 기록(fr_addr)하고, 쪽 16비트 전부를 디코드해 시드는 그 하위 14비트(계약 §5)로 잡는다.
    real        tclqv_ns = 8.0;
    reg         s_dead = 0;             // MISO 0 고정 (극성 검사)
    integer     inj_frame = -1;         // 이 프레임의
    integer     inj_bit   = -1;         // 이 데이터 비트를 반전
    reg  [5:0]  s_cnt;
    reg  [31:0] s_sh;
    reg  [15:0] s_page;
    reg  [14:0] s_lfsr;
    integer     s_nbit;
    reg         s_drive = 0, s_bit = 0;
    reg         s_drive_d = 0, s_bit_d = 0;
    integer     fr_cnt = 0;             // START 이후 CS 프레임 수 (TB 가 START 전에 0 으로)
    reg  [23:0] fr_addr [0:2047];
    integer     busy_rises = 0;
    always @(posedge busy3) busy_rises = busy_rises + 1;

    always @(negedge cs_n) begin s_cnt = 0; s_drive = 0; end
    always @(posedge cs_n) begin s_drive = 0; fr_cnt = fr_cnt + 1; end

    always @(posedge sclk) if (!cs_n) begin
        s_sh <= {s_sh[30:0], mosi};
        if (s_cnt < 6'd41) s_cnt <= s_cnt + 6'd1;
    end

    always @(negedge sclk) if (!cs_n) begin
        if (s_cnt == 6'd32 && !s_drive) begin
            if (s_sh[31:24] !== 8'h0B) begin errors = errors + 1;
                $display("FAIL slave: cmd %02x != 0B", s_sh[31:24]); end
            fr_addr[fr_cnt] = s_sh[23:0];
            s_page = s_sh[23:8];
        end
        if (s_cnt == 6'd40 && !s_drive) begin
            if (!s_dead) begin
                s_lfsr  = {1'b1, s_page[13:0]};
                s_nbit  = 0;
                s_bit   = s_lfsr[14] ^ (fr_cnt == inj_frame && inj_bit == 0);
                s_drive = 1'b1;
            end
        end else if (s_drive) begin
            s_lfsr = {s_lfsr[13:0], s_lfsr[14] ^ s_lfsr[13]};
            s_nbit = s_nbit + 1;
            s_bit  = s_lfsr[14] ^ (fr_cnt == inj_frame && s_nbit == inj_bit);
        end
    end

    always @(s_drive) s_drive_d <= #(tclqv_ns) s_drive;
    always @(s_bit)   s_bit_d   <= #(tclqv_ns) s_bit;
    assign miso_line = s_drive_d ? s_bit_d : 1'bz;

    // TB 쪽 PRBS (flash_prbs15 와 독립 구현) — 쪽 idx 의 j 번째 비트
    function prbs_bit(input [13:0] pidx, input integer j);
        reg [14:0] l;
        integer t;
    begin
        l = {1'b1, pidx};
        for (t = 0; t < j; t = t + 1) l = {l[13:0], l[14] ^ l[13]};
        prbs_bit = l[14];
    end
    endfunction

    // ── AXI-Lite BFM (tb_g0_smoke 와 동일) ──
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

    task poll_bit_set(input integer bitpos);
    begin
        rd_val = 0;
        while (!rd_val[bitpos]) axi_read(R_STATUS);
    end
    endtask

    task start_meas(input [10:0] bs, input [15:0] n, input [15:0] b);
    begin
        axi_write(R_BSEC, {21'd0, bs});
        axi_write(R_NREADS, {16'd0, n});
        axi_write(R_BURST, {16'd0, b});
        fr_cnt = 0; busy_rises = 0;
        axi_write(R_CTRL, 32'h1);
    end
    endtask

    // 읽기 i 의 e_i 와 여섯 값을 레지스터로 회수
    reg [15:0] ei;
    reg [15:0] ec [0:2];
    reg [15:0] e1c [0:2];
    task read6(input integer i);
    begin
        axi_write(R_LADDR, i);
        axi_read(R_LDATA); ei = rd_val[15:0];
        axi_read(R_LC0);   ec[0] = rd_val[15:0]; e1c[0] = rd_val[31:16];
        axi_read(R_LC1);   ec[1] = rd_val[15:0]; e1c[1] = rd_val[31:16];
        axi_read(R_LC2);   ec[2] = rd_val[15:0]; e1c[2] = rd_val[31:16];
    end
    endtask

    // R8 ①-⑥ 을 전 읽기에서. 정렬 c 의 (정답 0 오류) − (정답 1 오류) = e_c − 2·e1_c
    reg [31:0] r8_sum, r8_cnt;
    integer k, c, c2, dd, d1, d2, mn;
    task check_r8(input integer n, input integer b);
    begin
        r8_sum = 0; r8_cnt = 0;
        for (k = 0; k < n; k = k + 1) begin
            read6(k);
            r8_sum = r8_sum + ei;
            if (ei != 0) r8_cnt = r8_cnt + 1;
            if (ei > b) begin errors = errors + 1;
                $display("FAIL R8-3: e[%0d]=%0d > B=%0d", k, ei, b); end
            mn = ec[0];
            if (ec[1] < mn) mn = ec[1];
            if (ec[2] < mn) mn = ec[2];
            if (mn != ei) begin errors = errors + 1;
                $display("FAIL R8-4: read %0d min(%0d,%0d,%0d) != e_i %0d", k, ec[0], ec[1], ec[2], ei); end
            for (c = 0; c < 3; c = c + 1)
                if (e1c[c] > ec[c]) begin errors = errors + 1;
                    $display("FAIL R8-5: read %0d c%0d e1=%0d > e=%0d", k, c, e1c[c], ec[c]); end
            for (c = 0; c < 3; c = c + 1)
                for (c2 = c + 1; c2 < 3; c2 = c2 + 1) begin
                    d1 = ec[c]; d1 = d1 - 2 * e1c[c];
                    d2 = ec[c2]; d2 = d2 - 2 * e1c[c2];
                    dd = d1 - d2;
                    if (dd < 0) dd = -dd;
                    if (dd > c2 - c) begin errors = errors + 1;
                        $display("FAIL R8-6: read %0d (c%0d,c%0d) |%0d - %0d| > %0d", k, c, c2, d1, d2, c2 - c); end
                end
        end
        axi_read(R_ERRB); expect("R8-1 sum==ERR_BITS", r8_sum, rd_val);
        axi_read(R_ERRR); expect("R8-2 cnt==ERR_READS", r8_cnt, rd_val);
    end
    endtask

    // 깨끗한 창 하나: 수락 · 완주 · 와이어 주소 = (bs×16+i)×256 · 오류 0 · R8
    integer want_addr;
    task window_run(input [10:0] bs, input [15:0] n, input [15:0] b);
    begin
        start_meas(bs, n, b);
        poll_bit_set(B_DONE);
        expect("win: STATUS (DONE+LOCKED only)", rd_val & 32'h7F, 32'h0000_000A);
        expect("win: frames == N", fr_cnt, n);
        for (k = 0; k < n; k = k + 1) begin
            want_addr = (bs * 16 + k) * 256;
            if (fr_addr[k] !== want_addr[23:0]) begin errors = errors + 1;
                $display("FAIL win bs=%0d read %0d: wire addr 0x%06h want 0x%06h",
                         bs, k, fr_addr[k], want_addr[23:0]); end
        end
        check_r8(n, b);
        expect("win: ERR_BITS==0", r8_sum, 0);
    end
    endtask

    // 거부: CFG_ERR 만, busy 상승 없음, CS 프레임 없음
    task reject_run(input [10:0] bs, input [15:0] n, input [15:0] b);
    begin
        start_meas(bs, n, b);
        poll_bit_set(B_CERR);
        repeat (300) @(negedge clk_core);
        axi_read(R_STATUS);
        expect("reject: CFG_ERR sticky", (rd_val >> B_CERR) & 1, 1);
        expect("reject: no busy", (rd_val >> B_MBUSY) & 1, 0);
        expect("reject: no done", (rd_val >> B_DONE) & 1, 0);
        expect("reject: busy never rose", busy_rises, 0);
        expect("reject: no CS frame", fr_cnt, 0);
        expect("reject: CS idle", cs_n, 1);
    end
    endtask

    integer cstar, i, w0, w01, w2, w21;
    reg     xb;

    initial begin
        #700;
        @(negedge clk_core); aresetn = 1;
        #100;

        $display("== 1. ID 그대로 · FEATURE · BASE_SECTOR 리셋값 · RW 폭 ==");
        sel = 0;
        axi_read(R_ID);    expect("g3 ID", rd_val, 32'h4D42_0100);
        axi_read(R_FEAT);  expect("g3 FEATURE", rd_val, 32'h0000_0003);
        axi_read(R_BSEC);  expect("g3 BASE_SECTOR reset", rd_val, 0);
        axi_read(R_SPARE); expect("g3 0x3C reads 0", rd_val, 0);
        axi_write(R_BSEC, 32'hFFFF_FFFF);
        axi_read(R_BSEC);  expect("BASE_SECTOR is 11 bits", rd_val, 32'h0000_07FF);
        axi_write(R_FEAT, 32'hFFFF_FFFF);
        axi_read(R_FEAT);  expect("FEATURE is RO", rd_val, 32'h0000_0003);
        axi_write(R_BSEC, 0);
        sel = 1;
        axi_read(R_ID);    expect("g0 ID", rd_val, 32'h4D42_0100);
        axi_read(R_FEAT);  expect("g0 FEATURE", rd_val, 32'h0000_0001);
        sel = 0;

        $display("== 2. 읽기 창 이동 — 와이어 주소와 시드가 같은 page(i) (수정안 #1 A2 시뮬 몫) ==");
        window_run(11'd0,    16'd112, 16'd64);   // 하위 호환
        window_run(11'd1,    16'd112, 16'd64);   // ×16 스케일링
        window_run(11'd1024, 16'd112, 16'd64);   // 주소 비트 [14] — 시드는 별칭, 주소로 본다
        window_run(11'd2041, 16'd112, 16'd64);   // 상한 경계
        expect("2041/112 last page == 32767", fr_addr[111], 24'h7FFF00);
        window_run(11'd513,  16'd2,   16'd2048); // 시드 하위 14비트 전부가 실리는 쪽 · 1페이지 버스트

        $display("== 3. start 래치 (R12) — 측정 도중 BASE_SECTOR 변경은 무영향 ==");
        start_meas(11'd1, 16'd8, 16'd64);
        wait (fr_cnt == 3);
        axi_write(R_BSEC, 32'd77);
        poll_bit_set(B_DONE);
        for (i = 0; i < 8; i = i + 1) begin
            want_addr = (16 + i) * 256;
            expect("latch: wire addr", fr_addr[i], want_addr);
        end
        axi_read(R_ERRB); expect("latch: ERR_BITS==0", rd_val, 0);
        axi_read(R_BSEC); expect("latch: register holds new value", rd_val, 32'd77);
        axi_write(R_NREADS, 32'd2); axi_write(R_BURST, 32'd64);
        fr_cnt = 0;
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_DONE);
        expect("latch: next START uses new value", fr_addr[0], 24'd77 * 24'd16 * 24'd256);

        $display("== 4. 범위 거부 (수정안 #1 A3) — 이전 sticky 유지, 경계는 수락 ==");
        // 먼저 TIMEOUT sticky 를 만든다 (rx_done 차단 → 워치독)
        force u_fl3.u_rx.rx_done = 1'b0;
        start_meas(11'd0, 16'd2, 16'd64);
        poll_bit_set(B_TMO);
        release u_fl3.u_rx.rx_done;
        #500;
        reject_run(11'd2042, 16'd112, 16'd64);            // 2,042×16+111 = 32,783
        expect("reject keeps previous TIMEOUT", (rd_val >> B_TMO) & 1, 1);
        reject_run(11'd2047, 16'd17, 16'd64);             // 2,047×16+16 = 32,768
        reject_run(11'd2047, 16'd2048, 16'd8);            // 덧셈이 16비트를 넘는 조합
        window_run(11'd2047, 16'd16, 16'd64);             // 경계 정확히 — 수락, sticky 클리어
        expect("2047/16 last page == 32767", fr_addr[15], 24'h7FFF00);
        window_run(11'd0, 16'd2048, 16'd8);               // N 상한은 그대로 (BASE_SECTOR 0)

        $display("== 5. 에지 계수기 — 단일 비트 오염이 정답 0/1 로 갈려 나온다 ==");
        // 깨끗한 정렬 c* 를 오염 없는 읽기에서 찾는다 (e_c == 0 인 c)
        window_run(11'd3, 16'd4, 16'd64);
        read6(1);
        cstar = -1;
        for (c = 0; c < 3; c = c + 1) if (ec[c] == 0) cstar = c;
        if (cstar < 0) begin errors = errors + 1; $display("FAIL: no clean alignment"); cstar = 0; end
        // R14 정렬 번호: 같은 샘플을 정렬 c−1 은 한 비트 뒤, c+1 은 한 비트 앞의 정답과 맞댄다.
        // 이 스택(위상 0 · tCLQV 8ns)은 c* = 1 이라, 읽기 1(쪽 49)의 정렬 0 · 2 를 TB 의 PRBS 로 센다
        //   정렬 0: 샘플 = 비트 n, 정답 = 비트 n+1 (n = 0..B−2, 첫 샘플은 합성 프리앰블 1 = 비트 0)
        //   정렬 2: 샘플 = 비트 n, 정답 = 비트 n−1 (n = 1..B, 비트 B 는 슬레이브가 이어 낸 값)
        expect("R14: clean alignment is c1 here", cstar, 1);
        w0 = 0; w01 = 0; w2 = 0; w21 = 0;
        for (i = 0; i < 63; i = i + 1)
            if (prbs_bit(14'd49, i) != prbs_bit(14'd49, i + 1)) begin
                w0 = w0 + 1;
                if (prbs_bit(14'd49, i + 1)) w01 = w01 + 1;
            end
        for (i = 1; i <= 64; i = i + 1)
            if (prbs_bit(14'd49, i) != prbs_bit(14'd49, i - 1)) begin
                w2 = w2 + 1;
                if (prbs_bit(14'd49, i - 1)) w21 = w21 + 1;
            end
        expect("R14: e_c0 = next-bit mismatches",  ec[0],  w0);
        expect("R14: e1_c0",                       e1c[0], w01);
        expect("R14: e_c2 = prev-bit mismatches",  ec[2],  w2);
        expect("R14: e1_c2",                       e1c[2], w21);
        // 읽기 2(쪽 50) 의 비트 10(정답 1) · 11(정답 0) 을 차례로 반전 — 정답 비트는 TB 의 PRBS 로 계산
        for (i = 10; i < 12; i = i + 1) begin
            xb = prbs_bit(14'd50, i);
            inj_frame = 2; inj_bit = i;
            start_meas(11'd3, 16'd4, 16'd64);
            poll_bit_set(B_DONE);
            inj_frame = -1; inj_bit = -1;
            check_r8(4, 64);
            expect("inj: ERR_BITS==1", r8_sum, 1);
            read6(2);
            expect("inj: e_i==1", ei, 1);
            expect("inj: e_c*==1", ec[cstar], 1);
            expect("inj: e1_c* == expected bit", e1c[cstar], xb);
            read6(1);
            expect("inj: neighbour clean", ec[cstar], 0);
        end
        if (prbs_bit(14'd50, 10) == prbs_bit(14'd50, 11)) begin errors = errors + 1;
            $display("FAIL: injection bits do not cover both expected values"); end

        $display("== 6. 극성 — MISO 0 고정이면 모든 c 에서 e1_c == e_c ==");
        s_dead = 1;
        start_meas(11'd0, 16'd2, 16'd2048);
        poll_bit_set(B_DONE);
        expect("dead: no TIMEOUT", (rd_val >> B_TMO) & 1, 0);
        check_r8(2, 2048);
        for (i = 0; i < 2; i = i + 1) begin
            read6(i);
            for (c = 0; c < 3; c = c + 1) begin
                expect("dead: e1_c == e_c", e1c[c], ec[c]);
                if (ec[c] < 16'd512) begin errors = errors + 1;
                    $display("FAIL dead: read %0d e_c%0d=%0d too low", i, c, ec[c]); end
            end
        end
        s_dead = 0; #500;

        $display("== 7. N=1 START (훑기) ==");
        window_run(11'd9, 16'd1, 16'd2048);

        $display("== 8. 루프백 — BASE_SECTOR 무시, 여섯 값은 나온다 ==");
        sel = 1;
        axi_write(R_BSEC, 32'd2047);                      // 실칩이면 N=8 에서 거부되는 값
        axi_write(R_NREADS, 32'd8);
        axi_write(R_BURST, 32'd64);
        axi_write(R_CTRL, 32'h1);
        poll_bit_set(B_DONE);
        expect("g0: STATUS (DONE+LOCKED only)", rd_val & 32'h7F, 32'h0000_000A);
        check_r8(8, 64);
        expect("g0: ERR_BITS==0", r8_sum, 0);
        read6(7);
        if (ec[0] != 0 && ec[1] != 0 && ec[2] != 0) begin errors = errors + 1;
            $display("FAIL g0: no clean alignment in LOG_Cn"); end
        if (ec[0] == 0 && ec[1] == 0 && ec[2] == 0) begin errors = errors + 1;
            $display("FAIL g0: LOG_Cn all zero — candidates not recorded"); end
        sel = 0;

        if (errors == 0) $display("\nPASS: all checks passed");
        else             $display("\nFAIL: %0d errors", errors);
        $finish;
    end

    initial begin
        #400_000_000;
        $display("FAIL: global timeout — testbench hung");
        $finish;
    end

endmodule
