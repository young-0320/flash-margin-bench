/*
 * g0_sweep.c — G0 루프백 위상 스윕 (Vitis standalone, 계약 §3 호스트 시퀀스)
 *
 * 계약 §3 스텝 시퀀스를 그대로 옮긴 얇은 코드:
 *   PHASE_INC → PS_BUSY=0 폴 → MEAS_START → MEAS_DONE=1 폴
 *   → ERR_* 리드 + e_i 버퍼 회수(LOG_ADDR/LOG_DATA × N) → 행 출력, ×2,520스텝
 *
 * 출력은 UART 스트림 — PC측 host/capture/sweep_uart_capture.py가 파일화한다 (§3: PS는
 * 파일시스템 없음). 행 프로토콜:
 *   #G0 ...           메타/구분자 (BEGIN, COLS_*, END)
 *   M,<...>           메인 CSV 1행 (§6 열 중 PS가 아는 것 전부)
 *   R,<step>,<i>,<e>  동반 _reads.csv 1행 (읽기별 e_i 원본 — §6 필수)
 * target/generated_at/git_rev 열과 파일명 스탬프는 PC측이 붙인다 (PS는 시계·git 없음).
 *
 * 무효 런(§6): TIMEOUT ① / CFG_ERR ② / LOCKED=0 ③ / R8 불일치 ④는 그 자리에서
 * "#G0 SWEEP END valid=0"으로 중단. ⑤(미완주)는 END 자체가 안 나가므로 PC측이 판정.
 * ⑥(CMD_ERR)은 종료 시 1회 검사해 valid에 반영.
 *
 * R8 무결성(필수): Σe_i==ERR_BITS, count(e_i>0)==ERR_READS, 모든 e_i≤B.
 */

#include <stdint.h>
#include "xil_io.h"
#include "xil_printf.h"

/* build_g0_loopback.tcl이 배정한 베이스 (Address Editor: 0x43C0_0000, 4K) */
#define CORE_BASE       0x43C00000UL

#define REG_ID          (CORE_BASE + 0x00)
#define REG_CTRL        (CORE_BASE + 0x04)
#define REG_STATUS      (CORE_BASE + 0x08)
#define REG_N_READS     (CORE_BASE + 0x0C)
#define REG_BURST_BITS  (CORE_BASE + 0x10)
#define REG_PHASE_POS   (CORE_BASE + 0x14)
#define REG_ERR_BITS    (CORE_BASE + 0x18)
#define REG_ERR_READS   (CORE_BASE + 0x1C)
#define REG_LOG_ADDR    (CORE_BASE + 0x20)
#define REG_LOG_DATA    (CORE_BASE + 0x24)

#define ID_MAGIC        0x4D420100UL

#define CTRL_MEAS_START (1u << 0)
#define CTRL_PHASE_INC  (1u << 1)

#define ST_MEAS_BUSY    (1u << 0)
#define ST_MEAS_DONE    (1u << 1)
#define ST_PS_BUSY      (1u << 2)
#define ST_MMCM_LOCKED  (1u << 3)
#define ST_TIMEOUT      (1u << 4)
#define ST_CFG_ERR      (1u << 5)
#define ST_CMD_ERR      (1u << 6)

/* 계약 §5 수치 */
#define N_READS_CFG     100u
#define BURST_BITS_CFG  2048u
#define SWEEP_STEPS     2520u          /* 56 × 45 = 1 UI */
#define F_SCLK_HZ       25000000u
#define DPHI_PS_STR     "15.873016"    /* 40,000ps / 2,520 */

/*
 * 폴링 안전 한도 (무한 대기 방지 — R10이 하드웨어를 보장하지만 AXI/브리지
 * 고장까지는 못 덮는다). R10 T_max = 2N(B+64) = 422,400 clk_core 사이클
 * = 16.9ms @25MHz. AXI 왕복이 스핀당 >0.1us이므로 1e8 스핀 >> 수백 × T_max.
 */
#define POLL_LIMIT      100000000u

static uint16_t ei[2048];              /* R6: N ≤ 2,048 */
static uint16_t ei_prev[2048];         /* 무반응 라인 자가진단용 직전 스텝 e_i */
static uint32_t dead_armed;
static uint32_t low_seen;              /* BER<0.25 스텝 관측 여부 (no_window 판정) */

#define NEAR(a, b) ((a) >= (b) ? (a) - (b) <= 6u : (b) - (a) <= 6u)

/* 진단용 PRBS-15 (flash_prbs15.v와 동일 컨벤션) — line_dead 극성 분류에만 사용 */
static uint32_t prbs_ones(uint16_t idx, uint32_t nbits)
{
    uint16_t lfsr = (uint16_t)(0x4000u | (idx & 0x3FFFu));
    uint32_t ones = 0;
    for (uint32_t k = 0; k < nbits; k++) {
        ones += (lfsr >> 14) & 1u;
        lfsr = (uint16_t)(((lfsr << 1) | (((lfsr >> 14) ^ (lfsr >> 13)) & 1u))
                          & 0x7FFFu);
    }
    return ones;
}

static void print_u64(uint64_t v)      /* xil_printf는 64비트 미지원 */
{
    char buf[21];
    int  i = 20;
    buf[i] = '\0';
    do { buf[--i] = '0' + (char)(v % 10u); v /= 10u; } while (v);
    xil_printf("%s", &buf[i]);
}

static int poll_status(uint32_t mask, uint32_t want)
{
    for (uint32_t spin = 0; spin < POLL_LIMIT; spin++) {
        if ((Xil_In32(REG_STATUS) & mask) == want)
            return 0;
    }
    return -1;
}

static void end_sweep(int valid, const char *reason)
{
    xil_printf("#G0 SWEEP END valid=%d reason=%s\r\n", valid, reason);
    while (1) { /* 스윕 1회 = 부팅 1회. 재실행은 리셋으로 */ }
}

int main(void)
{
    /* 브링업 게이트: 주소 디코드(ID) → MMCM lock */
    uint32_t id = Xil_In32(REG_ID);
    if (id != ID_MAGIC) {
        xil_printf("#G0 ERROR bad ID: 0x%08x (expect 0x%08x)\r\n", id, ID_MAGIC);
        while (1) {}
    }
    if (poll_status(ST_MMCM_LOCKED, ST_MMCM_LOCKED) != 0) {
        xil_printf("#G0 ERROR MMCM not locked\r\n");
        while (1) {}
    }

    Xil_Out32(REG_N_READS,    N_READS_CFG);
    Xil_Out32(REG_BURST_BITS, BURST_BITS_CFG);

    xil_printf("#G0 SWEEP BEGIN steps=%u n=%u b=%u f_sclk_hz=%u dphi_ps=%s\r\n",
               SWEEP_STEPS, N_READS_CFG, BURST_BITS_CFG, F_SCLK_HZ, DPHI_PS_STR);
    xil_printf("#G0 COLS_MAIN phase_step,phase_ps,n_reads,b_bits,bit_errors,"
               "reads_with_error,bit_err_sq_sum,f_sclk_hz,dphi_ps\r\n");
    xil_printf("#G0 COLS_READS phase_step,read_idx,err_count\r\n");

    for (uint32_t step = 0; step < SWEEP_STEPS; step++) {
        /* 스텝 0은 리셋 위상(PHASE_POS=0) 그대로 측정 — phase_step과 PHASE_POS 일치 */
        if (step > 0) {
            Xil_Out32(REG_CTRL, CTRL_PHASE_INC);
            if (poll_status(ST_PS_BUSY, 0) != 0)
                end_sweep(0, "ps_busy_stuck");
        }
        if ((uint32_t)Xil_In32(REG_PHASE_POS) != step)
            end_sweep(0, "phase_pos_mismatch");     /* 호스트 루프 자체 검사 */

        Xil_Out32(REG_CTRL, CTRL_MEAS_START);
        if (poll_status(ST_MEAS_DONE, ST_MEAS_DONE) != 0)
            end_sweep(0, "done_stuck");             /* R10 위반 = 조사 대상 */

        uint32_t st = Xil_In32(REG_STATUS);
        if (st & ST_TIMEOUT)        end_sweep(0, "timeout");      /* 무효 ① */
        if (st & ST_CFG_ERR)        end_sweep(0, "cfg_err");      /* 무효 ② */
        if (!(st & ST_MMCM_LOCKED)) end_sweep(0, "lock_lost");    /* 무효 ③ */

        uint32_t err_bits  = Xil_In32(REG_ERR_BITS);
        uint32_t err_reads = Xil_In32(REG_ERR_READS);

        /* e_i 회수 (R3: 다음 START 전에 완료) + R8 무결성 + Σe_i² 파생(§6) */
        uint32_t sum = 0, nz = 0;
        uint64_t sq_sum = 0;
        for (uint32_t i = 0; i < N_READS_CFG; i++) {
            Xil_Out32(REG_LOG_ADDR, i);             /* 별도 리드 트랜잭션이 "주소
                                                       다음 사이클 유효"(§2)를 충족 */
            uint32_t e = Xil_In32(REG_LOG_DATA) & 0xFFFFu;
            ei[i] = (uint16_t)e;
            sum += e;
            nz  += (e != 0);
            sq_sum += (uint64_t)e * e;
            if (e > BURST_BITS_CFG)
                end_sweep(0, "r8_ei_gt_b");                       /* 무효 ④ */
        }
        if (sum != err_bits)  end_sweep(0, "r8_sum_mismatch");    /* 무효 ④ */
        if (nz != err_reads)  end_sweep(0, "r8_count_mismatch");  /* 무효 ④ */

        for (uint32_t i = 0; i < N_READS_CFG; i++)
            xil_printf("R,%u,%u,%u\r\n", step, i, ei[i]);

        /* phase_ps = step × Δφ. Δφ = VCO주기/56 = 10⁶/63 fs — VCO 고정이라
           클럭 사다리 공통 (25MHz의 UI/SWEEP_STEPS = 40×10⁶/2520과 동일값).
           정수 fs 연산, 소수 3자리 출력 */
        uint64_t fs = (uint64_t)step * 1000000ull / 63u;
        xil_printf("M,%u,%u.%03u,%u,%u,%u,%u,", step,
                   (uint32_t)(fs / 1000u), (uint32_t)(fs % 1000u),
                   N_READS_CFG, BURST_BITS_CFG, err_bits, err_reads);
        print_u64(sq_sum);
        xil_printf(",%u,%s\r\n", F_SCLK_HZ, DPHI_PS_STR);

        /* 저에러 스텝 관측 (BER < 0.25 상당) — 종료 시 no_window 판정용 */
        if (err_bits < (uint32_t)N_READS_CFG * BURST_BITS_CFG / 4u)
            low_seen = 1;

        /* 무반응 라인 자가진단 (리뷰 wf_16617fb7 #1, 결정 7/8): 위상을 바꿨는데
           e_i 벡터가 비트 단위로 동일 + 전 읽기 유에러 = 위상 무반응(무칩·단선·
           스턱). 창 밖(BER≈0.5) 유효 스텝은 노이즈라 두 스텝이 동일할 수 없고,
           죽은 라인은 결정론이라 항상 동일 — 스텝 2에서 중단. 검사를 행 출력 뒤에
           두어 중단 시점까지의 데이터(=결정론 고장의 전체 정보)가 캡처에 남는다.
           루프백 단선은 TIMEOUT(무효 ①)이 먼저 잡아 여기 못 온다.
           !low_seen 게이트(7/8 실측): 저노이즈 채널은 욕조 벽 평탄부에서 연속
           스텝 벡터가 결정론적으로 동일할 수 있다(루프백 스텝 952=953 실측).
           죽은 라인은 저에러 스텝을 낼 수 없으므로 low_seen=0인 동안만 검사. */
        if (err_reads == (uint32_t)N_READS_CFG && !low_seen) {
            if (dead_armed) {
                uint32_t same = 1;
                for (uint32_t i = 0; i < N_READS_CFG; i++)
                    if (ei[i] != ei_prev[i]) { same = 0; break; }
                if (same) {
                    /* stuck 극성 분류: 기대 PRBS의 1 개수와 대조. 허용 ±6은
                       3후보 min의 창 오프셋 슬롭. 둘 다 아니거나 겹치면 unknown */
                    uint32_t on0 = prbs_ones(0, BURST_BITS_CFG);
                    uint32_t on1 = prbs_ones(1, BURST_BITS_CFG);
                    uint32_t s0 = NEAR(ei[0], on0) && NEAR(ei[1], on1);
                    uint32_t s1 = NEAR(ei[0], BURST_BITS_CFG - on0) &&
                                  NEAR(ei[1], BURST_BITS_CFG - on1);
                    xil_printf("#G0 DIAG line_dead e0=%u e1=%u ones0=%u ones1=%u"
                               " b=%u\r\n", ei[0], ei[1], on0, on1, BURST_BITS_CFG);
                    if (s0 && !s1)      end_sweep(0, "line_dead_stuck0");
                    else if (s1 && !s0) end_sweep(0, "line_dead_stuck1");
                    else                end_sweep(0, "line_dead_unknown");
                }
            }
            for (uint32_t i = 0; i < N_READS_CFG; i++) ei_prev[i] = ei[i];
            dead_armed = 1;
        } else
            dead_armed = 0;
    }

    /* 무효 ⑥: 스윕 종료 시 CMD_ERR 1회 검사 (※7/8 추인 대상) */
    if (Xil_In32(REG_STATUS) & ST_CMD_ERR)
        end_sweep(0, "cmd_err");
    /* 애매한 고장 층 (결정 7/8): 완주했는데 저에러 스텝이 하나도 없으면 유효
       창이 없다 — 간헐 접촉·전원 문제류. 전체 에러 목록은 위에서 이미 출력됨 */
    if (!low_seen)
        end_sweep(0, "no_window");
    end_sweep(1, "complete");
    return 0;
}
