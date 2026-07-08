`timescale 1ns / 1ps
// flash_spi_ctrl.v — clk_core 도메인 제어 (실칩 SPI 프런트엔드): R11 검증 +
// 0x0B fast read 시퀀서 + R10 워치독. flash_ctrl(루프백)의 실칩 대응물.
//
// 읽기 1회 = CS 프레임 1개 (로그 10 결정 ③: 명령은 0x0B 하나뿐):
//   [CS↓ 셋업 2] [SCLK 40클럭: cmd 8 + addr 24 + dummy 8] [SCLK B클럭: 데이터]
//   [홀드 3, CS 유지] [CS↑ 갭 4] → 반복 N회 → S_WAIT
//   읽기 i → 페이지 i (addr = i×256) — RX의 PRBS 시드 {1, idx}와 자동 정합,
//   flash_prep이 쓰는 페이지와 1:1 (로그 10 가정 2).
//   오버헤드 49사이클/읽기 < R10의 (B+64)×2 여유 — T_max 안에 항상 완주.
//
// SCLK는 이 모듈이 만들지 않는다 — sclk_en을 top의 ODDR(D1=0, D2=sclk_en)에
// 공급해 clk_core를 무분주 포워딩(R9). ODDR이 rising에서 en을 잡아 그 사이클
// 후반부에 high를 내므로 SCLK 상승 = 사이클 중앙: MOSI(에지 런치)에 반주기
// 셋업/홀드가 자동 확보되는 mode 0.
//
// 타이밍 유도(사이클 = clk_core, E0 = S_XFER 진입 에지):
//   sclk_en은 en 세트 에지 +1 사이클의 SCLK 펄스를 만들므로, 프로토콜 비트 j의
//   펄스는 [E0+j+1.5, E0+j+2). mosi는 XFER 분기 첫 실행(E0+1)부터 시프트 —
//   비트 j 값이 [E0+j+1, E0+j+2)에 놓여 중앙 샘플과 정렬.
//   데이터 비트 0은 dummy 마지막 falling(E0+41)+tCLQV 이후 라인에 실린다.
// pay(데이터 창 예고)는 cyc==40-PAY_LEAD에 상승 — 2FF 동기(+2) + shim 프리앰블
//   4비트 뒤 페이로드 정렬이 flash_rx의 3후보 창 {t0+3, t0+4, t0+5}에 들어오도록
//   PAY_LEAD=5로 유도(경로지연 0~1UI 가정, 상세 산식은 tb_flash_spi_smoke.v).
//   클럭 상향으로 왕복 지연이 1UI를 넘으면 PAY_LEAD를 1 줄여 재보정.

module flash_spi_ctrl #(
    parameter PAY_LEAD = 5
) (
    input  wire        clk,           // = clk_core
    input  wire        rstn,

    // 계약 §2 (core 쪽)
    input  wire        meas_start,
    input  wire [15:0] cfg_n_reads,
    input  wire [15:0] cfg_burst_bits,
    output reg         meas_busy,
    output reg         meas_done,     // 1펄스
    output reg         meas_timeout,  // 1펄스, done과 동시 (R10)
    output reg         cfg_err,       // 1펄스 (R11)

    // RX 핸드셰이크 (flash_ctrl과 동일)
    output reg         run,
    input  wire        rx_done_s,

    // start 시점 래치값 (R6)
    output reg  [15:0] n_lat,
    output reg  [15:0] b_lat,

    // SPI 라인 (SCLK는 top의 ODDR이 sclk_en으로 생성)
    output reg         spi_cs_n,
    output reg         spi_mosi,
    output reg         sclk_en,
    output reg         pay            // 데이터 창 예고 → shim (clk_sample로 2FF)
);

    localparam CS_SETUP = 2, HOLD = 3, GAP = 4;
    localparam [2:0] S_IDLE = 3'd0, S_CS = 3'd1, S_XFER = 3'd2,
                     S_HOLD = 3'd3, S_GAP = 3'd4, S_WAIT = 3'd5;

    reg [2:0]  state;
    reg [16:0] cyc;
    reg [11:0] idx;       // 읽기 인덱스 = 페이지 번호 = RX PRBS 시드 인덱스
    reg [31:0] sh;        // {cmd 8, addr 24} 시프트 레지스터
    reg [31:0] wd_cnt;

    wire cfg_ok = (cfg_n_reads   >= 16'd1) && (cfg_n_reads   <= 16'd2048) &&
                  (cfg_burst_bits >= 16'd8) && (cfg_burst_bits <= 16'd65528) &&
                  (cfg_burst_bits[2:0] == 3'b000);

    wire [16:0] b_plus64 = {1'b0, b_lat} + 17'd64;
    wire [31:0] t_max    = (n_lat * b_plus64) << 1;

    wire [16:0] bits_total = {1'b0, b_lat} + 17'd40;   // 프레임당 SCLK 수

    always @(posedge clk) begin
        if (!rstn) begin
            state        <= S_IDLE;
            meas_busy    <= 1'b0;
            meas_done    <= 1'b0;
            meas_timeout <= 1'b0;
            cfg_err      <= 1'b0;
            run          <= 1'b0;
            spi_cs_n     <= 1'b1;
            spi_mosi     <= 1'b0;
            sclk_en      <= 1'b0;
            pay          <= 1'b0;
            n_lat        <= 16'd0;
            b_lat        <= 16'd0;
            cyc          <= 17'd0;
            idx          <= 12'd0;
            sh           <= 32'd0;
            wd_cnt       <= 32'd0;
        end else begin
            meas_done    <= 1'b0;
            meas_timeout <= 1'b0;
            cfg_err      <= 1'b0;

            case (state)
                S_IDLE: begin
                    spi_cs_n <= 1'b1;
                    if (meas_start) begin
                        if (cfg_ok) begin
                            n_lat     <= cfg_n_reads;
                            b_lat     <= cfg_burst_bits;
                            idx       <= 12'd0;
                            cyc       <= 17'd0;
                            wd_cnt    <= 32'd0;
                            run       <= 1'b1;
                            meas_busy <= 1'b1;   // start 다음 사이클 상승
                            spi_cs_n  <= 1'b0;
                            state     <= S_CS;
                        end else begin
                            cfg_err <= 1'b1;     // R11: 시끄러운 거부
                        end
                    end
                end

                S_CS: begin   // CS↓ 셋업 + 프레임 시프트 레지스터 장전
                    sh <= {8'h0B, 4'd0, idx, 8'h00};   // addr = idx × 256
                    if (cyc == CS_SETUP-1) begin
                        cyc     <= 17'd0;
                        sclk_en <= 1'b1;
                        state   <= S_XFER;
                    end else
                        cyc <= cyc + 17'd1;
                end

                S_XFER: begin   // cmd+addr+dummy 40 + 데이터 B (첫 실행 = cyc 0→1)
                    cyc      <= cyc + 17'd1;
                    spi_mosi <= sh[31];
                    sh       <= {sh[30:0], 1'b0};
                    if (cyc == 17'd40 - PAY_LEAD)
                        pay <= 1'b1;
                    if (cyc == bits_total - 17'd1)
                        sclk_en <= 1'b0;         // 마지막 펄스까지 내고 정지
                    if (cyc == bits_total) begin
                        cyc   <= 17'd0;
                        state <= S_HOLD;
                    end
                end

                S_HOLD: begin   // CS 유지 — 마지막 데이터 비트 샘플 여유
                    if (cyc == HOLD-1) begin
                        cyc      <= 17'd0;
                        spi_cs_n <= 1'b1;
                        pay      <= 1'b0;
                        state    <= S_GAP;
                    end else
                        cyc <= cyc + 17'd1;
                end

                S_GAP: begin    // tSHSL 충족 + RX 0-run 자격 구간
                    if (cyc == GAP-1) begin
                        cyc <= 17'd0;
                        if ({4'd0, idx} == n_lat - 16'd1)
                            state <= S_WAIT;
                        else begin
                            idx      <= idx + 12'd1;
                            spi_cs_n <= 1'b0;
                            state    <= S_CS;
                        end
                    end else
                        cyc <= cyc + 17'd1;
                end

                S_WAIT: begin
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
                    spi_cs_n     <= 1'b1;
                    sclk_en      <= 1'b0;
                    pay          <= 1'b0;
                    state        <= S_IDLE;
                end
            end
        end
    end

endmodule
