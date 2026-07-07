`timescale 1ns / 1ps
// flash_ctrl.v — clk_core 도메인 제어: R11 설정 검증 + TX 버스트 시퀀서 + R10 워치독
//
// 버스트 파형 (버스트 = 계약의 "읽기 1회", 루프백에서 CS 경계 = 갭):
//   [갭 0 × 32] [프리앰블 1 × 4] [PRBS 페이로드 × B] → 반복 N회 → 라인 0 유지
//   갭은 RX의 버스트 검출 기준(0-run 자격)이자 프레이밍 재정렬 경계.
//   오버헤드 36사이클/버스트 < R10의 (B+64)×2 여유 — T_max 안에 항상 완주.
//
// 규약 집행:
//  - R11: start 시점 검사 1≤N≤2,048 / 8≤B≤65,528 / B%8==0. 위반 → cfg_err 펄스만
//    (busy·done 발행 없음)
//  - meas_busy는 수락된 start의 "다음 사이클"에 상승 — core 명령 게이팅의 이중
//    수락 창을 닫는 flash 구현 요건 (log/young/6 노트)
//  - R10: T_max = 2×N×(B+64) clk_core 사이클. 초과 시 강제 종료 —
//    meas_done + meas_timeout 동시 펄스, run 철회로 RX도 해제
//  - 결과 유효성: meas_done은 rx_done(2FF 동기) 관측 후에만 — RX가 누적을 멈춘
//    지 최소 2 clk_sample + 2 clk_core 뒤라서 준정적 크로싱 성립

module flash_ctrl (
    input  wire        clk,           // = clk_core
    input  wire        rstn,

    // 계약 §2 (core 쪽)
    input  wire        meas_start,
    input  wire [15:0] cfg_n_reads,
    input  wire [15:0] cfg_burst_bits,
    output reg         meas_busy,
    output reg         meas_done,     // 1펄스
    output reg         meas_timeout,  // 1펄스, done과 동시 (§2 추인 대상 신호)
    output reg         cfg_err,       // 1펄스 (§2 추인 대상 신호)

    // RX 핸드셰이크
    output reg         run,           // 레벨 — RX 무장/해제
    input  wire        rx_done_s,     // 2FF 동기 완료

    // start 시점 래치값 (R6) — RX가 준정적으로 참조
    output reg  [15:0] n_lat,
    output reg  [15:0] b_lat,

    // 루프백 TX (JE1)
    output reg         pattern_out
);

    localparam GAP = 32, PRE = 4;
    localparam [2:0] S_IDLE = 3'd0, S_GAP = 3'd1, S_PRE = 3'd2,
                     S_PAY  = 3'd3, S_WAIT = 3'd4;

    reg [2:0]  state;
    reg [16:0] cyc;
    reg [11:0] tx_idx;
    reg [31:0] wd_cnt;

    wire cfg_ok = (cfg_n_reads   >= 16'd1) && (cfg_n_reads   <= 16'd2048) &&
                  (cfg_burst_bits >= 16'd8) && (cfg_burst_bits <= 16'd65528) &&
                  (cfg_burst_bits[2:0] == 3'b000);

    // T_max = 2·N·(B+64). B+64는 16비트를 넘칠 수 있어 17비트로 확장
    wire [16:0] b_plus64 = {1'b0, b_lat} + 17'd64;
    wire [31:0] t_max    = (n_lat * b_plus64) << 1;

    wire prbs_out;
    flash_prbs15 u_tx_prbs (
        .clk  (clk),
        .load (state == S_GAP),
        .seed ({1'b1, 2'b00, tx_idx}),
        .en   (state == S_PAY),
        .dout (prbs_out)
    );

    always @(posedge clk) begin
        if (!rstn) begin
            state        <= S_IDLE;
            meas_busy    <= 1'b0;
            meas_done    <= 1'b0;
            meas_timeout <= 1'b0;
            cfg_err      <= 1'b0;
            run          <= 1'b0;
            pattern_out  <= 1'b0;
            n_lat        <= 16'd0;
            b_lat        <= 16'd0;
            cyc          <= 17'd0;
            tx_idx       <= 12'd0;
            wd_cnt       <= 32'd0;
        end else begin
            meas_done    <= 1'b0;
            meas_timeout <= 1'b0;
            cfg_err      <= 1'b0;

            case (state)
                S_IDLE: begin
                    pattern_out <= 1'b0;
                    if (meas_start) begin
                        if (cfg_ok) begin
                            n_lat     <= cfg_n_reads;
                            b_lat     <= cfg_burst_bits;
                            tx_idx    <= 12'd0;
                            cyc       <= 17'd0;
                            wd_cnt    <= 32'd0;
                            run       <= 1'b1;
                            meas_busy <= 1'b1;   // start 다음 사이클 상승
                            state     <= S_GAP;
                        end else begin
                            cfg_err <= 1'b1;     // R11: 시끄러운 거부, busy/done 없음
                        end
                    end
                end

                S_GAP: begin
                    pattern_out <= 1'b0;
                    if (cyc == GAP-1) begin cyc <= 17'd0; state <= S_PRE; end
                    else                    cyc <= cyc + 17'd1;
                end

                S_PRE: begin
                    pattern_out <= 1'b1;
                    if (cyc == PRE-1) begin cyc <= 17'd0; state <= S_PAY; end
                    else                    cyc <= cyc + 17'd1;
                end

                S_PAY: begin
                    pattern_out <= prbs_out;
                    if (cyc == {1'b0, b_lat} - 17'd1) begin
                        cyc <= 17'd0;
                        if ({4'd0, tx_idx} == n_lat - 16'd1) state <= S_WAIT;
                        else begin tx_idx <= tx_idx + 12'd1; state <= S_GAP; end
                    end else
                        cyc <= cyc + 17'd1;
                end

                S_WAIT: begin
                    pattern_out <= 1'b0;
                    if (rx_done_s) begin
                        meas_done <= 1'b1;
                        meas_busy <= 1'b0;
                        run       <= 1'b0;
                        state     <= S_IDLE;
                    end
                end

                default: state <= S_IDLE;
            endcase

            // R10 워치독 — 상태 무관 강제 종료 (case보다 우선)
            if (state != S_IDLE) begin
                wd_cnt <= wd_cnt + 32'd1;
                if (wd_cnt >= t_max) begin
                    meas_done    <= 1'b1;
                    meas_timeout <= 1'b1;
                    meas_busy    <= 1'b0;
                    run          <= 1'b0;
                    pattern_out  <= 1'b0;
                    state        <= S_IDLE;
                end
            end
        end
    end

endmodule
