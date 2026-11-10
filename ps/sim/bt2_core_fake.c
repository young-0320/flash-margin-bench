/*
 * bt2_core_fake.c — 욕조 v2 펌웨어(bathtub_v2.c)의 호스트 시뮬레이션용 가짜 core + flash.
 *
 * Xil_In32 · Xil_Out32 를 레지스터 맵(계약 §3 + 수정안 #1 · #4)으로 받고, START 마다 읽기별 여섯 값을 만든다.
 * 칩 모형 — 쪽 데이터는 PRBS-15 (시드 {1, page[13:0]}, page = base_sector × 16 + i), 쪽 앞의 선 상태는 1 (BT2_FAKE_IDLE),
 * 쪽 뒤는 다음 쪽 비트. 경계 m(비트 m → m+1)의 전이가 셔터보다 먼저 왔으면 비트 m 의 샘플은 d[m+1], 아니면 d[m].
 * 먼저 왔을 확률은 위상 스텝마다 상승 p_r · 하강 p_f (프로파일 파일). 정렬 c 는 정답 d[j] 를 샘플
 * s[j + c − now] 와 맞댄다 — now 가 「지금 비트」 정렬, now − 1 이 「다음 비트」 (수정안 #4 R14).
 * 비트 단위로 세므로 R8 ④⑤⑥ 이 저절로 성립한다. 읽기마다 전이 1,000개를 다 뽑지 않고 기하 건너뛰기로
 * 바뀐 전이만 뽑는다 (기준 상태 = 방향별로 「전부 안 옴 / 전부 옴」 중 가까운 쪽).
 *
 * 환경변수 (전부 선택):
 *   BT2_FAKE_PROFILE=<file>   첫 줄 `steps <UI 스텝>`, 이후 `<step> <p_r> <p_f> <now>`. 없는 스텝은 0 0 1
 *   BT2_FAKE_RESCAN_PROFILE=<file>  끝 훑기(벽 START 뒤의 첫 N = 1 START 부터)에 쓰는 프로파일 — 표류 · 끝 훑기 덩어리 둘
 *   BT2_FAKE_COLLAPSE_STEP=<s>      N > 1 START 가 그 스텝에서 나면 그때부터 전 위상 p = 0.5 (접촉 붕괴)
 *   BT2_FAKE_STUCK=0|1        MISO 고정 — line_dead
 *   BT2_FAKE_FEATURE=<n>      FEATURE 값 (기본 3)
 *   BT2_FAKE_POS0=<n>         시작 PHASE_POS (기본 0)
 *   BT2_FAKE_PHASE_SKIP=<n>   n 번째 위상 명령을 무시한다 (1부터) — phase_pos_mismatch
 *   BT2_FAKE_BUG=min|e1gt|polarity  R8 ④ · ⑤ · ⑥ 위반 주입
 *   BT2_FAKE_SEED=<n>         난수 씨앗 (기본 1)
 *   BT2_FAKE_IDLE=0|1         쪽 앞의 선 상태 (기본 1). 0 이면 쪽 첫 비트(늘 1) 앞에 쪽 머리 상승이 생긴다 — RTL A2 의 기본
 *   BT2_FAKE_PREAMBLE=1       정렬 0 의 첫 샘플을 합성 프리앰블(= 1 = 쪽 첫 비트)로 둔다 — RTL 처럼 쪽 머리를 가린다
 * START 는 RTL 의 R11 검사(1 ≤ N ≤ 2,048 · 8 ≤ B ≤ 65,528 · B % 8 == 0 · BASE_SECTOR × 16 + N ≤ 32,768)를 따른다 —
 * 어기면 DONE 없이 CFG_ERR 만 선다. BASE_SECTOR 는 RTL 처럼 [10:0] 만 남는다.
 *   BT2_WALL_N · BT2_BASE_SECTOR    펌웨어의 g_wall_n · g_base_sector 를 실행 전에 덮어쓴다 (xsct print -set 흉내)
 */

#define _POSIX_C_SOURCE 200809L
#include "xil_io.h"
#include "xil_printf.h"
#include "xuartps.h"

#include <math.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define B        2048
#define NMAX     2048
#define CORE     0x43C00000UL

extern volatile u32 g_wall_n, g_base_sector;

typedef struct { double pr, pf; int now; } prof_t;

static prof_t *prof, *prof_rescan;
static int steps = 2520;
static int stuck = -1, bug, collapse_step = -1, collapsed, seen_big, rescan, idle = 1, preamble;
static long phase_skip = -1, moves;
static u32 feature = 3, n_reads = 100, burst = 2048, base_sector, log_addr, done, cfg_err, err_bits, err_reads;
static int32_t pos;
static u16 r_e[NMAX], r_ec[NMAX][3], r_e1[NMAX][3];
static uint64_t rng = 1;

/* ── 쪽 ─────────────────────────────────────────────────────────────── */
typedef struct {
    u8  d[B + 4];                  /* d[m] = D(m + 2), m ∈ [−2, B+1] */
    int nr, nf;
    int16_t rise[B + 3], fall[B + 3];
    int base_ok[2][2][3];          /* [rbase][fbase][now] */
    int base_e[2][2][3][3], base_e1[2][2][3][3];
} page_t;
static page_t *pages[32768 + 1];

#define D(pg, m) ((pg)->d[(m) + 2])

static void prbs(u32 page, u8 *out, int n)
{
    u16 lfsr = (u16)(0x4000u | (page & 0x3FFFu));
    for (int k = 0; k < n; k++) {
        out[k] = (lfsr >> 14) & 1u;
        lfsr = (u16)(((lfsr << 1) | (((lfsr >> 14) ^ (lfsr >> 13)) & 1u)) & 0x7FFFu);
    }
}

static page_t *page_get(u32 page)
{
    if (pages[page])
        return pages[page];
    page_t *p = calloc(1, sizeof *p);
    u8 nx[2];
    p->d[0] = p->d[1] = (u8)idle;                   /* 쪽 앞의 선 상태 */
    prbs(page, &p->d[2], B);
    prbs(page + 1, nx, 2);                          /* 쪽 뒤 = 다음 쪽 첫 두 비트 */
    p->d[B + 2] = nx[0];
    p->d[B + 3] = nx[1];
    for (int m = -2; m <= B; m++) {
        if (D(p, m) == D(p, m + 1))
            continue;
        if (D(p, m + 1)) p->rise[p->nr++] = (int16_t)m;
        else             p->fall[p->nf++] = (int16_t)m;
    }
    pages[page] = p;
    return p;
}

/* 기준 상태(상승 전부 rb · 하강 전부 fb 가 먼저 옴)의 정렬별 (e, e1) */
static void baseline(page_t *p, int rb, int fb, int now, int e[3], int e1[3])
{
    if (!p->base_ok[rb][fb][now]) {
        for (int c = 0; c < 3; c++) {
            int ee = 0, ee1 = 0;
            for (int j = 0; j < B; j++) {
                int m = j + c - now;
                int arrived = D(p, m) != D(p, m + 1) && (D(p, m + 1) ? rb : fb);
                int s = arrived ? D(p, m + 1) : D(p, m);
                if (preamble && c == 0 && j == 0)
                    s = 1;                          /* 합성 프리앰블 */
                if (s != D(p, j)) { ee++; ee1 += D(p, j); }
            }
            p->base_e[rb][fb][now][c] = ee;
            p->base_e1[rb][fb][now][c] = ee1;
        }
        p->base_ok[rb][fb][now] = 1;
    }
    memcpy(e, p->base_e[rb][fb][now], sizeof(int) * 3);
    memcpy(e1, p->base_e1[rb][fb][now], sizeof(int) * 3);
}

static double uniform(void)                         /* (0, 1) — xorshift64* */
{
    rng ^= rng >> 12; rng ^= rng << 25; rng ^= rng >> 27;
    return ((double)((rng * 2685821657736338717ULL) >> 11) + 0.5) * (1.0 / 9007199254740992.0);
}

/* 경계 m 의 도착 상태를 기준에서 뒤집는다 — 샘플 s[m] 이 d[m] ↔ d[m+1] */
static void toggle(page_t *p, int m, int base, int now, int e[3], int e1[3])
{
    int s_old = base ? D(p, m + 1) : D(p, m);
    for (int c = 0; c < 3; c++) {
        int j = m - c + now;
        if (j < 0 || j >= B || (preamble && c == 0 && j == 0))
            continue;
        int dlt = s_old != D(p, j) ? -1 : 1;
        e[c] += dlt;
        if (D(p, j)) e1[c] += dlt;
    }
}

static void sample(page_t *p, const int16_t *list, int n, double prob, int base, int now, int e[3], int e1[3])
{
    double q = base ? 1.0 - prob : prob;            /* 기준에서 뒤집힐 확률 (≤ 0.5) */
    if (q <= 0.0)
        return;
    double lq = log1p(-q);
    for (double idx = 0;; idx++) {
        idx += floor(log(uniform()) / lq);
        if (idx >= n)
            return;
        toggle(p, list[(int)idx], base, now, e, e1);
    }
}

static void read_one(u32 page, prof_t pr, int e[3], int e1[3])
{
    page_t *p = page_get(page);
    if (stuck >= 0) {                               /* MISO 고정 — 정렬과 무관하게 같은 창 */
        int ee = 0, ee1 = 0;
        for (int j = 0; j < B; j++)
            if (D(p, j) != stuck) { ee++; ee1 += D(p, j); }
        for (int c = 0; c < 3; c++) { e[c] = ee; e1[c] = ee1; }
        return;
    }
    int rb = pr.pr > 0.5, fb = pr.pf > 0.5;
    baseline(p, rb, fb, pr.now, e, e1);
    sample(p, p->rise, p->nr, pr.pr, rb, pr.now, e, e1);
    sample(p, p->fall, p->nf, pr.pf, fb, pr.now, e, e1);
}

static void start(void)
{
    int step = (int)(((pos % steps) + steps) % steps);
    if (n_reads > 1) seen_big = 1;
    else if (seen_big) rescan = 1;
    if (n_reads > 1 && step == collapse_step) collapsed = 1;
    prof_t pr = { 0, 0, 1 };
    prof_t *tab = rescan && prof_rescan ? prof_rescan : prof;
    if (tab) pr = tab[step];
    if (collapsed) { pr.pr = pr.pf = 0.5; }

    err_bits = err_reads = 0;
    for (u32 i = 0; i < n_reads && i < NMAX; i++) {
        int e[3], e1[3];
        read_one(base_sector * 16u + i, pr, e, e1);
        int mn = e[0] < e[1] ? e[0] : e[1];
        if (e[2] < mn) mn = e[2];
        if (bug == 1 && mn > 0) mn++;               /* R8 ④ */
        if (bug == 2) e1[0] = e[0] + 1;             /* R8 ⑤ */
        if (bug == 3) e1[0] = e[0] - e1[0];         /* R8 ⑥ — 정렬 0 만 정답 0 · 1 을 뒤바꿔 센다 */
        r_e[i] = (u16)mn;
        for (int c = 0; c < 3; c++) { r_ec[i][c] = (u16)e[c]; r_e1[i][c] = (u16)e1[c]; }
        err_bits += (u32)mn;
        err_reads += mn != 0;
    }
    done = 1;
}

/* ── 레지스터 ───────────────────────────────────────────────────────── */
u32 Xil_In32(UINTPTR a)
{
    switch (a - CORE) {
    case 0x00: return 0x4D420100u;
    case 0x08: return (1u << 3) | (done ? 1u << 1 : 0) | (cfg_err ? 1u << 5 : 0);
    case 0x0C: return n_reads;
    case 0x10: return burst;
    case 0x14: return (u32)pos;
    case 0x18: return err_bits;
    case 0x1C: return err_reads;
    case 0x20: return log_addr;
    case 0x24: return r_e[log_addr % NMAX];
    case 0x28: return base_sector;
    case 0x2C: case 0x30: case 0x34: {
        int c = (int)((a - CORE - 0x2C) / 4);
        return ((u32)r_e1[log_addr % NMAX][c] << 16) | r_ec[log_addr % NMAX][c];
    }
    case 0x38: return feature;
    }
    return 0;
}

void Xil_Out32(UINTPTR a, u32 v)
{
    switch (a - CORE) {
    case 0x04:
        if (v == 1u) {
            done = 0;
            cfg_err = !(n_reads >= 1 && n_reads <= 2048 && burst >= 8 && burst <= 65528 && burst % 8 == 0 &&
                        base_sector * 16u + n_reads <= 32768u);  /* R11 — 거부면 DONE 없이 CFG_ERR */
            if (!cfg_err) start();
            break;
        }
        if (v == 2u || v == 4u) {
            if (++moves == phase_skip) break;       /* 이 명령을 놓친다 */
            pos += v == 2u ? 1 : -1;
        }
        break;
    case 0x0C: n_reads = v; break;
    case 0x10: burst = v; break;
    case 0x20: log_addr = v; break;
    case 0x28: base_sector = v & 0x7FFu; break;
    }
}

void xil_printf(const char *fmt, ...)
{
    va_list ap;
    va_start(ap, fmt);
    vprintf(fmt, ap);
    va_end(ap);
    if (strstr(fmt, "SWEEP END") || strstr(fmt, "#G0 ERROR")) {
        fflush(stdout);
        exit(0);                                    /* 보드는 while(1) 로 선다 — 여기서는 프로세스를 끝낸다 */
    }
}

XUartPs_Config *XUartPs_LookupConfig(u32 base)
{
    static XUartPs_Config c;
    c.BaseAddress = base;
    return &c;
}
int XUartPs_CfgInitialize(XUartPs *p, XUartPs_Config *c, u32 base) { (void)p; (void)c; (void)base; return 0; }
int XUartPs_SetBaudRate(XUartPs *p, u32 baud) { (void)p; (void)baud; return 0; }

/* ── 설정 ───────────────────────────────────────────────────────────── */
static prof_t *load_profile(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(2); }
    if (fscanf(f, " steps %d", &steps) != 1 || steps <= 0) { fprintf(stderr, "%s: 첫 줄 `steps <n>`\n", path); exit(2); }
    prof_t *t = calloc((size_t)steps, sizeof *t);
    for (int s = 0; s < steps; s++) t[s].now = 1;
    int s, now;
    double a, b;
    while (fscanf(f, " %d %lf %lf %d", &s, &a, &b, &now) == 4) {
        if (s < 0 || s >= steps || now < 1 || now > 2) { fprintf(stderr, "%s: 잘못된 줄 step=%d now=%d\n", path, s, now); exit(2); }
        t[s].pr = a; t[s].pf = b; t[s].now = now;
    }
    fclose(f);
    return t;
}

__attribute__((constructor)) static void fake_init(void)
{
    const char *v;
    setvbuf(stdout, NULL, _IOFBF, 1 << 16);
    if ((v = getenv("BT2_FAKE_PROFILE"))) prof = load_profile(v);
    if ((v = getenv("BT2_FAKE_RESCAN_PROFILE"))) prof_rescan = load_profile(v);
    if ((v = getenv("BT2_FAKE_COLLAPSE_STEP"))) collapse_step = atoi(v);
    if ((v = getenv("BT2_FAKE_STUCK"))) stuck = atoi(v);
    if ((v = getenv("BT2_FAKE_FEATURE"))) feature = (u32)strtoul(v, NULL, 0);
    if ((v = getenv("BT2_FAKE_POS0"))) pos = atoi(v);
    if ((v = getenv("BT2_FAKE_PHASE_SKIP"))) phase_skip = atol(v);
    if ((v = getenv("BT2_FAKE_SEED"))) rng = strtoull(v, NULL, 0) | 1u;
    if ((v = getenv("BT2_FAKE_IDLE"))) idle = atoi(v) != 0;
    if ((v = getenv("BT2_FAKE_PREAMBLE"))) preamble = atoi(v) != 0;
    if ((v = getenv("BT2_FAKE_BUG")))
        bug = !strcmp(v, "min") ? 1 : !strcmp(v, "e1gt") ? 2 : !strcmp(v, "polarity") ? 3 : 0;
    if ((v = getenv("BT2_WALL_N"))) g_wall_n = (u32)strtoul(v, NULL, 0);
    if ((v = getenv("BT2_BASE_SECTOR"))) g_base_sector = (u32)strtoul(v, NULL, 0);
}
