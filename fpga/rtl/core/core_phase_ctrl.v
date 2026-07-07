`timescale 1ns / 1ps
// core_phase_ctrl.v — MMCM 동적 위상 시프트 핸드셰이크 (UG472)
//
// PSEN은 정확히 1사이클, PSDONE(약 12 PSCLK 후)까지 새 명령 금지 — 그 구간이
// ps_busy이고 STATUS.PS_BUSY로 노출된다. R1(위상 이동 완료 후에만 start)은
// 레지스터 파일이 ps_busy로 명령을 게이팅해서 집행한다.
// phase_pos는 리셋 기준 누적 스텝 (PHASE_POS, signed 32) — 완료(PSDONE) 시점에 갱신.

module core_phase_ctrl (
    input  wire        clk,         // = clk_core = PSCLK
    input  wire        rstn,

    input  wire        cmd_valid,   // 1펄스 (레지스터 파일에서 게이팅 완료)
    input  wire        cmd_incdec,  // 1=INC

    output reg         psen,
    output reg         psincdec,
    input  wire        psdone,

    output reg         ps_busy,
    output reg  signed [31:0] phase_pos
);

    always @(posedge clk) begin
        if (!rstn) begin
            psen      <= 1'b0;
            psincdec  <= 1'b0;
            ps_busy   <= 1'b0;
            phase_pos <= 32'sd0;
        end else begin
            psen <= 1'b0;
            if (!ps_busy && cmd_valid) begin
                psen     <= 1'b1;
                psincdec <= cmd_incdec;
                ps_busy  <= 1'b1;
            end else if (ps_busy && psdone) begin
                ps_busy   <= 1'b0;
                phase_pos <= phase_pos + (psincdec ? 32'sd1 : -32'sd1);
            end
        end
    end

endmodule
