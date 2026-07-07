`timescale 1ns / 1ps
// flash_sync2.v — 1비트 2FF 동기화기. run(clk_core→clk_sample), rx_done(반대 방향)
// 두 곳에서 사용. 멀티비트 결과(err_*, BRAM)는 동기화하지 않는다 — done 시점에
// 이미 멈춘 값이라 준정적(quasi-static) 크로싱 (계약 1-1 CDC 방침).

module flash_sync2 (
    input  wire clk,
    input  wire d,
    output wire q
);

    (* ASYNC_REG = "TRUE" *) reg [1:0] r = 2'b00;
    always @(posedge clk) r <= {r[0], d};
    assign q = r[1];

endmodule
