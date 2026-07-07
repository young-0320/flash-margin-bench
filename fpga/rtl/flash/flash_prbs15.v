`timescale 1ns / 1ps
// flash_prbs15.v — PRBS-15 엔진 (계약 결정 19: x¹⁵+x¹⁴+1, 시드 {1, index[13:0]})
//
// 방출 컨벤션 (golden model이 재현해야 하는 정확한 정의):
//  - dout = lfsr[14] (현재 상태 MSB). load 직후 첫 출력 = seed[14] = 1 (구조적 고정)
//  - en 1회마다: lfsr <= {lfsr[13:0], lfsr[14]^lfsr[13]}
//  → 방출 열 = seed[14], seed[13], …, seed[0], 이후 피드백 비트들 (시드 MSB-first)
// TX(패턴 생성)와 RX(기대값 재생성)가 같은 모듈을 인스턴스 — 정답지 대신 규칙 공유.

module flash_prbs15 (
    input  wire        clk,
    input  wire        load,   // 시드 재장전 (버스트마다 — 계약 19: 오염 격리 방화벽)
    input  wire [14:0] seed,   // {1'b1, index[13:0]} — 0 불가 구조
    input  wire        en,     // 1비트 방출(시프트)
    output wire        dout
);

    reg [14:0] lfsr;
    assign dout = lfsr[14];

    always @(posedge clk) begin
        if (load)    lfsr <= seed;
        else if (en) lfsr <= {lfsr[13:0], lfsr[14] ^ lfsr[13]};
    end

endmodule
