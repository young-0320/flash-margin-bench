`timescale 1ns / 1ps
// core_axil_regs.v — AXI-Lite 레지스터 파일 (contract §3 레지스터 맵 v0, ID=0x4D42_0100)
//
// 단일 클럭 clk_core. 계약 규약을 여기서 집행한다:
//  - R4: busy(MEAS_BUSY | PS_BUSY) 중의 CTRL 쓰기는 통째로 무시
//  - R2: 위상 명령은 meas_busy=0에서만 — R4 게이트에 포함
//  - R1: start는 위상 이동 완료 후에만 — ps_busy 게이트에 포함
//  - CTRL에 명령 비트가 2개 이상이면 실행하지 않고 STATUS.CMD_ERR(bit6, sticky,
//    리셋으로만 클리어)를 켠다 — 호스트 시퀀스는 항상 한 번에 한 명령이므로
//    조합은 호스트 버그. R11과 같은 시끄러운 거부 (§3 수정 제안, 7/8 추인 안건).
//    R4의 busy 중 무시는 계약 문언 그대로 조용히 유지 — CMD_ERR 대상 아님
//  - R5: MEAS_DONE sticky, 다음 START 수락 시 자동 클리어
//  - R10/R11: TIMEOUT·CFG_ERR sticky, 다음 유효 START(= meas_busy 상승)에 클리어.
//    거부된 START(CFG_ERR 재발)는 busy가 안 뜨므로 이전 TIMEOUT을 지우지 않는다.
//
// meas_timeout·cfg_err 입력은 contract §2에 아직 없는 경계 신호 (7/8 추인 안건).

module core_axil_regs (
    input  wire        clk,            // = clk_core
    input  wire        rstn,

    // AXI4-Lite slave — clk_core 동기 (계약 §1: 제어 전 도메인 clk_core)
    input  wire [5:0]  s_axi_awaddr,
    input  wire        s_axi_awvalid,
    output wire        s_axi_awready,
    input  wire [31:0] s_axi_wdata,
    input  wire [3:0]  s_axi_wstrb,
    input  wire        s_axi_wvalid,
    output wire        s_axi_wready,
    output wire [1:0]  s_axi_bresp,
    output reg         s_axi_bvalid,
    input  wire        s_axi_bready,
    input  wire [5:0]  s_axi_araddr,
    input  wire        s_axi_arvalid,
    output wire        s_axi_arready,
    output reg  [31:0] s_axi_rdata,
    output wire [1:0]  s_axi_rresp,
    output reg         s_axi_rvalid,
    input  wire        s_axi_rready,

    // flash 경계 (contract §2, 전부 clk_core 동기)
    output reg         meas_start,     // 1펄스
    input  wire        meas_busy,
    input  wire        meas_done,      // 1펄스
    input  wire        meas_timeout,   // 1펄스, done과 동시 (R10 — §2 추가 제안)
    input  wire        cfg_err,        // 1펄스, 거부된 start (R11 — §2 추가 제안)
    input  wire [31:0] err_bits,
    input  wire [31:0] err_reads,
    output reg  [11:0] log_rd_addr,
    input  wire [15:0] log_rd_data,
    output reg  [15:0] cfg_n_reads,
    output reg  [15:0] cfg_burst_bits,

    // 위상 제어 (core 내부)
    output reg         phase_cmd,      // 1펄스 (게이팅 완료)
    output reg         phase_incdec,   // 1=INC
    input  wire        ps_busy,
    input  wire signed [31:0] phase_pos,
    input  wire        mmcm_locked     // 비동기 — 내부 2FF 동기화
);

    localparam [3:0] A_ID       = 4'h0,   // 0x00
                     A_CTRL     = 4'h1,   // 0x04
                     A_STATUS   = 4'h2,   // 0x08
                     A_N_READS  = 4'h3,   // 0x0C
                     A_BURST    = 4'h4,   // 0x10
                     A_PHASE    = 4'h5,   // 0x14
                     A_ERRBITS  = 4'h6,   // 0x18
                     A_ERRREADS = 4'h7,   // 0x1C
                     A_LOGADDR  = 4'h8,   // 0x20
                     A_LOGDATA  = 4'h9;   // 0x24

    // ── AXI 핸드셰이크: 단일 미결(outstanding 1), 응답은 항상 OKAY ──
    wire wr_fire = s_axi_awvalid && s_axi_wvalid && !s_axi_bvalid;
    assign s_axi_awready = wr_fire;
    assign s_axi_wready  = wr_fire;
    assign s_axi_bresp   = 2'b00;

    wire rd_fire = s_axi_arvalid && !s_axi_rvalid;
    assign s_axi_arready = rd_fire;
    assign s_axi_rresp   = 2'b00;

    // LOCKED 동기화
    reg [1:0] locked_sync;
    always @(posedge clk) begin
        if (!rstn) locked_sync <= 2'b00;
        else       locked_sync <= {locked_sync[0], mmcm_locked};
    end

    // ── CTRL 명령 디코드 + 게이팅 ──
    wire        ctrl_wr = wr_fire && (s_axi_awaddr[5:2] == A_CTRL) && s_axi_wstrb[0];
    wire [2:0]  cmd     = s_axi_wdata[2:0];   // {PHASE_DEC, PHASE_INC, MEAS_START}
    wire        cmd_onehot = (cmd == 3'b001) || (cmd == 3'b010) || (cmd == 3'b100);
    wire        cmd_malformed = ctrl_wr && (cmd != 3'b000) && !cmd_onehot;
    wire        cmd_accept = ctrl_wr && cmd_onehot && !meas_busy && !ps_busy;

    // ── sticky 플래그 ──
    reg done_sticky, timeout_sticky, cfg_err_sticky, cmd_err_sticky;
    reg meas_busy_q;
    wire busy_rise = meas_busy && !meas_busy_q;

    wire [31:0] status_word = {25'd0, cmd_err_sticky, cfg_err_sticky, timeout_sticky,
                               locked_sync[1], ps_busy, done_sticky, meas_busy};

    always @(posedge clk) begin
        if (!rstn) begin
            meas_start     <= 1'b0;
            phase_cmd      <= 1'b0;
            phase_incdec   <= 1'b0;
            cfg_n_reads    <= 16'd100;    // 리셋값 (계약 §3)
            cfg_burst_bits <= 16'd2048;
            log_rd_addr    <= 12'd0;
            done_sticky    <= 1'b0;
            timeout_sticky <= 1'b0;
            cfg_err_sticky <= 1'b0;
            cmd_err_sticky <= 1'b0;
            meas_busy_q    <= 1'b0;
            s_axi_bvalid   <= 1'b0;
            s_axi_rvalid   <= 1'b0;
            s_axi_rdata    <= 32'd0;
        end else begin
            meas_busy_q <= meas_busy;

            // 명령 펄스 (CTRL은 self-clear — 레지스터로 저장하지 않음)
            meas_start <= cmd_accept && cmd[0];
            phase_cmd  <= cmd_accept && (cmd[1] || cmd[2]);
            if (cmd_accept) phase_incdec <= cmd[1];

            // R5: done은 set 우선 없이도 충돌 불가 (start는 busy 중 수락 불가)
            if (meas_done)                    done_sticky <= 1'b1;
            else if (cmd_accept && cmd[0])    done_sticky <= 1'b0;

            if (busy_rise)         timeout_sticky <= 1'b0;
            else if (meas_timeout) timeout_sticky <= 1'b1;

            if (busy_rise)    cfg_err_sticky <= 1'b0;
            else if (cfg_err) cfg_err_sticky <= 1'b1;

            // 호스트 소프트웨어 버그 검출기 — 스윕 무효 판정용이라 리셋 전까지 유지
            if (cmd_malformed) cmd_err_sticky <= 1'b1;

            // RW 레지스터 쓰기
            if (wr_fire) begin
                case (s_axi_awaddr[5:2])
                    A_N_READS: begin
                        if (s_axi_wstrb[0]) cfg_n_reads[7:0]  <= s_axi_wdata[7:0];
                        if (s_axi_wstrb[1]) cfg_n_reads[15:8] <= s_axi_wdata[15:8];
                    end
                    A_BURST: begin
                        if (s_axi_wstrb[0]) cfg_burst_bits[7:0]  <= s_axi_wdata[7:0];
                        if (s_axi_wstrb[1]) cfg_burst_bits[15:8] <= s_axi_wdata[15:8];
                    end
                    A_LOGADDR: begin
                        if (s_axi_wstrb[0]) log_rd_addr[7:0]  <= s_axi_wdata[7:0];
                        if (s_axi_wstrb[1]) log_rd_addr[11:8] <= s_axi_wdata[11:8];
                    end
                    default: ;
                endcase
            end

            // 쓰기 응답
            if (wr_fire)                            s_axi_bvalid <= 1'b1;
            else if (s_axi_bvalid && s_axi_bready)  s_axi_bvalid <= 1'b0;

            // 읽기
            if (rd_fire) begin
                s_axi_rvalid <= 1'b1;
                case (s_axi_araddr[5:2])
                    A_ID:       s_axi_rdata <= 32'h4D42_0100;
                    A_CTRL:     s_axi_rdata <= 32'd0;
                    A_STATUS:   s_axi_rdata <= status_word;
                    A_N_READS:  s_axi_rdata <= {16'd0, cfg_n_reads};
                    A_BURST:    s_axi_rdata <= {16'd0, cfg_burst_bits};
                    A_PHASE:    s_axi_rdata <= phase_pos;
                    A_ERRBITS:  s_axi_rdata <= err_bits;
                    A_ERRREADS: s_axi_rdata <= err_reads;
                    A_LOGADDR:  s_axi_rdata <= {20'd0, log_rd_addr};
                    A_LOGDATA:  s_axi_rdata <= {16'd0, log_rd_data};
                    default:    s_axi_rdata <= 32'd0;
                endcase
            end else if (s_axi_rvalid && s_axi_rready) begin
                s_axi_rvalid <= 1'b0;
            end
        end
    end

endmodule
