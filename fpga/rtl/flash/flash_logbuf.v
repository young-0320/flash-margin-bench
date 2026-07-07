`timescale 1ns / 1ps
// flash_logbuf.v — e_i 버퍼 BRAM 2,048×16b (계약 §2, 결정 3-4: 읽기별 에러 수 원시 보존)
//
// 듀얼 클럭 단순 이중 포트: 쓰기 @clk_sample(측정 중), 읽기 @clk_core(done 이후 회수).
// 두 포트가 동시에 같은 주소를 건드리는 일은 프로토콜이 배제한다 — R3: 결과는
// done~다음 start 사이에만 읽고, start가 버퍼를 덮어쓴다.
// 읽기는 주소 제시 다음 사이클 유효 (계약 §2 log_rd_data 규약 그대로).

module flash_logbuf (
    input  wire        wclk,      // clk_sample
    input  wire        we,
    input  wire [11:0] waddr,
    input  wire [15:0] wdata,

    input  wire        rclk,      // clk_core
    input  wire [11:0] raddr,
    output reg  [15:0] rdata
);

    reg [15:0] mem [0:2047];

    always @(posedge wclk)
        if (we) mem[waddr[10:0]] <= wdata;

    always @(posedge rclk)
        rdata <= mem[raddr[10:0]];  // 상위 비트 무시 (N ≤ 2,048)

endmodule
