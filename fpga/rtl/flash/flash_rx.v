`timescale 1ns / 1ps
// flash_rx.v — clk_sample 도메인 수신부: 캡처 → 버스트 검출 → 비교 → e_i 산출
//
// 여기가 G0의 최대 기술 난제(캡처 프레이밍 ±1 사이클)를 처리하는 곳이다.
// clk_core/clk_sample은 같은 VCO에서 나와 주파수가 완전히 같고(드리프트 0),
// 위상만 다르다(mesochronous). 위상 스텝에 따라 샘플열의 정수 비트 정렬 d가
// 바뀌고, 전이 경계 부근에서는 프리앰블 에지 샘플이 0/1 중 어느 쪽으로도
// 읽힐 수 있어 검출이 ±1 흔들린다. 고정 정렬로 비교하면 스윕 절반이 BER 0.5
// 절벽이 된다(분석기 체크 5가 잡는 증상).
//
// 대책 — 버스트마다(갭 = CS 경계) 독립 재정렬:
//  1) 갭의 0-run(≥8)으로 자격을 얻은 뒤 첫 1 샘플 = t0 (프리앰블 비트0 후보)
//  2) 페이로드 시작 후보 3개(t0+3, t0+4(공칭), t0+5)를 병렬 비교 —
//     기대열은 PRBS 1개 + 지연 플롭 2개로 3개 오프셋 동시 생성
//  3) e_i = min(e0,e1,e2). 옳은 정렬은 진짜 비트 에러만 세고, 틀린 정렬은
//     ≈B/2라 벽 적합 영역(BER ≤ 0.25)에서 항상 명확히 분리된다.
//     정직한 한계: 포화 영역(진짜 BER→0.5)에서는 min이 0.5를 약간 밑돌 수
//     있다 — 통계가 쓰는 벽 영역 밖이라 무해 (로그 7에 기록).
//
// 도메인 규율: 이 모듈 전체가 clk_sample. 리셋 없음 — run_s(2FF)가 0이면 전부
// 초기화(DISARM)라 리셋 CDC가 필요 없다. n_lat/b_lat은 start 래치 후 불변인
// 준정적 값. 결과(err_*, BRAM)는 rx_done을 올리기 전에 이미 멈춘다.

module flash_rx (
    input  wire        clk_sample,
    input  wire        din_pin,     // JE2 (W16)
    input  wire        run_s,       // 측정 창 레벨 (2FF 동기 완료)
    input  wire [15:0] n_lat,       // 준정적
    input  wire [15:0] b_lat,       // 준정적

    output reg         rx_done,     // 레벨 — N버스트 집계 완료
    output reg  [31:0] err_bits,
    output reg  [31:0] err_reads,

    // e_i 버퍼 쓰기 포트
    output reg         log_we,
    output reg  [11:0] log_waddr,
    output reg  [15:0] log_wdata
);

    localparam [2:0] S_DIS = 3'd0, S_HUNT = 3'd1, S_CMP = 3'd2,
                     S_TALLY = 3'd3, S_DONE = 3'd4;

    // 캡처 사슬: IOB 플롭(측정 그 자체) → 메타 해소 → 사용
    (* IOB = "TRUE" *)       reg cap;
    (* ASYNC_REG = "TRUE" *) reg meta;
    reg d;
    always @(posedge clk_sample) begin
        cap  <= din_pin;
        meta <= cap;
        d    <= meta;
    end

    reg [2:0]  state;
    reg [3:0]  zcnt;      // 0-run 자격 카운터 (포화 8)
    reg [17:0] cc;        // t0 이후 사이클 (최대 B+4)
    reg [11:0] idx;       // 버스트 인덱스 = e_i 주소 = PRBS 시드 인덱스
    reg [15:0] e0, e1, e2;
    reg        pd1, pd2;  // 기대 비트 지연선 (+1, +2 오프셋용)

    wire pd0;
    flash_prbs15 u_rx_prbs (
        .clk  (clk_sample),
        .load (state == S_HUNT),
        .seed ({1'b1, 2'b00, idx}),
        .en   ((state == S_CMP) && (cc >= 18'd3) && (cc <= {2'd0, b_lat} + 18'd2)),
        .dout (pd0)
    );

    // min(e0, e1, e2)
    wire [15:0] min01  = (e0 <= e1) ? e0 : e1;
    wire [15:0] ei_min = (min01 <= e2) ? min01 : e2;

    always @(posedge clk_sample) begin
        log_we <= 1'b0;

        if (!run_s) begin
            state   <= S_DIS;
            rx_done <= 1'b0;
        end else begin
            case (state)
                S_DIS: begin   // run 상승 = 새 측정: 전부 초기화 (R3: start가 결과를 덮음)
                    err_bits  <= 32'd0;
                    err_reads <= 32'd0;
                    idx       <= 12'd0;
                    zcnt      <= 4'd0;
                    e0 <= 16'd0; e1 <= 16'd0; e2 <= 16'd0;
                    state     <= S_HUNT;
                end

                S_HUNT: begin
                    if (d) begin
                        if (zcnt >= 4'd8) begin  // 자격 통과 후 첫 1 = t0
                            cc    <= 18'd1;
                            state <= S_CMP;
                        end
                        zcnt <= 4'd0;
                    end else if (zcnt < 4'd8)
                        zcnt <= zcnt + 4'd1;
                end

                S_CMP: begin
                    cc  <= cc + 18'd1;
                    pd1 <= pd0;
                    pd2 <= pd1;
                    // 세 오프셋의 B-샘플 창 (공칭 = t0+4 시작)
                    if (cc >= 18'd3 && cc <= {2'd0, b_lat} + 18'd2 && d != pd0) e0 <= e0 + 16'd1;
                    if (cc >= 18'd4 && cc <= {2'd0, b_lat} + 18'd3 && d != pd1) e1 <= e1 + 16'd1;
                    if (cc >= 18'd5 && cc <= {2'd0, b_lat} + 18'd4 && d != pd2) e2 <= e2 + 16'd1;
                    if (cc == {2'd0, b_lat} + 18'd4)
                        state <= S_TALLY;
                end

                S_TALLY: begin
                    log_we    <= 1'b1;
                    log_waddr <= idx;
                    log_wdata <= ei_min;
                    err_bits  <= err_bits + {16'd0, ei_min};
                    if (ei_min != 16'd0) err_reads <= err_reads + 32'd1;
                    e0 <= 16'd0; e1 <= 16'd0; e2 <= 16'd0;
                    zcnt <= 4'd0;
                    if ({4'd0, idx} == n_lat - 16'd1) begin
                        rx_done <= 1'b1;     // 이 시점에 err_*·BRAM은 이미 확정
                        state   <= S_DONE;
                    end else begin
                        idx   <= idx + 12'd1;
                        state <= S_HUNT;
                    end
                end

                S_DONE: ;   // run_s 하강까지 결과 동결 유지

                default: state <= S_DIS;
            endcase
        end
    end

endmodule
