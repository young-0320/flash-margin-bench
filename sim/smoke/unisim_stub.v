`timescale 1ns / 1ps
// 시뮬레이션 전용 스텁 — core_mmcm이 참조하는 Xilinx 프리미티브의 행동 모델.
// CLKOUT0/1은 CLKIN 무시하고 25MHz 자유 발진, PSDONE은 PSEN 12 PSCLK 후 1펄스.

module MMCME2_ADV #(
    parameter BANDWIDTH = "OPTIMIZED",
    parameter real CLKIN1_PERIOD = 0.0,
    parameter integer DIVCLK_DIVIDE = 1,
    parameter real CLKFBOUT_MULT_F = 5.0,
    parameter real CLKOUT0_DIVIDE_F = 1.0,
    parameter integer CLKOUT1_DIVIDE = 1,
    parameter CLKOUT1_USE_FINE_PS = "FALSE",
    parameter COMPENSATION = "ZHOLD"
) (
    input  wire CLKIN1, CLKIN2, CLKINSEL, CLKFBIN,
    output wire CLKFBOUT, CLKFBOUTB,
    output wire CLKOUT0, CLKOUT0B, CLKOUT1, CLKOUT1B,
    output wire CLKOUT2, CLKOUT2B, CLKOUT3, CLKOUT3B,
    output wire CLKOUT4, CLKOUT5, CLKOUT6,
    output reg  LOCKED,
    output wire CLKFBSTOPPED, CLKINSTOPPED,
    input  wire PSCLK, PSEN, PSINCDEC,
    output reg  PSDONE,
    input  wire [6:0] DADDR,
    input  wire DCLK, DEN, DWE,
    input  wire [15:0] DI,
    output wire [15:0] DO,
    output wire DRDY,
    input  wire PWRDWN, RST
);
    reg clk25 = 1'b0;
    always #20 clk25 = ~clk25;   // 25MHz

    assign CLKOUT0 = clk25;
    assign CLKOUT1 = clk25;
    assign CLKFBOUT = 1'b0;
    assign {CLKFBOUTB, CLKOUT0B, CLKOUT1B, CLKOUT2, CLKOUT2B,
            CLKOUT3, CLKOUT3B, CLKOUT4, CLKOUT5, CLKOUT6} = 10'd0;
    assign {CLKFBSTOPPED, CLKINSTOPPED, DRDY} = 3'd0;
    assign DO = 16'd0;

    initial begin
        LOCKED = 1'b0;
        #500 LOCKED = 1'b1;
    end

    integer ps_cnt = 0;
    reg ps_active = 1'b0;
    initial PSDONE = 1'b0;
    always @(posedge PSCLK) begin
        PSDONE <= 1'b0;
        if (PSEN && !ps_active) begin
            if (ps_active) $display("STUB ERROR: PSEN during shift");
            ps_active <= 1'b1;
            ps_cnt <= 0;
        end else if (ps_active) begin
            ps_cnt <= ps_cnt + 1;
            if (ps_cnt == 10) begin   // PSEN 후 12번째 PSCLK 부근에서 DONE
                PSDONE <= 1'b1;
                ps_active <= 1'b0;
            end
        end
    end
endmodule

module BUFG (input wire I, output wire O);
    assign O = I;
endmodule
