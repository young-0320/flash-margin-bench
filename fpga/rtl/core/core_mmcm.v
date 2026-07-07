`timescale 1ns / 1ps
// core_mmcm.v — MMCME2_ADV 래퍼 (계약 결정 16: M=9, D=1 → VCO 1,125MHz, O=45 → 25MHz)
//
// Xilinx 프리미티브를 이 파일에만 격리한다 — 시뮬레이션에서는 이 모듈만
// 행동 스텁으로 대체하면 나머지 core 로직이 전부 순수 Verilog로 돈다.
//
// - clk_core   : CLKOUT0, 고정 위상. SPI/제어/AXI 전 도메인 (계약 §1)
// - clk_sample : CLKOUT1, USE_FINE_PS — PSEN 1회당 VCO주기/56 = 15.87ps 이동
// - 피드백은 내부 직결(COMPENSATION="INTERNAL") — 입력 클럭과의 정렬은 불필요,
//   clk_core ↔ clk_sample 상대 위상만이 계측 대상
// - PSCLK = clk_core: 위상 제어 FSM(core_phase_ctrl)과 같은 도메인

module core_mmcm (
    input  wire clk_in_125,   // 보드 125MHz (K17, 계약 §5)
    input  wire rst,          // 비동기 high — MMCM 재로크용, 평시 0 고정
    output wire clk_core,     // 25MHz 고정 위상
    output wire clk_sample,   // 25MHz 가변 위상
    output wire locked,       // 비동기 — 사용처에서 동기화

    // 동적 위상 시프트 (clk_core 도메인)
    input  wire psen,
    input  wire psincdec,     // 1=지연 증가(INC)
    output wire psdone
);

    wire clkfb;
    wire clk_core_u, clk_sample_u;

    MMCME2_ADV #(
        .BANDWIDTH          ("OPTIMIZED"),
        .CLKIN1_PERIOD      (8.000),      // 125MHz
        .DIVCLK_DIVIDE      (1),          // D=1 — 지터 최선 구성 (결정 16)
        .CLKFBOUT_MULT_F    (9.000),      // M=9 → VCO 1,125MHz
        .CLKOUT0_DIVIDE_F   (45.000),     // clk_core 25MHz
        .CLKOUT1_DIVIDE     (45),         // clk_sample 25MHz
        .CLKOUT1_USE_FINE_PS("TRUE"),     // 위상 시프트는 clk_sample에만 (계약 §1 A안)
        .COMPENSATION       ("INTERNAL")
    ) u_mmcm (
        .CLKIN1   (clk_in_125),
        .CLKIN2   (1'b0),
        .CLKINSEL (1'b1),
        .CLKFBIN  (clkfb),
        .CLKFBOUT (clkfb),
        .CLKFBOUTB(),
        .CLKOUT0  (clk_core_u),
        .CLKOUT0B (),
        .CLKOUT1  (clk_sample_u),
        .CLKOUT1B (),
        .CLKOUT2  (),
        .CLKOUT2B (),
        .CLKOUT3  (),
        .CLKOUT3B (),
        .CLKOUT4  (),
        .CLKOUT5  (),
        .CLKOUT6  (),
        .LOCKED       (locked),
        .CLKFBSTOPPED (),
        .CLKINSTOPPED (),
        .PSCLK    (clk_core),
        .PSEN     (psen),
        .PSINCDEC (psincdec),
        .PSDONE   (psdone),
        .DADDR    (7'd0),
        .DCLK     (1'b0),
        .DEN      (1'b0),
        .DI       (16'd0),
        .DWE      (1'b0),
        .DO       (),
        .DRDY     (),
        .PWRDWN   (1'b0),
        .RST      (rst)
    );

    BUFG u_bufg_core   (.I(clk_core_u),   .O(clk_core));
    BUFG u_bufg_sample (.I(clk_sample_u), .O(clk_sample));

endmodule
