/*
 * flash_wear.c — P/E 마모 엔진 (PS C, 무상태)
 *
 * 정본: docs/interface/pe_engine.md §2 (경계 10개) · docs/spec/s4.blackbox_tb.md §4·§5.2 (거부 12종 ·
 * 명령/응답/행 문법) · docs/spec/s1.wear_bench_spec.md §6~§10 (루프·무결성·tally·로그·중단).
 * 기본값이 비어 있던 자리의 결정은 docs/log/young/45 이다.
 *
 * 구조: 파서·상태기계·루프·행 생성이 전부 이 파일이고, 플랫폼은 flash_io.h(SPI 배관) 와
 * wear_plat.h(UART 송수신·시계) 둘만 부른다. 같은 소스가 Zynq(wear_plat_zynq.c) 와 호스트
 * 시뮬레이션(ps/sim/) 에서 같은 TB(host/tests/) 로 채점된다.
 *
 * 절대 규칙 — START 가 받은 [base, base+n_sectors) 밖은 한 번도 지우지 않는다. 예외는 tally
 * 섹터(512·1,536) 의 1바이트 쓰기와, idle 에서 칩 UID 를 되받아야만 받는 TALLY_ERASE(S-1 §8.1 의
 * 실험 개시 소거) 뿐이다. 명령은 체크섬 → req → 인자 범위 → 상태 → (tally 읽기 뒤)
 * E_DIRTY/E_CYCLE 을 전부 통과한 뒤에만 플래시에 P/E 를 낸다. 거부는 거부로 끝난다.
 *
 * 빌드: vitis -s ps/scripts/build_flash_wear.py (Zynq) · ps/sim/build_sim.sh (호스트).
 * 빌드 스크립트가 wear_build.h(WEAR_GIT_REV) 를 생성한다 — 하드코딩하지 않는다.
 */

#include "flash_io.h"
#include "wear_plat.h"
#include "wear_build.h"                 /* WEAR_GIT_REV "<short hash>" — 생성 파일 */

#include <ctype.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#ifndef WEAR_SPI_PRESCALE
#define WEAR_SPI_PRESCALE 64u           /* 기본 = JEDEC 검증치. 빌드 define 으로 16·8 (실측 뒤 사람이 고른다, [U44-7]) */
#endif

/* ── 칩·배치 상수 (S-1 §1·§2·§8.1) ─────────────────────────────────────── */
#define PAGE_BYTES      256u
#define SECTOR_PAGES    16u
#define SECTOR_BYTES    (PAGE_BYTES * SECTOR_PAGES)
#define CHIP_SECTORS    2048u
#define TALLY_SECTOR_A  512u
#define TALLY_SECTOR_B  1536u
#define TALLY_BYTES     4096u
#define TALLY_STRIDE    100u
#define TALLY_CAP       (TALLY_BYTES * TALLY_STRIDE)        /* 409,600 사이클 */
#define CHECK_PERIOD    100u            /* §7 기본 검사 주기 */
#define DENSE_PERIOD    10u             /* §7 조밀화 — blank check·B 행에만, tally 는 항상 100 */
#define DEFECT_STOP     4588u           /* §10 정지 문턱. 46·459 는 호스트가 B 행에서 판정 */
#define ADDR_MAX        64u             /* §7 결함 주소 최대 64개 + 총 개수 */
#define WIP_TIMEOUT_US  2000000ULL      /* §10 WIP 미해제 2초 (잠정) — 시간 기준, 반복 상한 아님 */

/* 보호 범위 — 엔진 상수. 배치가 바뀌면 ELF 재빌드 ([D44-2]) */
static const struct { u32 lo, hi; } CTRL_RANGES[] = { { 7u, 13u }, { 2041u, 2047u } };

/* W25Q64JV 명령 */
#define CMD_WREN    0x06
#define CMD_WRDI    0x04
#define CMD_RDSR1   0x05
#define CMD_SE      0x20
#define CMD_PP      0x02
#define CMD_READ    0x03
#define SR1_BUSY    0x01u
#define SR1_WEL     0x02u
#define SR1_BP      0x1Cu               /* BP0..BP2 — 서 있으면 쓰기가 막힌다 */

/* ── 문자열 ──────────────────────────────────────────────────────────────── */
#define LINE_MAX    2048u               /* B 행 최대 ≈ 1,700 (주소 64개 × 2벌) */
#define RX_MAX      256u                /* START 행 ≈ 110 */
#define ROW_PREFIX  "#WEAR "
#define CMD_PREFIX  "WEAR "

typedef enum { ST_IDLE, ST_RUNNING, ST_CHECKPOINT_DUE, ST_RECOVERING, ST_HALTED, ST_ERROR } state_t;
static const char *STATE_NAME[] = { "idle", "running", "checkpoint_due", "recovering", "halted", "error" };

/* ── 엔진 상태 (전부 휘발 — 리셋마다 0) ─────────────────────────────────── */
static state_t  g_state = ST_IDLE;
static u32      g_base, g_n, g_pattern = 0x00u;     /* pattern 기본 0x00 — START 전 BLANK 의 대조값 */
static u32      g_cycle, g_delta_left, g_session;
static int      g_defect_seen;
static char     g_last_reject[20];
static int      g_have_req; static u32 g_last_req;
static int      g_halt_pending;
static u8       g_uid[UID_LEN];
static u32      g_tally_idx[2];                      /* 다음 슬롯 — START 에서 읽는다 (§3 #7) */
static struct { int valid; u32 base, n, resid; } g_last_bc;   /* recovering 이 드는 마지막 blank check */

static u8   tx[PAGE_BYTES + 4], rx[PAGE_BYTES + 4];
static u32  t_prog_us[CHIP_SECTORS], t_erase_us[CHIP_SECTORS];  /* 섹터별 WIP 합 — A 행은 ④ 뒤에 낸다 */
static char line[LINE_MAX]; static u32 line_len, line_sum_from; static int line_overflow;
static char rxbuf[RX_MAX]; static u32 rxlen; static int rx_overflow;

/* ── 행 만들기: 버퍼에 쌓고 체크섬을 붙여 plat_puts ────────────────────── */
static void ln_begin(const char *prefix, u32 sum_from)
{
    line_len = 0; line_overflow = 0;
    line[0] = 0;
    while (*prefix) line[line_len++] = *prefix++;
    line[line_len] = 0;
    line_sum_from = sum_from;
}

static void ap(const char *fmt, ...)
{
    va_list va; va_start(va, fmt);
    int n = vsnprintf(line + line_len, LINE_MAX - line_len, fmt, va);
    va_end(va);
    if (n < 0 || (u32)n >= LINE_MAX - line_len) { line_overflow = 1; line_len = LINE_MAX - 1; }
    else line_len += (u32)n;
}

static void ap_u64(u64 v)                            /* newlib-nano 의 %llu 를 믿지 않는다 */
{
    char buf[21]; int i = 20; buf[i] = 0;
    do { buf[--i] = (char)('0' + (v % 10u)); v /= 10u; } while (v);
    ap("%s", buf + i);
}

static void ln_end(void)
{
    u32 sum = 0;
    for (u32 i = line_sum_from; i < line_len; i++) sum += (u8)line[i];
    ap(" sum=%04x\n", sum & 0xFFFFu);
    if (line_overflow) return;                       /* 잘린 행은 내보내지 않는다 — 체크섬이 어차피 틀린다 */
    plat_puts(line);
}

static void row_begin(char kind)                     /* 체크섬은 "#WEAR " 다음부터 */
{
    ln_begin(ROW_PREFIX, (u32)strlen(ROW_PREFIX));
    ap("%c", kind);
}

static void ok_begin(u32 req)                        /* 응답은 접두가 없다 — "OK" 부터 ([D45-1]) */
{
    ln_begin("", 0);
    ap("OK req=%u", req);
}

static void reject(u32 req, const char *code)
{
    ln_begin("", 0);
    ap("REJECT req=%u code=%s", req, code);
    ln_end();
    strncpy(g_last_reject, code, sizeof g_last_reject - 1);
}

/* ── 플래시 원시 동작 (flash_io 배관 위) ───────────────────────────────── */
static int xfer(u8 *t, u8 *r, u32 len)
{
    for (int k = 0; k < 3; k++)                      /* 전송만 3회 ([D41-18]) — 플래시 동작 재시도는 0회 */
        if (!flash_xfer(t, r, len)) return 0;
    return -1;
}

static void addr3(u8 *p, u32 addr) { p[0] = (u8)(addr >> 16); p[1] = (u8)(addr >> 8); p[2] = (u8)addr; }

static int wren(void) { tx[0] = CMD_WREN; return xfer(tx, rx, 1); }
static int wrdi(void) { tx[0] = CMD_WRDI; return xfer(tx, rx, 1); }

static int rdsr1(u8 *sr)
{
    tx[0] = CMD_RDSR1; tx[1] = 0;
    if (xfer(tx, rx, 2)) return -1;
    *sr = rx[1];
    return 0;
}

/* WIP 해제까지의 시간(µs). 0=해제, 1=타임아웃(§10 2초), -1=전송 실패 */
static int wait_wip(u64 *dur_us)
{
    u64 t0 = plat_now_us();
    for (;;) {
        u8 sr;
        if (rdsr1(&sr)) { *dur_us = plat_now_us() - t0; return -1; }
        *dur_us = plat_now_us() - t0;
        if (!(sr & SR1_BUSY)) return 0;
        if (*dur_us > WIP_TIMEOUT_US) return 1;
    }
}

static int read_page(u32 page)                       /* rx[4..259] */
{
    tx[0] = CMD_READ; addr3(&tx[1], page * PAGE_BYTES);
    return xfer(tx, rx, PAGE_BYTES + 4);
}

static int sector_erase(u32 sector, u64 *t_us)       /* 0 / 1 타임아웃 / -1 전송 */
{
    if (wren()) return -1;
    tx[0] = CMD_SE; addr3(&tx[1], sector * SECTOR_BYTES);
    if (xfer(tx, rx, 4)) return -1;
    return wait_wip(t_us);
}

static int page_program(u32 page, u8 pattern, u64 *t_us)
{
    if (wren()) return -1;
    tx[0] = CMD_PP; addr3(&tx[1], page * PAGE_BYTES);
    memset(tx + 4, pattern, PAGE_BYTES);
    if (xfer(tx, rx, PAGE_BYTES + 4)) return -1;
    return wait_wip(t_us);
}

/* ── 읽어서 세기 (§7) — 부를 때 실제로 읽는다, 캐시 없음 ───────────────── */
typedef struct {
    u32 bits, addr_count, worst_page, worst_bits;
    struct { u16 p; u8 b, k; } addr[ADDR_MAX];
} scan_t;

static void scan_reset(scan_t *s) { memset(s, 0, sizeof *s); }

static void scan_byte(scan_t *s, u32 page_rel, u32 byte, u8 z, u32 *page_bits)
{
    if (!z) return;
    u32 c = (u32)__builtin_popcount(z);
    s->bits += c; *page_bits += c;
    for (u32 k = 0; k < 8u; k++) {
        if (!(z & (1u << k))) continue;
        if (s->addr_count < ADDR_MAX) {
            s->addr[s->addr_count].p = (u16)page_rel;
            s->addr[s->addr_count].b = (u8)byte;
            s->addr[s->addr_count].k = (u8)k;
        }
        s->addr_count++;
    }
}

/* [base, base+n) 을 한 번 읽어 ref_e(0xFF) 대비 잔류와 ref_p(pattern) 대비 불일치를 같이 센다.
   sp 가 NULL 이면 잔류만. 페이지 번호는 base 기준 상대값 (§3 #9). 0=성공, -1=전송 실패 */
static int scan_range(u32 base, u32 n, scan_t *se, u8 ref_e, scan_t *sp, u8 ref_p)
{
    scan_reset(se); if (sp) scan_reset(sp);
    u32 npages = n * SECTOR_PAGES;
    for (u32 pr = 0; pr < npages; pr++) {
        if (read_page(base * SECTOR_PAGES + pr)) return -1;
        u32 pb_e = 0, pb_p = 0;
        for (u32 i = 0; i < PAGE_BYTES; i++) {
            u8 v = rx[4 + i];
            scan_byte(se, pr, i, (u8)(v ^ ref_e), &pb_e);
            if (sp) scan_byte(sp, pr, i, (u8)(v ^ ref_p), &pb_p);
        }
        if (pb_e > se->worst_bits) { se->worst_bits = pb_e; se->worst_page = pr; }
        if (sp && pb_p > sp->worst_bits) { sp->worst_bits = pb_p; sp->worst_page = pr; }
    }
    return 0;
}

static void ap_scan(const char *pfx, const scan_t *s)   /* <pfx>addr_count= <pfx>addrs= <pfx>worst_page= <pfx>worst_bits= */
{
    ap(" %saddr_count=%u %saddrs=", pfx, s->addr_count, pfx);
    u32 shown = s->addr_count < ADDR_MAX ? s->addr_count : ADDR_MAX;
    for (u32 i = 0; i < shown; i++)
        ap("%s%u:%u:%u", i ? ";" : "", s->addr[i].p, s->addr[i].b, s->addr[i].k);
    ap(" %sworst_page=%u %sworst_bits=%u", pfx, s->worst_page, pfx, s->worst_bits);
}

/* ── tally (§8) ──────────────────────────────────────────────────────────── */
typedef struct { u32 count; int marked; int next_byte; } tally_t;   /* next_byte -1 = 다 썼다 */

static int tally_read_copy(u32 copy, tally_t *t)
{
    u32 sector = copy ? TALLY_SECTOR_B : TALLY_SECTOR_A;
    t->count = 0; t->marked = 0; t->next_byte = -1;
    for (u32 pg = 0; pg < SECTOR_PAGES; pg++) {
        if (read_page(sector * SECTOR_PAGES + pg)) return -1;
        for (u32 i = 0; i < PAGE_BYTES; i++) {
            u8 v = rx[4 + i];
            if (v == 0x00u) t->count++;
            if (v != 0xFFu) t->marked = 1;
        }
    }
    if (t->count < TALLY_BYTES) {                    /* 다음 슬롯의 값 — 0xFF 면 미기록, 그 외는 쓰다 만 것 */
        u32 idx = t->count;
        if (read_page(sector * SECTOR_PAGES + idx / PAGE_BYTES)) return -1;
        t->next_byte = rx[4 + idx % PAGE_BYTES];
    }
    return 0;
}

static int tally_write(u32 copy, u64 *t_us)          /* 다음 슬롯에 0x00 한 바이트 — 재기록 아님 (§8.1) */
{
    u32 sector = copy ? TALLY_SECTOR_B : TALLY_SECTOR_A;
    u32 idx = g_tally_idx[copy];
    if (idx >= TALLY_BYTES) return -1;               /* E_CAP 이 막았어야 한다 */
    if (wren()) return -1;
    tx[0] = CMD_PP; addr3(&tx[1], sector * SECTOR_BYTES + idx); tx[4] = 0x00u;
    if (xfer(tx, rx, 5)) return -1;
    int rc = wait_wip(t_us);
    if (rc == 0) g_tally_idx[copy]++;
    return rc;
}

/* 비파괴 쓰기 가능 시험 — WREN 뒤 WEL 이 서고 BP 가 0 이면 1. WRDI 로 되돌린다 */
static int write_ok(void)
{
    u8 sr;
    if (wren() || rdsr1(&sr)) return 0;
    int ok = (sr & SR1_WEL) && !(sr & SR1_BP);
    wrdi();
    return ok;
}

/* ── 행 출력 ─────────────────────────────────────────────────────────────── */
static void emit_header(u32 cycle, u32 delta)
{
    row_begin('H');
    ap(" session=%u chip_id=", g_session);
    for (u32 i = 0; i < UID_LEN; i++) ap("%02X", g_uid[i]);
    ap(" git_rev=%s base_sector=%u n_sectors=%u pattern=0x%02x cycle=%u delta=%u ts=",
       WEAR_GIT_REV, g_base, g_n, g_pattern, cycle, delta);
    ap_u64(plat_now_us());
    ln_end();
}

static void emit_a(u32 sector, u32 t_erase, u32 t_prog)
{
    row_begin('A');
    ap(" cycle=%u sector=%u t_erase_us=%u t_program_us=%u ts=", g_cycle, sector, t_erase, t_prog);
    ap_u64(plat_now_us());
    ln_end();
}

static void emit_b(const scan_t *p, const scan_t *e, int uid_ok)
{
    row_begin('B');
    ap(" cycle=%u erase_residual_bits=%u program_fail_bits=%u", g_cycle, e->bits, p->bits);
    ap_scan("p_", p);
    ap_scan("e_", e);
    ap(" die_temp_mc= uid_ok=%d ts=", uid_ok);     /* die_temp_mc — XADC 미구현, 빈 값 */
    ap_u64(plat_now_us());
    ln_end();
}

/* 사건 행 — 쓰지 않는 필드는 빈 값. has_* 로 빈 값을 가른다 */
static void emit_r(const char *kind, int has_sector, u32 sector, const char *op,
                   int has_t, u64 t_us, int ok, int has_before, u32 before, int has_after, u32 after)
{
    row_begin('R');
    ap(" kind=%s cycle=%u sector=", kind, g_cycle);
    if (has_sector) ap("%u", sector);
    ap(" op=%s t_us=", op);
    if (has_t) ap_u64(t_us);
    ap(" ok=%d resid_before=", ok);
    if (has_before) ap("%u", before);
    ap(" resid_after=");
    if (has_after) ap("%u", after);
    ap(" ts=");
    ap_u64(plat_now_us());
    ln_end();
}

/* 정지 — R 행 1건 + error. 자동 재시도 없음 (§10) */
static void stop_error(const char *kind, u32 sector, const char *op, int has_t, u64 t_us, int has_bits, u32 bits)
{
    emit_r(kind, 1, sector, op, has_t, t_us, 0, has_bits, bits, 0, 0);
    g_state = ST_ERROR;
}

/* ── 마모 루프 1사이클 (S-1 §6 ①~⑥) ─────────────────────────────────────── */
static void run_cycle(void)
{
    u32 target = g_cycle + 1u;
    u32 period = g_defect_seen ? DENSE_PERIOD : CHECK_PERIOD;
    int checking = (target % period) == 0u;
    int tally_due = (target % TALLY_STRIDE) == 0u;     /* 조밀화와 무관하게 항상 100 단위 (§3 #8) */
    static scan_t pscan, escan;
    u64 t;

    for (u32 s = 0; s < g_n; s++) {                   /* ① 프로그램 112페이지 — 섹터별 WIP 합 */
        t_prog_us[s] = 0;
        for (u32 pg = 0; pg < SECTOR_PAGES; pg++) {
            int rc = page_program((g_base + s) * SECTOR_PAGES + pg, (u8)g_pattern, &t);
            if (rc < 0) { stop_error("program_fail", g_base + s, "program", 0, 0, 0, 0); return; }
            if (rc > 0) { stop_error("wip_timeout", g_base + s, "program", 1, t, 0, 0); return; }
            t_prog_us[s] += (u32)t;
        }
    }
    if (checking && scan_range(g_base, g_n, &escan, 0xFFu, &pscan, (u8)g_pattern)) {   /* ①' 프로그램 직후 — t_* 에 넣지 않는다 */
        stop_error("program_fail", g_base, "program", 0, 0, 0, 0); return;
    }
    for (u32 s = 0; s < g_n; s++) {                   /* ② 7섹터 소거 */
        int rc = sector_erase(g_base + s, &t);
        if (rc < 0) { stop_error("erase_fail", g_base + s, "erase", 0, 0, 0, 0); return; }
        if (rc > 0) { stop_error("wip_timeout", g_base + s, "erase", 1, t, 0, 0); return; }
        t_erase_us[s] = (u32)t;
    }
    g_cycle = target;                                 /* ③ 카운터 — 마모 루프만 센다 */
    g_delta_left--;

    int uid_ok = 1;
    if (checking) {                                   /* ④ 검사 주기 */
        if (scan_range(g_base, g_n, &escan, 0xFFu, NULL, 0)) {   /* 소거 직후 잔류 */
            stop_error("erase_fail", g_base, "erase", 0, 0, 0, 0); return;
        }
        if (pscan.bits || escan.bits) g_defect_seen = 1;
        u8 uid[UID_LEN];                              /* UID 재확인 — 3회 일치 */
        uid_ok = flash_read_uid(uid) == 0 && memcmp(uid, g_uid, UID_LEN) == 0;
    }
    if (tally_due) {                                  /* ④ tally 2벌 — A 행보다 먼저 (§8.3 의 창) */
        for (u32 c = 0; c < 2u; c++) {
            int rc = tally_write(c, &t);
            if (rc < 0) { stop_error("program_fail", c ? TALLY_SECTOR_B : TALLY_SECTOR_A, "program", 0, 0, 0, 0); return; }
            if (rc > 0) { stop_error("wip_timeout", c ? TALLY_SECTOR_B : TALLY_SECTOR_A, "program", 1, t, 0, 0); return; }
        }
    }
    for (u32 s = 0; s < g_n; s++)                     /* ⑥ A 행 n개 — 매 사이클 실시간 */
        emit_a(g_base + s, t_erase_us[s], t_prog_us[s]);
    if (checking) {
        emit_b(&pscan, &escan, uid_ok);               /* 검사 사이클당 정확히 1행 */
        if (pscan.bits > DEFECT_STOP)      stop_error("program_fail", g_base, "program", 0, 0, 1, pscan.bits);
        else if (escan.bits > DEFECT_STOP) stop_error("erase_fail", g_base, "erase", 0, 0, 1, escan.bits);
        else if (!uid_ok)                  stop_error("uid_mismatch", g_base, "", 0, 0, 0, 0);
    }
}

/* ── 명령 파싱 ───────────────────────────────────────────────────────────── */
#define TOK_MAX 16u
static char *tok[TOK_MAX]; static u32 ntok;

static const char *arg(const char *key)              /* "key=value" 토큰의 value, 없으면 NULL */
{
    size_t kl = strlen(key);
    for (u32 i = 1; i < ntok; i++)
        if (!strncmp(tok[i], key, kl) && tok[i][kl] == '=') return tok[i] + kl + 1;
    return NULL;
}

static int arg_u32(const char *key, u32 *out)        /* 0=있음, -1=없거나 숫자 아님 */
{
    const char *v = arg(key);
    if (!v || !*v) return -1;
    char *end; unsigned long x = strtoul(v, &end, 0);
    if (*end || x > 0xFFFFFFFFul) return -1;
    *out = (u32)x;
    return 0;
}

static int overlaps(u32 base, u32 n, u32 lo, u32 hi) { return base <= hi && lo < base + n; }

/* START·REERASE 공통 인자 검사 — §3 #2 의 순서. 0=통과, 아니면 reject 를 보냈다 */
static int check_range(u32 req, u32 base, u32 n)
{
    if (n == 0u) { reject(req, "E_NSECT0"); return -1; }
    if (base > CHIP_SECTORS || n > CHIP_SECTORS - base) { reject(req, "E_RANGE"); return -1; }
    if (overlaps(base, n, TALLY_SECTOR_A, TALLY_SECTOR_A) || overlaps(base, n, TALLY_SECTOR_B, TALLY_SECTOR_B)) {
        reject(req, "E_TALLY_OVERLAP"); return -1;
    }
    for (u32 i = 0; i < sizeof CTRL_RANGES / sizeof CTRL_RANGES[0]; i++)
        if (overlaps(base, n, CTRL_RANGES[i].lo, CTRL_RANGES[i].hi)) { reject(req, "E_CTRL_OVERLAP"); return -1; }
    return 0;
}

static void cmd_start(u32 req)
{
    u32 base, n, pattern, cycle, delta, session;
    if (arg_u32("base", &base) || arg_u32("n_sectors", &n) || arg_u32("pattern", &pattern) ||
        arg_u32("cycle", &cycle) || arg_u32("delta", &delta) || arg_u32("session", &session) ||
        pattern > 0xFFu) { reject(req, "E_RANGE"); return; }
    if (check_range(req, base, n)) return;
    if ((u64)cycle + delta > TALLY_CAP) { reject(req, "E_CAP"); return; }
    if (g_state == ST_RUNNING) { reject(req, "E_RUNNING"); return; }
    tally_t ta, tb;                                   /* tally 읽기 — 그 뒤에만 E_DIRTY/E_CYCLE */
    if (tally_read_copy(0, &ta) || tally_read_copy(1, &tb)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    if (cycle == 0u && (ta.marked || tb.marked)) { reject(req, "E_DIRTY"); return; }
    u32 t = (ta.count > tb.count ? ta.count : tb.count) * TALLY_STRIDE;   /* §3 #6 */
    if (cycle < t || cycle - t >= TALLY_STRIDE) { reject(req, "E_CYCLE"); return; }

    g_base = base; g_n = n; g_pattern = pattern; g_cycle = cycle; g_delta_left = delta; g_session = session;
    g_tally_idx[0] = ta.count; g_tally_idx[1] = tb.count;
    g_halt_pending = 0; g_last_bc.valid = 0;
    g_state = delta ? ST_RUNNING : ST_CHECKPOINT_DUE;   /* §3 #13 — delta=0 은 H 행만 내고 즉시 checkpoint_due */
    ok_begin(req);                                    /* OK 는 검사 통과 직후·루프 시작 전 (§3 #16) */
    ap(" base=%u n_sectors=%u pattern=0x%02x cycle=%u delta=%u session=%u", base, n, pattern, cycle, delta, session);
    ln_end();
    emit_header(cycle, delta);
}

static void cmd_status(u32 req)
{
    ok_begin(req);
    ap(" cycle=%u state=%s defect_seen=%d last_reject=%s", g_cycle, STATE_NAME[g_state], g_defect_seen, g_last_reject);
    ln_end();
}

static void cmd_resume(u32 req)
{
    if (g_state == ST_RUNNING) { reject(req, "E_STATE"); return; }
    tally_t ta, tb;
    if (tally_read_copy(0, &ta) || tally_read_copy(1, &tb)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    int wok = write_ok();
    g_state = ST_RECOVERING; g_last_bc.valid = 0;     /* [D44-3] */
    ok_begin(req);
    ap(" tally_a=%u tally_b=%u mismatch=%d next_byte=", ta.count, tb.count, ta.count != tb.count);
    if (ta.next_byte >= 0) ap("%d", ta.next_byte);
    ap(" write_ok=%d", wok);
    ln_end();
}

static void cmd_blank(u32 req)
{
    u32 base, n;
    if (arg_u32("base", &base) || arg_u32("n_sectors", &n)) { reject(req, "E_RANGE"); return; }
    if (n == 0u) { reject(req, "E_NSECT0"); return; }
    if (base > CHIP_SECTORS || n > CHIP_SECTORS - base) { reject(req, "E_RANGE"); return; }
    if (g_state == ST_RUNNING) { reject(req, "E_STATE"); return; }
    static scan_t se, sp;
    if (scan_range(base, n, &se, 0xFFu, &sp, (u8)g_pattern)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    if (g_state == ST_RECOVERING) { g_last_bc.valid = 1; g_last_bc.base = base; g_last_bc.n = n; g_last_bc.resid = se.bits; }
    ok_begin(req);
    ap(" erase_residual_bits=%u program_fail_bits=%u", se.bits, sp.bits);
    ap_scan("", &se);                                 /* addrs 는 잔류 기준 (§3 #9) */
    ln_end();
}

static void cmd_tally(u32 req)
{
    if (g_state == ST_RUNNING) { reject(req, "E_STATE"); return; }
    tally_t ta, tb;
    if (tally_read_copy(0, &ta) || tally_read_copy(1, &tb)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    ok_begin(req);
    ap(" count_a=%u count_b=%u mismatch=%d", ta.count, tb.count, ta.count != tb.count);
    ln_end();
}

static void cmd_dump(u32 req)
{
    if (g_state == ST_RUNNING) { reject(req, "E_STATE"); return; }
    ok_begin(req); ln_end();
    for (u32 c = 0; c < 2u; c++) {                    /* 벌당 32행 × 128B (§3 #10) */
        u32 sector = c ? TALLY_SECTOR_B : TALLY_SECTOR_A;
        for (u32 off = 0; off < TALLY_BYTES; off += 128u) {
            if ((off % PAGE_BYTES) == 0u && read_page(sector * SECTOR_PAGES + off / PAGE_BYTES)) return;
            row_begin('D');
            ap(" copy=%u off=%u hex=", c, off);
            for (u32 i = 0; i < 128u; i++) ap("%02x", rx[4 + (off % PAGE_BYTES) + i]);
            ln_end();
        }
    }
}

static void cmd_uid(u32 req)
{
    if (g_state == ST_RUNNING) { reject(req, "E_STATE"); return; }
    u8 uid[UID_LEN];
    if (flash_read_uid(uid)) { reject(req, "E_STATE"); return; }
    ok_begin(req);
    ap(" uid=");
    for (u32 i = 0; i < UID_LEN; i++) ap("%02X", uid[i]);
    ln_end();
}

static void cmd_reerase(u32 req)
{
    u32 base, n;
    if (arg_u32("base", &base) || arg_u32("n_sectors", &n)) { reject(req, "E_RANGE"); return; }
    if (check_range(req, base, n)) return;
    if (g_state != ST_RECOVERING) { reject(req, "E_STATE"); return; }
    if (!g_last_bc.valid || g_last_bc.base != base || g_last_bc.n != n || g_last_bc.resid == 0u) {
        reject(req, "E_STATE"); return;               /* 마지막 blank_check 가 이 범위의 잔류를 보지 않았다 */
    }
    static scan_t s;
    u64 t_sum = 0; u32 resid_after = 0; int ok = 1;
    for (u32 k = 0; k < n; k++) {                     /* 잔류가 있는 섹터만 — 사건 1건 1행 */
        if (scan_range(base + k, 1, &s, 0xFFu, NULL, 0)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
        u32 before = s.bits;
        if (!before) continue;
        u64 t = 0;
        int rc = sector_erase(base + k, &t);
        t_sum += t;
        if (rc || scan_range(base + k, 1, &s, 0xFFu, NULL, 0)) {
            emit_r("reerase", 1, base + k, "erase", 1, t, 0, 1, before, 0, 0);
            ok = 0; resid_after += before;
            if (rc > 0) { stop_error("wip_timeout", base + k, "erase", 1, t, 0, 0); } else { g_state = ST_ERROR; }
            reject(req, "E_STATE");
            return;
        }
        emit_r("reerase", 1, base + k, "erase", 1, t, s.bits == 0u, 1, before, 1, s.bits);
        if (s.bits) ok = 0;
        resid_after += s.bits;
    }
    g_last_bc.resid = resid_after;
    ok_begin(req);
    ap(" ok=%d t_erase_us=", ok); ap_u64(t_sum); ap(" resid_after=%u", resid_after);
    ln_end();
}

/* tally 를 지우는 유일한 길 — S-1 §8.1 「실험 시작 시 tally 섹터 2개를 각 1회 소거」. 자물쇠 셋:
 * ① idle 에서만 (부팅 직후, 아무것도 돌지 않았다) ② uid 인자가 부팅 때 읽은 칩 UID 와 같아야 한다
 * (E_UID — 호스트가 소켓의 칩을 알고 있어야 지울 수 있다) ③ 범위는 상수 512·1,536 뿐, 인자로 못 바꾼다.
 * 지운 뒤 다시 읽어 전부 0xFF 인지(clean) 되돌린다. 지우기 전 값(count_a·count_b)도 되돌린다 — 호스트가
 * 장부(chip_pe.md)에 옮겨 적는 값이다. */
static void cmd_tally_erase(u32 req)
{
    const char *u = arg("uid");
    if (!u || strlen(u) != UID_LEN * 2u) { reject(req, "E_RANGE"); return; }
    for (u32 i = 0; i < UID_LEN; i++) {
        char hex[3]; snprintf(hex, sizeof hex, "%02X", g_uid[i]);
        if (toupper((unsigned char)u[2 * i]) != hex[0] || toupper((unsigned char)u[2 * i + 1]) != hex[1]) {
            reject(req, "E_UID"); return;
        }
    }
    if (g_state != ST_IDLE) { reject(req, "E_STATE"); return; }
    tally_t ta, tb;
    if (tally_read_copy(0, &ta) || tally_read_copy(1, &tb)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    u64 t_sum = 0;
    for (u32 copy = 0; copy < 2u; copy++) {
        u32 sector = copy ? TALLY_SECTOR_B : TALLY_SECTOR_A;
        u64 t = 0;
        int rc = sector_erase(sector, &t);
        t_sum += t;
        if (rc) {
            if (rc > 0) { stop_error("wip_timeout", sector, "erase", 1, t, 0, 0); } else { g_state = ST_ERROR; }
            reject(req, "E_STATE");
            return;
        }
    }
    tally_t ra, rb;                                   /* 다시 읽어 확인 — 안 지워졌으면 error 로 앉는다 */
    if (tally_read_copy(0, &ra) || tally_read_copy(1, &rb)) { reject(req, "E_STATE"); g_state = ST_ERROR; return; }
    int clean = !ra.marked && !rb.marked;
    if (!clean) g_state = ST_ERROR;
    g_tally_idx[0] = g_tally_idx[1] = 0;
    ok_begin(req);
    ap(" count_a=%u count_b=%u t_erase_us=", ta.count, tb.count); ap_u64(t_sum); ap(" clean=%d", clean);
    ln_end();
}

static void cmd_halt(u32 req)
{
    if (g_state != ST_RUNNING) { reject(req, "E_STATE"); return; }
    g_halt_pending = 1;                               /* 이 경계에서 멈춘다 ([D44-4]) */
    ok_begin(req); ln_end();
}

static void process_line(char *s)
{
    if (strncmp(s, CMD_PREFIX, strlen(CMD_PREFIX)) != 0) return;   /* 명령이 아닌 줄은 버린다 */
    char *body = s + strlen(CMD_PREFIX);
    char *sum_at = NULL;                              /* 마지막 " sum=" */
    for (char *p = body; (p = strstr(p, " sum=")) != NULL; p++) sum_at = p;
    u32 got = 0xFFFFFFFFu, want = 0;
    if (sum_at) {
        for (char *p = body; p < sum_at; p++) want += (u8)*p;
        want &= 0xFFFFu;
        char *end; unsigned long x = strtoul(sum_at + 5, &end, 16);
        if (end != sum_at + 5 && *end == 0) got = (u32)x;
        *sum_at = 0;
    }
    ntok = 0;                                         /* 토큰화 (sum 앞까지) */
    for (char *p = strtok(body, " "); p && ntok < TOK_MAX; p = strtok(NULL, " ")) tok[ntok++] = p;
    if (!ntok) return;
    u32 req = 0; arg_u32("req", &req);
    if (!sum_at || got != want) { reject(req, "E_SUM"); return; }          /* 1. 체크섬 — req 를 갱신하지 않는다 */
    if (g_have_req && req <= g_last_req) { reject(req, "E_DUP"); return; } /* 2. req 단조 — 재실행 없음 */
    g_have_req = 1; g_last_req = req;
    const char *verb = tok[0];
    if      (!strcmp(verb, "START"))   cmd_start(req);
    else if (!strcmp(verb, "STATUS"))  cmd_status(req);
    else if (!strcmp(verb, "RESUME"))  cmd_resume(req);
    else if (!strcmp(verb, "BLANK"))   cmd_blank(req);
    else if (!strcmp(verb, "TALLY"))   cmd_tally(req);
    else if (!strcmp(verb, "DUMP"))    cmd_dump(req);
    else if (!strcmp(verb, "UID"))     cmd_uid(req);
    else if (!strcmp(verb, "REERASE")) cmd_reerase(req);
    else if (!strcmp(verb, "HALT"))    cmd_halt(req);
    else if (!strcmp(verb, "TALLY_ERASE")) cmd_tally_erase(req);
    else reject(req, "E_STATE");                      /* 모르는 동사 */
}

/* RX 를 비운다 — 완성된 행마다 process_line. 사이클 경계와 유휴 루프에서 부른다 */
static void rx_pump(void)
{
    int c;
    while ((c = plat_getc()) >= 0) {
        if (c == '\r') continue;
        if (c == '\n') {
            if (rx_overflow) reject(0, "E_SUM");    /* 넘친 행 — 호스트가 기다리지 않게 */
            else { rxbuf[rxlen] = 0; process_line(rxbuf); }
            rxlen = 0; rx_overflow = 0;
            continue;
        }
        if (rxlen < RX_MAX - 1u) rxbuf[rxlen++] = (char)c;
        else rx_overflow = 1;
    }
}

int main(void)
{
    plat_init();
    /* 부팅: SPI → JEDEC → UID(3회 일치). 실패하면 error 로 앉아 STATUS 에 답한다. 배너 없음 (§3 #12) */
    u8 id[3];
    if (flash_spi_init_prescale(WEAR_SPI_PRESCALE) || flash_jedec_check(id) != 0 || flash_read_uid(g_uid) != 0)
        g_state = ST_ERROR;

    for (;;) {
        if (g_state == ST_RUNNING) {
            run_cycle();
            if (g_state != ST_RUNNING) continue;      /* §10 정지 */
            if (g_delta_left == 0u) { g_state = ST_CHECKPOINT_DUE; continue; }   /* §6 ⑤ — 여기서 멈춘다 */
            rx_pump();                                /* §3 #3 — 사이클 경계에서 RX 를 비운다 */
            if (g_halt_pending) {
                g_halt_pending = 0;
                g_state = ST_HALTED;
                emit_r("halt", 0, 0, "", 0, 0, 1, 0, 0, 0, 0);
            }
        } else {
            rx_pump();
        }
    }
    return 0;
}
