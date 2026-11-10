/*
 * bathtub_v2.c — 욕조 v2 측정 (훑기 → 벽 집중, Vitis standalone)
 *
 * 정본: docs/spec/s6.bathtub_v2.md §2 · §3 (파라미터 · 절차 ①-⑦) · docs/interface/amendments/4.edge_counter_bathtub_v2.md
 * (LOG_C0-2 · FEATURE · R8 ④⑤⑥ · v2 행 · 무효 ⑦-⑭ · END 행 수) · amendments/1.base_sector.md (BASE_SECTOR · 쪽 번호).
 * v1 스윕(g0_sweep.c)은 그대로 두고 따로 둔다 — 마모 체크포인트는 v1 이다 ([D55-10]).
 *
 * 절차 (S-6 §3):
 *   ① FEATURE bit0 · PHASE_POS == 0 · BASE_SECTOR(0 아니면 FEATURE bit1, 되읽기 일치) 확인 → BEGIN
 *   ② 훑기   스텝 0 → UI 끝, 스텝마다 START 1회(N = 1). pass=scan. 무반응 검사(⑦)는 여기서만
 *   ③ 덩어리 바닥 = 가장 긴 원형 0 구간, 덩어리 = 그 여집합 — ⑧ ⑬ ⑨ ⑭ · block_out_of_range
 *   ④ 천장   덩어리 안 훑기 오류 ≥ CEIL_ERR 스텝 → 112회 한 묶음. pass=ceil
 *   ⑤ 벽     덩어리 안 나머지 → 벽 N, 경계 바깥으로 한 스텝씩 벽 N — 0 오류 K 연속이면 멈춤.
 *            바깥 스텝 묶음의 읽기당 평균 ≥ CEIL_ERR 이면 그 자리에서 ⑫, 64스텝 넘으면 ⑩. pass=wall
 *   ⑥ 끝 훑기 ② 한 번 더. pass=rescan — 천장 양 끝 1스텝 넘게 다르면 drift, 덩어리 둘 이상이면 rescan_multi_block
 *   ⑦ END    main_rows · reads_rows · mode · flags
 *
 * 행 프로토콜 (수정안 #4 §2.5):
 *   M,<v1 메인 열 9개>,<pass>      (pass, phase_step) 하나에 한 줄. bit_errors · 제곱합은 u64 (§2.4)
 *   R,<step>,<i>,<e>,<e_c0>,<e_c1>,<e_c2>,<e1_c0>,<e1_c1>,<e1_c2>
 *                                  읽기 하나에 한 줄. pass 는 싣지 않는다 — R 묶음 뒤에 그 M 이 오므로 캡처가 순서로 붙인다
 *   read_idx 는 START(묶음)마다 0 부터. 읽은 쪽은 base_sector × 16 + read_idx
 *
 * 위상: INC · DEC 를 섞는다. 기대 위치를 int32 로 세고(INC +1 · DEC −1) 측정마다 PHASE_POS(signed 32)와
 * 정확히 비교한다. 스텝 = ((pos mod UI) + UI) mod UI — 덩어리가 UI 끝 → 0 에 걸쳐도 같은 절차다.
 *
 * 실행 때 덮어쓰는 값 (g_uart_baud 와 같은 방식, 로그 49): g_wall_n(벽 N — std 8,064 · deep 2,064,384) ·
 * g_base_sector. xsct 가 dow 뒤 con 앞에 print -set 으로 덮어쓴다 (program_g3.tcl, BATHTUB2_* 환경변수).
 *
 * 75MHz 묶음(S-6 §2)은 빌드 때 치환한다 — ps/scripts/bathtub_v2_gen.py. 이 파일의 상수는 25MHz 값이다.
 * 호스트 시뮬레이션: ps/sim/build_bt2_sim.sh (같은 소스를 가짜 레지스터 위에 올린다).
 */

#include <stdint.h>
#include "xil_io.h"
#include "xil_printf.h"
#include "xparameters.h"
#include "xuartps.h"

/* g0_sweep.c 와 같은 베이스 (Address Editor: 0x43C0_0000, 4K) */
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
#define REG_BASE_SECTOR (CORE_BASE + 0x28)     /* 수정안 #1 */
#define REG_LOG_C0      (CORE_BASE + 0x2C)     /* 수정안 #4 — [15:0] e_c · [31:16] e1_c */
#define REG_LOG_C1      (CORE_BASE + 0x30)
#define REG_LOG_C2      (CORE_BASE + 0x34)
#define REG_FEATURE     (CORE_BASE + 0x38)     /* bit0 에지 계수기 · bit1 BASE_SECTOR */

#define ID_MAGIC        0x4D420100u            /* 그대로 ([D55-18]) — 기능 유무는 FEATURE */
#define FEAT_EDGE       (1u << 0)
#define FEAT_BASE_SECTOR (1u << 1)

#define CTRL_MEAS_START (1u << 0)
#define CTRL_PHASE_INC  (1u << 1)
#define CTRL_PHASE_DEC  (1u << 2)

#define ST_MEAS_BUSY    (1u << 0)
#define ST_MEAS_DONE    (1u << 1)
#define ST_PS_BUSY      (1u << 2)
#define ST_MMCM_LOCKED  (1u << 3)
#define ST_TIMEOUT      (1u << 4)
#define ST_CFG_ERR      (1u << 5)
#define ST_CMD_ERR      (1u << 6)

/* UART 보 레이트 — g0_sweep.c 와 같다 (로그 30 §10.3 B) */
volatile u32 g_uart_baud = 921600u;   /* xsct 가 dow 뒤 con 앞에 덮어쓴다 (print -set) — 지민 PC 는 115200 */
static XUartPs uart;
static void uart_set_baud(void)
{
    XUartPs_CfgInitialize(&uart, XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR), XPAR_XUARTPS_0_BASEADDR);
    XUartPs_SetBaudRate(&uart, g_uart_baud);
}

/* 실행 때 덮어쓰는 값 — 같은 ELF 로 std · deep (S-6 §2, [D55-5]) */
volatile u32 g_wall_n = 8064u;        /* 벽 N. 112 의 배수 — std 8,064 = 112 × 72 · deep 2,064,384 = 112 × 18,432 */
volatile u32 g_base_sector = 0u;      /* 읽기 창 시작 섹터 (수정안 #1). 범위 밖은 RTL 이 CFG_ERR 로 거부한다 (R11) */

/* 클럭 상수 — 75MHz 는 빌드 때 치환 (bathtub_v2_gen.py) */
#define SWEEP_STEPS     2520u          /* 56 × 45 = 1 UI */
#define F_SCLK_HZ       25000000u
#define DPHI_PS_STR     "15.873016"    /* VCO 고정 — 전 사다리 공통 */
#define CEIL_ERR        205u           /* 천장 판정: 읽기당 오류 ≥ 이 값 (BER ≥ 0.1) */
#define RANGE_LO        580u           /* 이력 범위: 덩어리 중심 스텝 */
#define RANGE_HI        760u

/* 스텝 단위 상수 — 두 주파수 공통 (S-6 §2) */
#define BURST_BITS_CFG  2048u
#define BATCH_N         112u           /* 천장 N = 벽 한 묶음 = 쪽 112개 */
#define K_STOP          5u             /* 벽 N 으로 0 오류 K 연속이면 그 방향을 멈춘다 · 안쪽 0 틈 K 이상이면 ⑨ */
#define WALK_CAP        64u            /* 덩어리 경계에서 바깥으로 최대 스텝 — 넘으면 ⑩ */
#define FLOOR_MIN       128u           /* 바닥 최소 — 미만이면 ⑭ */

#define WALL_N_STD      8064u
#define WALL_N_DEEP     2064384u

/* 폴링 안전 한도 — g0_sweep.c 와 같다 */
#define POLL_LIMIT      100000000u

enum { PASS_SCAN, PASS_CEIL, PASS_WALL, PASS_RESCAN };
static const char *const PASS_NAME[] = { "scan", "ceil", "wall", "rescan" };

static uint16_t ei[BATCH_N];
static uint16_t ec[BATCH_N][3];        /* 정렬별 총 오류 e_c */
static uint16_t e1c[BATCH_N][3];       /* 정렬별 정답 1 오류 e1_c */
static uint16_t scan_e[SWEEP_STEPS];   /* 훑기 (N = 1) 결과 — 덩어리 · 천장 판정 */
static uint16_t rescan_e[SWEEP_STEPS];
static uint8_t  is_ceil[SWEEP_STEPS];

static int32_t  pos;                   /* 기대 누적 위상 (INC +1 · DEC −1) */
static uint32_t main_rows;
static uint64_t reads_rows;
static char     flags[64];             /* 런 표시 — ';' 로 잇는다 */

static uint16_t scan_prev;             /* 무반응 검사용 직전 스텝 e_i (N = 1 이라 하나) */
static uint32_t dead_armed;
static uint32_t low_seen;              /* BER < 0.25 스텝 관측 — v1 과 같은 게이트 */

#define NEAR(a, b) ((a) >= (b) ? (a) - (b) <= 6u : (b) - (a) <= 6u)

/* 진단용 PRBS-15 (flash_prbs15.v 와 같은 컨벤션) — line_dead 극성 분류에만 쓴다 */
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

static const char *u64_str(uint64_t v, char buf[21])   /* xil_printf 는 64비트 미지원 */
{
    int i = 20;
    buf[i] = '\0';
    do { buf[--i] = '0' + (char)(v % 10u); v /= 10u; } while (v);
    return &buf[i];
}

static void flag_add(const char *f)
{
    uint32_t n = 0;
    while (flags[n]) n++;
    if (n) flags[n++] = ';';
    while (*f) flags[n++] = *f++;
    flags[n] = '\0';
}

static int poll_status(uint32_t mask, uint32_t want)
{
    for (uint32_t spin = 0; spin < POLL_LIMIT; spin++) {
        if ((Xil_In32(REG_STATUS) & mask) == want)
            return 0;
    }
    return -1;
}

/* END 줄은 한 번의 출력으로 낸다 (수정안 #4 §2.6) */
static void end_sweep(int valid, const char *reason)
{
    char rr[21], mode[16];
    uint32_t n = g_wall_n;
    if (n == WALL_N_STD) {
        mode[0] = 's'; mode[1] = 't'; mode[2] = 'd'; mode[3] = '\0';
    } else if (n == WALL_N_DEEP) {
        mode[0] = 'd'; mode[1] = 'e'; mode[2] = 'e'; mode[3] = 'p'; mode[4] = '\0';
    } else {
        char nb[21];
        const char *s = u64_str(n, nb);
        uint32_t k = 0;
        mode[k++] = 'n';
        while (*s) mode[k++] = *s++;
        mode[k] = '\0';
    }
    xil_printf("#G0 SWEEP END valid=%d reason=%s main_rows=%u reads_rows=%s mode=%s flags=%s\r\n",
               valid, reason, main_rows, u64_str(reads_rows, rr), mode, flags);
    while (1) { /* 스윕 1회 = 부팅 1회. 재실행은 리셋으로 */ }
}

static uint32_t step_of(int32_t p)
{
    int32_t s = p % (int32_t)SWEEP_STEPS;
    return (uint32_t)(s < 0 ? s + (int32_t)SWEEP_STEPS : s);
}

static void phase_move(int dir)
{
    Xil_Out32(REG_CTRL, dir > 0 ? CTRL_PHASE_INC : CTRL_PHASE_DEC);
    if (poll_status(ST_PS_BUSY, 0) != 0)
        end_sweep(0, "ps_busy_stuck");
    pos += dir;
}

/* 지금 스텝에서 target 스텝으로 원형 최단 거리로 옮긴다 — INC · DEC 가 섞인다 */
static void seek(uint32_t target)
{
    uint32_t d = (target + SWEEP_STEPS - step_of(pos)) % SWEEP_STEPS;
    if (d <= SWEEP_STEPS / 2)
        while (d--) phase_move(+1);
    else
        for (d = SWEEP_STEPS - d; d; d--) phase_move(-1);
}

/* START 한 번(n 읽기) + 회수 + R8 ①-⑥ + R 줄. 반환 = ERR_BITS */
static uint32_t measure_batch(uint32_t step, uint32_t n, uint32_t *err_reads, uint64_t *sq_sum)
{
    if ((int32_t)Xil_In32(REG_PHASE_POS) != pos)
        end_sweep(0, "phase_pos_mismatch");         /* 호스트 루프 자체 검사 — 정확 비교 */

    Xil_Out32(REG_N_READS, n);
    Xil_Out32(REG_CTRL, CTRL_MEAS_START);
    /* 거부된 START(R11)는 DONE 없이 CFG_ERR 만 선다 — 한도까지 돌지 않고 바로 끝낸다 */
    uint32_t spin;
    for (spin = 0; spin < POLL_LIMIT; spin++) {
        uint32_t s0 = Xil_In32(REG_STATUS);
        if (s0 & ST_CFG_ERR)
            end_sweep(0, "cfg_err");                /* 무효 ② */
        if (s0 & ST_MEAS_DONE)
            break;
    }
    if (spin == POLL_LIMIT)
        end_sweep(0, "done_stuck");                 /* R10 위반 = 조사 대상 */

    uint32_t st = Xil_In32(REG_STATUS);
    if (st & ST_TIMEOUT)        end_sweep(0, "timeout");      /* 무효 ① */
    if (st & ST_CFG_ERR)        end_sweep(0, "cfg_err");      /* 무효 ② */
    if (!(st & ST_MMCM_LOCKED)) end_sweep(0, "lock_lost");    /* 무효 ③ */

    uint32_t err_bits = Xil_In32(REG_ERR_BITS);
    *err_reads        = Xil_In32(REG_ERR_READS);

    /* e_i · 여섯 값 회수 (R3: 다음 START 전에) + R8 */
    uint32_t sum = 0, nz = 0;
    for (uint32_t i = 0; i < n; i++) {
        Xil_Out32(REG_LOG_ADDR, i);
        uint32_t e = Xil_In32(REG_LOG_DATA) & 0xFFFFu;
        uint32_t w[3] = { Xil_In32(REG_LOG_C0), Xil_In32(REG_LOG_C1), Xil_In32(REG_LOG_C2) };
        int32_t  d[3];
        uint32_t mn = 0xFFFFu;
        for (uint32_t c = 0; c < 3; c++) {
            ec[i][c]  = (uint16_t)(w[c] & 0xFFFFu);
            e1c[i][c] = (uint16_t)(w[c] >> 16);
            if (e1c[i][c] > ec[i][c])
                end_sweep(0, "r8_e1_gt_e");                       /* 무효 ④ — R8 ⑤ */
            if (ec[i][c] < mn) mn = ec[i][c];
            d[c] = (int32_t)ec[i][c] - 2 * (int32_t)e1c[i][c];   /* (받은 1 의 수) − (정답 1 의 수) */
        }
        if (mn != e)
            end_sweep(0, "r8_min_mismatch");                      /* 무효 ④ — R8 ④ */
        for (uint32_t c = 0; c < 3; c++)
            for (uint32_t c2 = c + 1; c2 < 3; c2++) {
                int32_t dd = d[c] - d[c2];
                if ((dd < 0 ? -dd : dd) > (int32_t)(c2 - c))
                    end_sweep(0, "r8_polarity");                  /* 무효 ④ — R8 ⑥ */
            }
        ei[i] = (uint16_t)e;
        sum += e;
        nz  += (e != 0);
        *sq_sum += (uint64_t)e * e;
        if (e > BURST_BITS_CFG)
            end_sweep(0, "r8_ei_gt_b");                           /* 무효 ④ — R8 ③ */
    }
    if (sum != err_bits)   end_sweep(0, "r8_sum_mismatch");       /* 무효 ④ — R8 ① */
    if (nz != *err_reads)  end_sweep(0, "r8_count_mismatch");     /* 무효 ④ — R8 ② */

    for (uint32_t i = 0; i < n; i++) {
        xil_printf("R,%u,%u,%u,%u,%u,%u,%u,%u,%u\r\n", step, i, ei[i],
                   ec[i][0], ec[i][1], ec[i][2], e1c[i][0], e1c[i][1], e1c[i][2]);
        reads_rows++;
    }
    return err_bits;
}

static void print_main(uint32_t step, uint32_t n_reads, uint64_t bits, uint32_t err_reads,
                       uint64_t sq_sum, int pass)
{
    char b1[21], b2[21];
    /* phase_ps = step × Δφ, Δφ = 10⁶/63 fs (g0_sweep.c 와 같다) */
    uint64_t fs = (uint64_t)step * 1000000ull / 63u;
    xil_printf("M,%u,%u.%03u,%u,%u,%s,%u,%s,%u,%s,%s\r\n", step,
               (uint32_t)(fs / 1000u), (uint32_t)(fs % 1000u), n_reads, BURST_BITS_CFG,
               u64_str(bits, b1), err_reads, u64_str(sq_sum, b2), F_SCLK_HZ, DPHI_PS_STR,
               PASS_NAME[pass]);
    main_rows++;
}

/* 한 (pass, 스텝): 묶음 nb 번 × n 읽기 → M 줄 하나. outer 면 묶음마다 접촉 붕괴(⑫)를 본다. 반환 = 스텝 bit_errors */
static uint64_t measure_step(int pass, uint32_t nb, uint32_t n, int outer)
{
    uint32_t step = step_of(pos);
    uint64_t bits = 0, sq = 0;
    uint32_t reads = 0;
    for (uint32_t k = 0; k < nb; k++) {
        uint32_t er;
        uint32_t eb = measure_batch(step, n, &er, &sq);
        bits  += eb;
        reads += er;
        if (outer && eb >= CEIL_ERR * n) {
            /* 바닥이던 자리가 천장 높이 — 벽이 아니라 접촉 붕괴. 받은 묶음까지 행으로 남기고 그 자리에서 끝낸다 */
            print_main(step, (k + 1) * n, bits, reads, sq, pass);
            end_sweep(0, "contact_collapse");                     /* 무효 ⑫ */
        }
    }
    print_main(step, nb * n, bits, reads, sq, pass);
    return bits;
}

/* 훑기 한 바퀴 (N = 1): 스텝 0 → UI 끝. check_dead 면 무반응 검사(⑦) */
static void scan(int pass, uint16_t *e, int check_dead)
{
    seek(0);
    for (uint32_t s = 0; s < SWEEP_STEPS; s++) {
        if (s > 0)
            phase_move(+1);
        e[s] = (uint16_t)measure_step(pass, 1, 1, 0);
        if (!check_dead)
            continue;

        /* 무반응 라인 자가진단 — g0_sweep.c 와 같은 검사, 읽기가 하나라 비교하는 값도 하나다
           (수정안 #4 ⑦). 극성 분류는 그 한 읽기의 쪽(base_sector × 16)으로 한다 */
        if (e[s] < BURST_BITS_CFG / 4u)
            low_seen = 1;
        if (e[s] != 0 && !low_seen) {
            if (dead_armed && e[s] == scan_prev) {
                uint16_t pg = (uint16_t)(g_base_sector * 16u);
                uint32_t on = prbs_ones(pg, BURST_BITS_CFG);
                uint32_t s0 = NEAR(e[s], on);
                uint32_t s1 = NEAR(e[s], BURST_BITS_CFG - on);
                xil_printf("#G0 DIAG line_dead e0=%u ones0=%u page=%u b=%u\r\n",
                           e[s], on, pg, BURST_BITS_CFG);
                if (s0 && !s1)      end_sweep(0, "line_dead_stuck0");
                else if (s1 && !s0) end_sweep(0, "line_dead_stuck1");
                else                end_sweep(0, "line_dead_unknown");
            }
            scan_prev = e[s];
            dead_armed = 1;
        } else
            dead_armed = 0;
    }
}

/* 덩어리 = 가장 긴 원형 0 구간(바닥)의 여집합. 반환: 0 정상 · 1 no_window · 2 no_block · 3 multi_block */
static int find_block(const uint16_t *e, uint32_t *first, uint32_t *len)
{
    uint32_t best = 0, cur = 0, end = 0;
    for (uint32_t i = 0; i < 2 * SWEEP_STEPS; i++) {
        cur = e[i % SWEEP_STEPS] == 0 ? cur + 1 : 0;
        if (cur > best) { best = cur; end = i; }
    }
    if (best == 0)
        return 1;
    if (best >= SWEEP_STEPS)
        return 2;
    *first = (end + 1) % SWEEP_STEPS;
    *len = SWEEP_STEPS - best;
    for (uint32_t k = 0, gap = 0; k < *len; k++) {           /* 안쪽 0 틈 */
        gap = e[(*first + k) % SWEEP_STEPS] == 0 ? gap + 1 : 0;
        if (gap >= K_STOP)
            return 3;
    }
    return 0;
}

/* 천장 양 끝 — 바닥 한가운데(org)를 원점으로 잰 오프셋의 최소 · 최대. 천장이 없으면 0 */
static int ceil_ends(const uint16_t *e, uint32_t org, uint32_t *lo, uint32_t *hi)
{
    int any = 0;
    for (uint32_t s = 0; s < SWEEP_STEPS; s++) {
        if (e[s] < CEIL_ERR)
            continue;
        uint32_t o = (s + SWEEP_STEPS - org) % SWEEP_STEPS;
        if (!any || o < *lo) *lo = o;
        if (!any || o > *hi) *hi = o;
        any = 1;
    }
    return any;
}

/* 벽 바깥 걷기 — dir = −1 왼쪽(스텝 감소) · +1 오른쪽 */
static void walk_out(int dir, uint32_t nb)
{
    uint32_t zeros = 0;
    for (uint32_t k = 1; k <= WALK_CAP; k++) {
        phase_move(dir);
        zeros = measure_step(PASS_WALL, nb, BATCH_N, 1) == 0 ? zeros + 1 : 0;
        if (zeros == K_STOP)
            return;
    }
    end_sweep(0, "wall_cap");                                     /* 무효 ⑩ */
}

int main(void)
{
    uart_set_baud();

    /* 브링업 게이트: 주소 디코드(ID) → MMCM lock (g0_sweep.c 와 같다) */
    uint32_t id = Xil_In32(REG_ID);
    if (id != ID_MAGIC) {
        xil_printf("#G0 ERROR bad ID: 0x%08x (expect 0x%08x)\r\n", id, ID_MAGIC);
        while (1) {}
    }
    if (poll_status(ST_MMCM_LOCKED, ST_MMCM_LOCKED) != 0) {
        xil_printf("#G0 ERROR MMCM not locked\r\n");
        while (1) {}
    }
    if (g_wall_n == 0 || g_wall_n % BATCH_N != 0) {
        xil_printf("#G0 ERROR wall_n=%u is not a multiple of %u\r\n", g_wall_n, BATCH_N);
        while (1) {}
    }

    /* ① */
    if (!(Xil_In32(REG_FEATURE) & FEAT_EDGE))
        end_sweep(0, "no_feature");                               /* 무효 ⑪ */
    if ((int32_t)Xil_In32(REG_PHASE_POS) != 0)
        end_sweep(0, "phase_pos_mismatch");
    pos = 0;

    Xil_Out32(REG_BURST_BITS, BURST_BITS_CFG);
    /* BASE_SECTOR (수정안 #1) — 0 이 아니면 그 레지스터가 있는 빌드(FEATURE bit1)여야 한다. 쓴 값을 되읽어 맞댄다 */
    if (g_base_sector != 0 && !(Xil_In32(REG_FEATURE) & FEAT_BASE_SECTOR))
        end_sweep(0, "no_base_sector");
    Xil_Out32(REG_BASE_SECTOR, g_base_sector);
    uint32_t bs_rb = Xil_In32(REG_BASE_SECTOR);
    if (bs_rb != g_base_sector)
        end_sweep(0, "base_sector_mismatch");

    xil_printf("#G0 SWEEP BEGIN fmt=bathtub2 steps=%u b=%u f_sclk_hz=%u dphi_ps=%s base_sector=%u\r\n",
               SWEEP_STEPS, BURST_BITS_CFG, F_SCLK_HZ, DPHI_PS_STR, bs_rb);   /* 되읽은 값 */
    xil_printf("#G0 COLS_MAIN phase_step,phase_ps,n_reads,b_bits,bit_errors,"
               "reads_with_error,bit_err_sq_sum,f_sclk_hz,dphi_ps,pass\r\n");
    xil_printf("#G0 COLS_READS phase_step,read_idx,err_count,e_c0,e_c1,e_c2,e1_c0,e1_c1,e1_c2\r\n");

    /* ② */
    scan(PASS_SCAN, scan_e, 1);

    /* ③ */
    uint32_t first = 0, len = 0;
    int fb = find_block(scan_e, &first, &len);
    if (fb == 1) end_sweep(0, "no_window");                       /* 무효 ⑧ */
    if (fb == 2) end_sweep(0, "no_block");                        /* 무효 ⑬ */
    if (fb == 3) end_sweep(0, "multi_block");                     /* 무효 ⑨ */
    if (SWEEP_STEPS - len < FLOOR_MIN)
        end_sweep(0, "short_floor");                              /* 무효 ⑭ */
    uint32_t c2 = (2 * first + len - 1) % (2 * SWEEP_STEPS);      /* 중심 × 2 (반 스텝까지) */
    if (c2 < 2 * RANGE_LO || c2 > 2 * RANGE_HI)
        flag_add("block_out_of_range");

    /* ④ 천장 — 한 묶음 */
    for (uint32_t k = 0; k < len; k++) {
        uint32_t s = (first + k) % SWEEP_STEPS;
        is_ceil[s] = scan_e[s] >= CEIL_ERR;
        if (is_ceil[s]) {
            seek(s);
            measure_step(PASS_CEIL, 1, BATCH_N, 0);
        }
    }

    /* ⑤ 벽 — 덩어리 안 나머지, 그리고 경계 바깥으로 */
    uint32_t nb = g_wall_n / BATCH_N;
    for (uint32_t k = 0; k < len; k++) {
        uint32_t s = (first + k) % SWEEP_STEPS;
        if (!is_ceil[s]) {
            seek(s);
            measure_step(PASS_WALL, nb, BATCH_N, 0);
        }
    }
    seek(first);
    walk_out(-1, nb);
    seek((first + len - 1) % SWEEP_STEPS);
    walk_out(+1, nb);

    /* ⑥ 끝 훑기 */
    scan(PASS_RESCAN, rescan_e, 0);
    uint32_t org = (c2 / 2 + SWEEP_STEPS / 2) % SWEEP_STEPS;      /* 바닥 한가운데 — 천장 오프셋의 원점 */
    uint32_t a_lo = 0, a_hi = 0, b_lo = 0, b_hi = 0;
    int a = ceil_ends(scan_e, org, &a_lo, &a_hi);
    int b = ceil_ends(rescan_e, org, &b_lo, &b_hi);
    if (a != b || (a && (a_lo + 1 < b_lo || b_lo + 1 < a_lo || a_hi + 1 < b_hi || b_hi + 1 < a_hi)))
        flag_add("drift");
    uint32_t rf, rl;
    if (find_block(rescan_e, &rf, &rl) == 3)
        flag_add("rescan_multi_block");

    /* 무효 ⑥: 종료 시 CMD_ERR 1회 검사 (g0_sweep.c 와 같다) */
    if (Xil_In32(REG_STATUS) & ST_CMD_ERR)
        end_sweep(0, "cmd_err");
    end_sweep(1, "complete");
    return 0;
}
