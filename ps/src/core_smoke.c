/*
 * core_smoke.c
 *
 * 작성: 장세은 (2026-07-08) — 리뷰·수정 내역은 하단 (로그 14)
 *
 * 목적: PS(Zynq bare-metal) <-> PL(core 블록, fpga/rtl/core/) 간
 *       AXI-Lite 통신이 정상 동작함을 확인하는 스모크 테스트.
 *       1회성 브링업이 아니라 반복 사용 도구 — 클럭 사다리(런북 3 D4)에서
 *       비트스트림을 갈아탈 때마다 core 생존 확인용 (배치는 G0·G3 공통).
 *
 * 확인 범위:
 *   1) ID 레지스터 리드백           - 주소 디코드 확인
 *   2) RW 레지스터 write/readback   - 버스 왕복 무결성
 *   3) MMCM_LOCKED                  - 위상 제어 전제조건
 *   4) 단발 측정 트랜잭션           - meas_start -> meas_busy -> meas_done
 *                                      핸드셰이크 (core <-> flash 경계까지 포함)
 *   5) R8 무결성 검사               - e_i 버퍼 회수 후 3중 검증
 *   6) CMD_ERR 음성 테스트          - 마지막 수행 (sticky, 리셋으로만 클리어)
 *
 * 근거 문서: docs/interface/ 인터페이스 계약 v1 (2026-07-08 3인 추인, 동결)
 *
 * 실행 환경: Vitis standalone bare-metal (OS 없음, Xil_Out32/In32 직접 접근)
 * 결과 확인: UART(xil_printf, STDOUT 기본 리다이렉트) 로 PC에 트랜잭션 로그 출력
 *
 * 빌드:       vitis -s ps/scripts/build_core_smoke.py   (G0 XSA 소비)
 * 프로그래밍: xsct ps/scripts/program_core_smoke.tcl    (G0 비트스트림 사용)
 *
 * 2026-07-08 수정 (리뷰 — 로그 14): %lu → %u 전체 치환 (xil_printf는
 * SUPPORT_64BIT_PRINT라 %lu가 64비트 va_arg를 소비 — u32는 %u, g0_sweep.c 관례),
 * CORE_BASEADDR 자리표시자를 실배치 확정값으로, 파일명 core_bringup_test.c →
 * core_smoke.c (반복 사용 도구 성격 반영). 그 외 세은 원문 그대로.
 */

#include "xil_io.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "sleep.h"

/* ------------------------------------------------------------------------
 * 0. 베이스 주소 / 레지스터 오프셋 / 비트 정의 (계약 §3 그대로)
 * ------------------------------------------------------------------------ */

/* build_g0_loopback.tcl·build_g3_chip.tcl 공통 배치 (Address Editor: 0x43C0_0000) */
#define CORE_BASEADDR   0x43C00000U

#define REG_ID           (CORE_BASEADDR + 0x00U)  /* RO */
#define REG_CTRL         (CORE_BASEADDR + 0x04U)  /* W, self-clear */
#define REG_STATUS       (CORE_BASEADDR + 0x08U)  /* RO */
#define REG_N_READS      (CORE_BASEADDR + 0x0CU)  /* RW, 리셋값 100 */
#define REG_BURST_BITS   (CORE_BASEADDR + 0x10U)  /* RW, 리셋값 2048 */
#define REG_PHASE_POS    (CORE_BASEADDR + 0x14U)  /* RO, signed */
#define REG_ERR_BITS     (CORE_BASEADDR + 0x18U)  /* RO */
#define REG_ERR_READS    (CORE_BASEADDR + 0x1CU)  /* RO */
#define REG_LOG_ADDR     (CORE_BASEADDR + 0x20U)  /* RW */
#define REG_LOG_DATA     (CORE_BASEADDR + 0x24U)  /* RO */

#define ID_MAGIC         0x4D420100U

/* CTRL bit (offset 0x04) - 명령 비트는 한 번에 하나만 세울 것 (계약 §3) */
#define CTRL_MEAS_START  (1U << 0)
#define CTRL_PHASE_INC   (1U << 1)
#define CTRL_PHASE_DEC   (1U << 2)

/* STATUS bit (offset 0x08) */
#define STATUS_MEAS_BUSY     (1U << 0)
#define STATUS_MEAS_DONE     (1U << 1)  /* sticky */
#define STATUS_PS_BUSY       (1U << 2)
#define STATUS_MMCM_LOCKED   (1U << 3)
#define STATUS_TIMEOUT       (1U << 4)  /* sticky, R10 */
#define STATUS_CFG_ERR       (1U << 5)  /* sticky, R11 */
#define STATUS_CMD_ERR       (1U << 6)  /* sticky, 리셋으로만 클리어 */

/* 리셋 기본값 (계약 §3) */
#define DEFAULT_N_READS      100U
#define DEFAULT_BURST_BITS   2048U

/* R10 워치독: T_max = 2 * N * (B + 64) clk_core 사이클, clk_core = 25MHz (계약 §5) */
#define CLK_CORE_HZ          25000000U
#define WATCHDOG_CYCLES(n, b)  (2U * (n) * ((b) + 64U))
#define WATCHDOG_US(n, b)    ((WATCHDOG_CYCLES((n), (b)) * 1000000ULL) / CLK_CORE_HZ)

/* 소프트웨어 폴링 타임아웃 = 워치독 예산의 3배 여유 (버스 지연·폴링 오버헤드 감안) */
#define SW_POLL_STEP_US      100U

/* ------------------------------------------------------------------------
 * 1. 레지스터 접근 헬퍼
 * ------------------------------------------------------------------------ */

static inline u32 reg_read(u32 addr)
{
    return Xil_In32(addr);
}

static inline void reg_write(u32 addr, u32 value)
{
    Xil_Out32(addr, value);
}

/* ------------------------------------------------------------------------
 * 2. 테스트 결과 집계
 * ------------------------------------------------------------------------ */

static int g_fail_count = 0;

static void report(const char *name, int pass, const char *detail)
{
    xil_printf("[%s] %s%s%s\r\n",
               pass ? " PASS" : " FAIL",
               name,
               detail ? " - " : "",
               detail ? detail : "");
    if (!pass) {
        g_fail_count++;
    }
}

/* ------------------------------------------------------------------------
 * 3. 테스트 1: ID 레지스터 리드백 (주소 디코드 확인)
 * ------------------------------------------------------------------------ */

static int test_id_register(void)
{
    u32 id = reg_read(REG_ID);
    int pass = (id == ID_MAGIC);

    xil_printf("  -> ID readback = 0x%08X (expected 0x%08X)\r\n", id, ID_MAGIC);
    report("TEST1 ID_REGISTER", pass, pass ? NULL : "주소 디코드 실패 - BASEADDR 확인 필요");
    return pass;
}

/* ------------------------------------------------------------------------
 * 4. 테스트 2: RW 레지스터 write/readback 왕복 (버스 무결성)
 *    N_READS, BURST_BITS 에 임의값을 쓰고 되읽어 확인한 뒤 기본값으로 복원.
 * ------------------------------------------------------------------------ */

static int test_rw_roundtrip(void)
{
    const u32 test_n = 50U;
    const u32 test_b = 512U;
    int pass = 1;

    reg_write(REG_N_READS, test_n);
    reg_write(REG_BURST_BITS, test_b);

    u32 rb_n = reg_read(REG_N_READS);
    u32 rb_b = reg_read(REG_BURST_BITS);

    xil_printf("  -> N_READS write=%u readback=%u\r\n", test_n, rb_n);
    xil_printf("  -> BURST_BITS write=%u readback=%u\r\n", test_b, rb_b);

    if (rb_n != test_n || rb_b != test_b) {
        pass = 0;
    }

    /* 계약 §5 기본값으로 복원 (이후 측정 테스트가 기본 조건에서 돌도록) */
    reg_write(REG_N_READS, DEFAULT_N_READS);
    reg_write(REG_BURST_BITS, DEFAULT_BURST_BITS);

    report("TEST2 RW_ROUNDTRIP", pass, pass ? NULL : "write/readback 불일치 - 버스 또는 레지스터 파일 오류");
    return pass;
}

/* ------------------------------------------------------------------------
 * 5. 테스트 3: MMCM_LOCKED 확인
 * ------------------------------------------------------------------------ */

static int test_mmcm_locked(void)
{
    u32 status = reg_read(REG_STATUS);
    int pass = (status & STATUS_MMCM_LOCKED) != 0;

    xil_printf("  -> STATUS = 0x%08X (MMCM_LOCKED=%d)\r\n",
               status, pass);
    report("TEST3 MMCM_LOCKED", pass, pass ? NULL : "MMCM 미락 - 위상 스윕 불가 상태");
    return pass;
}

/* ------------------------------------------------------------------------
 * 6. 테스트 4: 단발 측정 트랜잭션
 *    R4: busy 중 명령 무시 -> start 전 MEAS_BUSY/PS_BUSY=0 확인
 *    R1~R3, R10, R11 순서를 그대로 따른다.
 * ------------------------------------------------------------------------ */

static int test_single_measurement(u32 *out_err_bits, u32 *out_err_reads)
{
    u32 status;
    int pass = 1;

    /* 사전조건: busy=0 이어야 명령이 먹힌다 (R4) */
    status = reg_read(REG_STATUS);
    if (status & (STATUS_MEAS_BUSY | STATUS_PS_BUSY)) {
        report("TEST4 SINGLE_MEASUREMENT", 0, "사전조건 위반 - busy 상태에서 시작");
        return 0;
    }

    /* 기본 설정값 확인 (N=100, B=2048) */
    u32 n = reg_read(REG_N_READS);
    u32 b = reg_read(REG_BURST_BITS);
    xil_printf("  -> config: N=%u, B=%u\r\n", n, b);

    /* 측정 개시: CTRL 명령 비트는 한 번에 하나만 (계약 §3) */
    reg_write(REG_CTRL, CTRL_MEAS_START);

    u32 timeout_us = (u32)(3ULL * WATCHDOG_US(n, b)) + 1000U; /* 3배 여유 */
    u32 waited_us = 0;
    int done = 0;

    while (waited_us < timeout_us) {
        status = reg_read(REG_STATUS);
        if (status & STATUS_MEAS_DONE) {
            done = 1;
            break;
        }
        usleep(SW_POLL_STEP_US);
        waited_us += SW_POLL_STEP_US;
    }

    xil_printf("  -> waited=%uus (sw timeout budget=%uus), STATUS=0x%08X\r\n",
               waited_us, timeout_us, status);

    if (!done) {
        report("TEST4 SINGLE_MEASUREMENT", 0, "소프트웨어 타임아웃 - meas_done 미수신");
        return 0;
    }

    /* 계약 §4 R10, R11: TIMEOUT/CFG_ERR sticky 플래그 확인 */
    if (status & STATUS_TIMEOUT) {
        report("TEST4 SINGLE_MEASUREMENT", 0, "STATUS.TIMEOUT set - 워치독 강제 종료(R10), 무효 스텝");
        pass = 0;
    }
    if (status & STATUS_CFG_ERR) {
        report("TEST4 SINGLE_MEASUREMENT", 0, "STATUS.CFG_ERR set - R11 설정 검증 실패, 측정 미개시");
        pass = 0;
    }
    if (!pass) {
        return 0;
    }

    /* 결과 리드 (R3: meas_done부터 다음 start 전까지 유효) */
    u32 err_bits = reg_read(REG_ERR_BITS);
    u32 err_reads = reg_read(REG_ERR_READS);

    xil_printf("  -> ERR_BITS=%u, ERR_READS=%u (of N=%u reads, B=%u bits/read)\r\n",
               err_bits, err_reads, n, b);

    *out_err_bits = err_bits;
    *out_err_reads = err_reads;

    report("TEST4 SINGLE_MEASUREMENT", 1, "start->busy->done 핸드셰이크 정상");
    return 1;
}

/* ------------------------------------------------------------------------
 * 7. 테스트 5: R8 무결성 검사
 *    ① sum(e_i) == ERR_BITS
 *    ② count(e_i > 0) == ERR_READS
 *    ③ 모든 e_i <= B
 *    버퍼 회수는 다음 START 전에 완료해야 하므로(R3), TEST4 직후에만 호출할 것.
 * ------------------------------------------------------------------------ */

static int test_buffer_integrity(u32 expected_err_bits, u32 expected_err_reads)
{
    u32 n = reg_read(REG_N_READS);
    u32 b = reg_read(REG_BURST_BITS);

    u32 sum_ei = 0;
    u32 count_nonzero = 0;
    int range_ok = 1;
    u32 first_violation_idx = 0xFFFFFFFFU;

    for (u32 i = 0; i < n; i++) {
        reg_write(REG_LOG_ADDR, i);
        /* 계약 §2: 주소 제시 다음 사이클 유효. AXI-Lite 리드 자체가
         * 별도 트랜잭션이므로 write 이후 read 사이에 충분한 지연이 있다. */
        u32 e_i = reg_read(REG_LOG_DATA);

        sum_ei += e_i;
        if (e_i > 0) {
            count_nonzero++;
        }
        if (e_i > b && range_ok) {
            range_ok = 0;
            first_violation_idx = i;
        }
    }

    xil_printf("  -> buffer scan: sum(e_i)=%u, count(e_i>0)=%u, N=%u, B=%u\r\n",
               sum_ei, count_nonzero, n, b);

    int cond1 = (sum_ei == expected_err_bits);
    int cond2 = (count_nonzero == expected_err_reads);
    int cond3 = range_ok;

    xil_printf("  -> R8-1 sum==ERR_BITS: %s (expected %u)\r\n",
               cond1 ? "OK" : "MISMATCH", expected_err_bits);
    xil_printf("  -> R8-2 count==ERR_READS: %s (expected %u)\r\n",
               cond2 ? "OK" : "MISMATCH", expected_err_reads);
    if (!cond3) {
        xil_printf("  -> R8-3 e_i<=B: VIOLATION at index %u\r\n", first_violation_idx);
    } else {
        xil_printf("  -> R8-3 e_i<=B: OK\r\n");
    }

    int pass = cond1 && cond2 && cond3;
    report("TEST5 BUFFER_INTEGRITY(R8)", pass,
           pass ? NULL : "e_i 버퍼 불일치 - 카운터/버퍼 경로 구현 버그 의심, 해당 스윕은 _invalid 처리 대상");
    return pass;
}

/* ------------------------------------------------------------------------
 * 8. 테스트 6: CMD_ERR 음성 테스트 (마지막에만 실행)
 *    CTRL에 명령 비트 2개 이상을 동시에 세워 CMD_ERR가 정상적으로
 *    걸리는지 확인한다. CMD_ERR는 sticky이며 리셋으로만 클리어되므로
 *    이 테스트 이후 다른 STATUS 판단에 영향을 주지 않도록 항상 마지막에 둔다.
 * ------------------------------------------------------------------------ */

static int test_cmd_err_negative(void)
{
    u32 status_before = reg_read(REG_STATUS);
    if (status_before & STATUS_CMD_ERR) {
        xil_printf("  -> 주의: CMD_ERR가 이미 set 상태 (이전 리셋 이후 잔류) - 그래도 진행\r\n");
    }

    /* 고의 위반: MEAS_START + PHASE_INC 동시 요청 (명령 비트 2개 이상) */
    reg_write(REG_CTRL, CTRL_MEAS_START | CTRL_PHASE_INC);
    usleep(SW_POLL_STEP_US);

    u32 status_after = reg_read(REG_STATUS);
    int pass = (status_after & STATUS_CMD_ERR) != 0;

    xil_printf("  -> STATUS after invalid CTRL write = 0x%08X (CMD_ERR=%d)\r\n",
               status_after, pass);
    report("TEST6 CMD_ERR_NEGATIVE", pass,
           pass ? "예상대로 CMD_ERR 발생 (정상 - 리셋 전까지 sticky 유지)"
                : "CMD_ERR 미발생 - 명령 인코딩 검증 로직 확인 필요");
    return pass;
}

/* ------------------------------------------------------------------------
 * 9. main
 * ------------------------------------------------------------------------ */

int main(void)
{
    u32 err_bits = 0, err_reads = 0;

    xil_printf("\r\n============================================================\r\n");
    xil_printf(" flash-margin-bench : core <-> PS AXI-Lite smoke test\r\n");
    xil_printf(" CORE_BASEADDR = 0x%08X\r\n", (unsigned int)CORE_BASEADDR);
    xil_printf("============================================================\r\n\r\n");

    int t1 = test_id_register();
    xil_printf("\r\n");

    if (!t1) {
        xil_printf("ID 리드백 실패 - 이후 테스트를 진행해도 신뢰할 수 없으므로 중단합니다.\r\n");
        xil_printf("BASEADDR 및 Vivado 주소 편집기 배치를 먼저 확인하십시오.\r\n");
        return -1;
    }

    test_rw_roundtrip();
    xil_printf("\r\n");

    int t3 = test_mmcm_locked();
    xil_printf("\r\n");

    if (t3) {
        int t4 = test_single_measurement(&err_bits, &err_reads);
        xil_printf("\r\n");

        if (t4) {
            test_buffer_integrity(err_bits, err_reads);
            xil_printf("\r\n");
        } else {
            xil_printf("측정 트랜잭션 실패로 R8 무결성 검사를 건너뜁니다.\r\n\r\n");
        }
    } else {
        xil_printf("MMCM 미락 상태이므로 측정 관련 테스트를 건너뜁니다.\r\n\r\n");
    }

    test_cmd_err_negative();
    xil_printf("\r\n");

    xil_printf("============================================================\r\n");
    if (g_fail_count == 0) {
        xil_printf(" 결과: 전체 PASS - core <-> PS 통신 정상 확인\r\n");
    } else {
        xil_printf(" 결과: %d건 FAIL - 위 로그에서 원인 확인 필요\r\n", g_fail_count);
    }
    xil_printf("============================================================\r\n\r\n");

    return g_fail_count == 0 ? 0 : -1;
}
