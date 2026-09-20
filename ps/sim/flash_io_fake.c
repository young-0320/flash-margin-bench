/*
 * flash_io_fake.c — flash_io.h 의 호스트 구현: 8MB NOR 모델 (W25Q64JV 흉내).
 *
 * 같은 서명(uart_set_baud · flash_spi_init · flash_spi_init_prescale · flash_xfer ·
 * flash_jedec_check · flash_read_uid) 위에 06 WREN · 04 WRDI · 05 RDSR1 · 20 SE · 02 PP(AND) ·
 * 03 READ · 9F JEDEC · 4B UID 를 모델링한다. UID 는 mock 의 REGISTRY_UID(chip01) 와 같다.
 * 칩 물리는 없다 — 소거는 즉시 0xFF, 프로그램은 AND, WIP 는 RDSR 몇 번 뒤에 풀린다.
 *
 * 환경변수:
 *   WEAR_FAKE_IMAGE=<file>   초기 이미지 패치. 줄마다 `<addr> <byte>` 또는 `fill <addr> <len> <byte>`
 *                            (숫자는 0x 허용, `#` 주석). tally 마크·잔류 비트를 심는다
 *   WEAR_FAKE_TRACE=<file>   P/E 자취를 덧붙인다 — `SE <sector>` · `PP <addr> <len>`. TB 가
 *                            소거·프로그램 주소가 전부 [base, base+n) 안인지 (tally 제외) 본다
 *   WEAR_FAKE_STUCK_SE=<n>   그 섹터의 SE 뒤 WIP 가 영원히 안 풀린다 — wip_timeout 경로
 *   WEAR_FAKE_STATE=<file>   raw 8MB 이미지. 있으면 시작 때 읽고, 종료(stdin EOF) 때 쓴다 —
 *                            프로세스를 다시 띄우는 것이 보드 리셋이고 칩만 남는다 (무상태 엔진의 J·B)
 *
 * jedec_check·read_uid 는 flash_io.c 와 같은 논리다 — 그 파일은 xspips.h 에 묶여 있어 호스트에서
 * 컴파일할 수 없다. 이 둘은 시험 대역이고 검증된 배관의 재사용은 엔진(flash_wear.c) 쪽 이야기다.
 */

#define _POSIX_C_SOURCE 200809L
#include "flash_io.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHIP_BYTES   (8u << 20)
#define SECTOR_BYTES 4096u
#define PAGE_BYTES   256u
#define BUSY_POLLS   2               /* SE/PP 뒤 RDSR 두 번은 BUSY */

static u8 *mem;
static const char *state_path;
static int wel, busy_polls;
static long stuck_se = -1;
static FILE *trace;
static const u8 UID[UID_LEN] = { 0xD1, 0x65, 0x4C, 0xB0, 0x9B, 0x35, 0x22, 0x33 };

static void load_image(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { fprintf(stderr, "fake: cannot open WEAR_FAKE_IMAGE %s\n", path); exit(2); }
    char ln[256];
    while (fgets(ln, sizeof ln, f)) {
        char *p = ln; while (*p == ' ' || *p == '\t') p++;
        if (*p == '#' || *p == '\n' || !*p) continue;
        unsigned long a, n = 1, v;
        if (!strncmp(p, "fill", 4)) {
            if (sscanf(p + 4, "%li %li %li", (long *)&a, (long *)&n, (long *)&v) != 3) { fprintf(stderr, "fake: bad line %s", ln); exit(2); }
        } else if (sscanf(p, "%li %li", (long *)&a, (long *)&v) != 2) { fprintf(stderr, "fake: bad line %s", ln); exit(2); }
        for (unsigned long i = 0; i < n && a + i < CHIP_BYTES; i++) mem[a + i] = (u8)v;
    }
    fclose(f);
}

static void save_state(void)
{
    FILE *f = fopen(state_path, "wb");
    if (!f) return;
    fwrite(mem, 1, CHIP_BYTES, f);
    fclose(f);
}

void uart_set_baud(void) {}

int flash_spi_init(void) { return flash_spi_init_prescale(64u); }

int flash_spi_init_prescale(u32 div)
{
    (void)div;
    if (!mem) {
        mem = malloc(CHIP_BYTES);
        memset(mem, 0xFF, CHIP_BYTES);
        const char *img = getenv("WEAR_FAKE_IMAGE"), *tr = getenv("WEAR_FAKE_TRACE"), *st = getenv("WEAR_FAKE_STUCK_SE");
        state_path = getenv("WEAR_FAKE_STATE");
        if (state_path && *state_path) {
            FILE *f = fopen(state_path, "rb");
            if (f) { if (fread(mem, 1, CHIP_BYTES, f) != CHIP_BYTES) { fprintf(stderr, "fake: short WEAR_FAKE_STATE\n"); exit(2); } fclose(f); }
            atexit(save_state);
        } else state_path = NULL;
        if (img && *img) load_image(img);
        if (tr && *tr) trace = fopen(tr, "a");
        if (st && *st) stuck_se = strtol(st, NULL, 0);
    }
    return 0;
}

static u32 addr_of(const u8 *t) { return ((u32)t[1] << 16) | ((u32)t[2] << 8) | t[3]; }

int flash_xfer(u8 *t, u8 *r, u32 len)
{
    memset(r, 0xFF, len);
    switch (t[0]) {
    case 0x06: wel = 1; break;
    case 0x04: wel = 0; break;
    case 0x05: {
        u8 sr = 0;
        if (busy_polls > 0) { busy_polls--; sr |= 0x01; }
        if (wel) sr |= 0x02;
        if (len > 1) r[1] = sr;
        break;
    }
    case 0x20:                                          /* 4KB 섹터 소거 */
        if (len >= 4 && wel) {
            u32 a = addr_of(t) & ~(SECTOR_BYTES - 1u);
            memset(mem + (a % CHIP_BYTES), 0xFF, SECTOR_BYTES);
            busy_polls = (stuck_se >= 0 && (long)(a / SECTOR_BYTES) == stuck_se) ? 0x7FFFFFFF : BUSY_POLLS;
            wel = 0;
            if (trace) { fprintf(trace, "SE %u\n", a / SECTOR_BYTES); fflush(trace); }
        }
        break;
    case 0x02:                                          /* 페이지 프로그램 — AND, 페이지 안에서 감긴다 */
        if (len >= 5 && wel) {
            u32 a = addr_of(t);
            for (u32 i = 4; i < len; i++)
                mem[((a & ~(PAGE_BYTES - 1u)) | ((a + i - 4) & (PAGE_BYTES - 1u))) % CHIP_BYTES] &= t[i];
            busy_polls = BUSY_POLLS; wel = 0;
            if (trace) { fprintf(trace, "PP %u %u\n", a, len - 4); fflush(trace); }
        }
        break;
    case 0x03:
        if (len >= 4) { u32 a = addr_of(t); for (u32 i = 4; i < len; i++) r[i] = mem[(a + i - 4) % CHIP_BYTES]; }
        break;
    case 0x9F: if (len >= 4) { r[1] = 0xEF; r[2] = 0x40; r[3] = 0x17; } break;
    case 0x4B: if (len >= 5 + UID_LEN) memcpy(r + 5, UID, UID_LEN); break;
    default: break;
    }
    return 0;
}

int flash_jedec_check(u8 id[3])
{
    u8 t[4] = { 0x9F, 0, 0, 0 }, r[4];
    if (flash_xfer(t, r, 4)) return -1;
    id[0] = r[1]; id[1] = r[2]; id[2] = r[3];
    return (id[0] == 0xEF && id[1] == 0x40 && id[2] == 0x17) ? 0 : 1;
}

int flash_read_uid(u8 out[UID_LEN])
{
    u8 uid[3][UID_LEN], t[5 + UID_LEN], r[5 + UID_LEN];
    for (int k = 0; k < 3; k++) {
        memset(t, 0, sizeof t); t[0] = 0x4B;
        if (flash_xfer(t, r, 5 + UID_LEN)) return -1;
        memcpy(uid[k], r + 5, UID_LEN);
    }
    for (int k = 1; k < 3; k++)
        if (memcmp(uid[k], uid[0], UID_LEN)) return -2;
    memcpy(out, uid[0], UID_LEN);
    return 0;
}
