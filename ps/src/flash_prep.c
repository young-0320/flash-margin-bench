/*
 * flash_prep.c — 실칩 사전 쓰기 + 무결성 확인 (로그 10 결정 ④)
 *
 * 실칩 곡선(게재 4번)은 읽기 마진 측정 — 그 전에 이 앱이 PS 하드 SPI(저클럭,
 * 마진 논란 없음)로 페이지 0..N-1에 PRBS를 굽고 read-back 전수 비교로 "쓰기
 * 무결" 증거를 만든다. 통과한 경우에만 스윕 진행 (쓰기 오류의 읽기 마진 둔갑
 * 차단). 검증 읽기는 0x03 — 2.6MHz 유틸리티 경로이므로 측정 명령 통일(0x0B,
 * 결정 ③)과 무관.
 *
 * 실행 절차 (G2 인프라 재사용 — PL 로직 0, PS SPI0 EMIO→JB):
 *   1. vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl  (이미 있으면 생략)
 *   2. vitis -s ps/scripts/build_flash_prep.py
 *   3. xsct ps/scripts/program_g2.tcl build/vitis_prep/flash_prep/build/flash_prep.elf
 *   4. UART에서 "#PREP PASS" 확인 → 스윕 비트스트림(build_g3_chip.tcl)으로 재프로그램
 *
 * UID: JEDEC 통과 직후 4Bh(Read Unique ID)를 3회 읽어 일치하면 "#PREP UID <16hex>"
 * 출력. 개체 식별자(docs/chip_registry.md)이며 호스트 래퍼가 등록부 역조회·CSV
 * 열 기입에 쓴다. 계약 §6 밖(PS SPI 경로)이라 승인 없이 추가.
 *
 * PRBS-15 (계약 결정 19): x^15+x^14+1, 시드 {1, page[13:0]}, dout=lfsr[14] 후
 * 시프트, MSB-first 바이트 패킹 — flash_prbs15.v와 비트 단위 동일 (시드·방출
 * 컨벤션이 어긋나면 스윕이 전부 에러로 보인다).
 *
 * 주의: 실칩 스윕에서 B는 2,048비트(=1페이지) 고정 — B>2,048은 읽기가 페이지
 * 경계를 넘어 시드가 어긋나므로 무의미한 설정이다 (버스트당 시드 = 페이지 단위).
 */

#include "xspips.h"
#include "xil_printf.h"
#include "xuartps.h"
#include "xiltimer.h"               /* XTime_GetTime · COUNTS_PER_SECOND (2025.2 BSP는 xtime_l.h 대신 xiltimer) */

#define N_PAGES     2048u           /* = R6 상한 — N_READS를 어디까지 올려도(계약 §5
                                       레지스터 가변) 미준비 페이지가 없도록 전 범위
                                       준비 (리뷰 wf_16617fb7 #7). 512KB, ~1분 */
#define PAGE_BYTES  256u
#define SECTOR      4096u

#define CMD_JEDEC   0x9F
#define CMD_WREN    0x06
#define CMD_RDSR1   0x05
#define CMD_SE      0x20            /* 4KB sector erase */
#define CMD_PP      0x02            /* page program */
#define CMD_READ    0x03            /* 저클럭 검증 읽기 */
#define CMD_UID     0x4B            /* Read Unique ID: [4Bh][더미 4][UID 8] = 13바이트, 주소 없음 */
#define UID_LEN     8u

/* 신품 조사 (로그 30) — blank 판독 범위·주소 출력 상한·소거 시간 경고 */
#define CHIP_PAGES       32768u     /* W25Q64JV = 64Mbit / 256B */
#define BLANK_PRE_PAGE0  0u
#define BLANK_PRE_PAGES  CHIP_PAGES /* 전역 스캔 (S-2 §5) */
#define BLANK_ADDR_CAP   1024u      /* 주소 "출력" 상한 — 배열 크기가 아니다 */
#define ERASE_WARN_US    400000u    /* S-1 §10 */

/* addr3()가 3바이트 주소라 페이지 32,768을 넘기면 상위 비트가 조용히 잘린다 — 빌드 타임에 차단 */
_Static_assert(BLANK_PRE_PAGE0 + BLANK_PRE_PAGES <= CHIP_PAGES, "blank 범위가 칩을 넘는다");
_Static_assert(N_PAGES <= CHIP_PAGES, "prep 범위가 칩을 넘는다");

static XSpiPs spi;
static u8 tx[PAGE_BYTES + 4], rx[PAGE_BYTES + 4];

/* flash_prbs15.v와 동일: dout = lfsr[14], 이후 {lfsr[13:0], lfsr[14]^lfsr[13]} */
static u16 lfsr;
static void prbs_load(u16 page) { lfsr = 0x4000u | (page & 0x3FFFu); }
static u32 prbs_bit(void)
{
    u32 out = (lfsr >> 14) & 1u;
    u32 fb  = ((lfsr >> 14) ^ (lfsr >> 13)) & 1u;
    lfsr = (u16)(((lfsr << 1) | fb) & 0x7FFFu);
    return out;
}
static u8 prbs_byte(void)               /* MSB-first — SPI 송출 순서와 일치 */
{
    u8 b = 0;
    for (int i = 0; i < 8; i++) b = (u8)((b << 1) | prbs_bit());
    return b;
}

static int xfer(u8 *t, u8 *r, u32 len)
{
    if (XSpiPs_PolledTransfer(&spi, t, r, len) != XST_SUCCESS) {
        /* xil_printf는 SUPPORT_64BIT_PRINT라 %lu가 64비트 va_arg — u32는 %u로 (g0_sweep.c 관례) */
        xil_printf("#PREP ERROR spi transfer len=%u\r\n", len);
        return -1;
    }
    return 0;
}

static int wait_wip_clear(void)         /* RDSR1 bit0(BUSY) 폴 */
{
    for (u32 i = 0; i < 10000000u; i++) {
        tx[0] = CMD_RDSR1; tx[1] = 0;
        if (xfer(tx, rx, 2)) return -1;
        if (!(rx[1] & 1u)) return 0;
    }
    xil_printf("#PREP ERROR busy stuck\r\n");
    return -1;
}

static int wren(void)
{
    tx[0] = CMD_WREN;
    return xfer(tx, rx, 1);
}

static void addr3(u8 *p, u32 addr)
{
    p[0] = (u8)(addr >> 16); p[1] = (u8)(addr >> 8); p[2] = (u8)addr;
}

static u32 us_since(XTime t0)          /* XTime(u64) 경과를 us로 — xil_printf에는 u32 %u로만 넘긴다 */
{
    /* COUNTS_PER_SECOND 는 BSP(xtimer_config.h)에서 `XPAR_CPU_CORE_CLOCK_FREQ_HZ/2` 로
       정의돼 있고 괄호가 없다. 나눗셈에 직접 쓰면 X/(A/2) 가 아니라 X/A/2 로 전개돼
       결과가 정확히 4배 작아진다 (2026-09-15 chip02 실측: 소거 6.6ms → 실제 26.4ms).
       대입식에서 한 번 값으로 받으면 온전히 평가된다. */
    const u64 cps = COUNTS_PER_SECOND;
    XTime t1; XTime_GetTime(&t1);
    return (u32)(((t1 - t0) * 1000000ULL) / cps);
}

/* blank 판독: 페이지 page0..page0+npages-1 을 03h로 읽어 0으로 굳은 비트 수·바이트 수를 세고,
   그 바이트 주소는 스캔 중 그 자리에서 UART로 흘린다 (배열 없음 — addr_cap은 찍은 줄 수 상한).
   판정 없음: 재prep 칩(chip01)은 PRBS가 살아 있어 수백만 비트가 나오는 게 정상 (로그 30 §4.2).
   xfer 실패만 -1 (xfer가 #PREP ERROR를 찍는다) */
static int blank_scan(const char *phase, u32 page0, u32 npages, u32 addr_cap)
{
    u32 bits = 0, bytes = 0, shown = 0;
    XTime t0; XTime_GetTime(&t0);
    for (u32 i = 0; i < PAGE_BYTES; i++) tx[4 + i] = 0;
    for (u32 p = page0; p < page0 + npages; p++) {
        tx[0] = CMD_READ; addr3(&tx[1], p * PAGE_BYTES);
        if (xfer(tx, rx, PAGE_BYTES + 4)) return -1;
        for (u32 i = 0; i < PAGE_BYTES; i++) {
            u8 z = (u8)~rx[4 + i];      /* 0으로 굳은 비트 위치 */
            if (!z) continue;
            bytes++; bits += (u32)__builtin_popcount(z);
            if (shown < addr_cap) {
                xil_printf("#PREP BLANKADDR %s %u %u %02x\r\n", phase, p, i, z);
                shown++;
            }
        }
    }
    xil_printf("#PREP BLANK %-4s range=%u-%u bits=%u bytes=%u shown=%u t_ms=%u\r\n",
               phase, page0, page0 + npages - 1, bits, bytes, shown, us_since(t0) / 1000u);
    return 0;
}

/* UART 보 레이트 — 첫 출력보다 먼저, 전 앱 공통 (2026-09-15, 로그 30 §10.3 B). 호스트 기본값도 921600.
   드라이버가 TRM 절차(TX/RX 정지 → CD·BDIV 기록 → FIFO 리셋 → 재개)로 바꾸고 분주비도 고른다:
   100MHz 기준 클럭에서 CD=18·BDIV=5 → 925,925bps (+0.47%, 허용치 3% 안) */
#define UART_BAUD   921600u
static XUartPs uart;
static void uart_set_baud(void)
{
    XUartPs_CfgInitialize(&uart, XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR), XPAR_XUARTPS_0_BASEADDR);
    XUartPs_SetBaudRate(&uart, UART_BAUD);
}

int main(void)
{
    uart_set_baud();                        /* UART 921600 — 첫 출력 전에 (전 앱 공통) */

    XSpiPs_Config *cfg = XSpiPs_LookupConfig(XPAR_XSPIPS_0_BASEADDR);
    if (!cfg || XSpiPs_CfgInitialize(&spi, cfg, cfg->BaseAddress) != XST_SUCCESS) {
        xil_printf("#PREP ERROR spi init\r\n");
        return 1;
    }
    XSpiPs_SetOptions(&spi, XSPIPS_MASTER_OPTION | XSPIPS_FORCE_SSELECT_OPTION);
    XSpiPs_SetClkPrescaler(&spi, XSPIPS_CLK_PRESCALE_64);   /* ≈2.6MHz, JEDEC 검증치 */
    XSpiPs_SetSlaveSelect(&spi, 0);

    /* 글로벌 타이머 enable — 2025.2 BSP(xiltimer)는 crt0에서 타이머를 시작하지 않고 usleep()이 처음
       불릴 때만 켠다. 안 켜면 XTime_GetTime이 상수를 돌려줘 소거 시간이 전부 0으로 조용히 틀린다 */
    Xil_Out32(XPAR_GLOBAL_TMR_BASEADDR + 0x08u, 1u);

    /* 0. JEDEC 선검사 — 배선·칩 자체가 정상일 때만 지우기 시작 */
    tx[0] = CMD_JEDEC; tx[1] = tx[2] = tx[3] = 0;
    if (xfer(tx, rx, 4)) return 1;
    xil_printf("#PREP JEDEC %02x %02x %02x\r\n", rx[1], rx[2], rx[3]);
    if (rx[1] != 0xEF || rx[2] != 0x40 || rx[3] != 0x17) {
        xil_printf("#PREP FAIL jedec mismatch (want EF 40 17) — 배선/전원 확인\r\n");
        return 1;
    }

    /* 0b. UID(4Bh) — 배선 확인 후, 칩을 건드리기 전. SPI에는 체크섬이 없어 접촉이
       튀면 XST_SUCCESS로 틀린 값이 오므로, 위 JEDEC 검사가 값(EF 40 17)을 보듯 UID는
       3회 읽어 자기 일관성(전부 일치)을 요구한다 (로그 23 §5). 전송 실패는 3회 재시도.
       재시도 중에는 xfer()를 쓰지 않는다 — "#PREP ERROR"는 이 앱의 다른 모든 경로에서
       종료 신호라 호스트 래퍼가 그 줄에서 중단한다 (로그 25 중요 1). 포기할 때만 FAIL */
    u8 uid[3][UID_LEN];
    for (int k = 0; k < 3; k++) {
        int err = -1;
        for (int t = 0; t < 3 && err; t++) {
            tx[0] = CMD_UID;
            for (u32 i = 1; i < 5 + UID_LEN; i++) tx[i] = 0;
            err = (XSpiPs_PolledTransfer(&spi, tx, rx, 5 + UID_LEN) == XST_SUCCESS) ? 0 : -1;
        }
        if (err) {
            xil_printf("#PREP FAIL uid transfer (4Bh) 3회 실패 — 배선/전원 확인\r\n");
            return 1;
        }
        for (u32 i = 0; i < UID_LEN; i++) uid[k][i] = rx[5 + i];
    }
    for (int k = 1; k < 3; k++)
        for (u32 i = 0; i < UID_LEN; i++)
            if (uid[k][i] != uid[0][i]) {
                xil_printf("#PREP FAIL uid mismatch across 3 reads — SPI 경로 불안정\r\n");
                return 1;
            }
    xil_printf("#PREP UID ");           /* 16hex 대문자 — 호스트 파서와 맞춤 (xil_printf는 64비트 미지원이라 바이트별) */
    for (u32 i = 0; i < UID_LEN; i++) xil_printf("%02X", uid[0][i]);
    xil_printf("\r\n");

    xil_printf("#PREP BEGIN n_pages=%u prbs15 seed={1,page}\r\n", N_PAGES);

    /* 0c. 소거 전 전역 판독 — 출고 시점 결함 비트 (G-d 전반, 로그 30 §4.2). 판정 없음 */
    if (blank_scan("pre", BLANK_PRE_PAGE0, BLANK_PRE_PAGES, BLANK_ADDR_CAP)) return 1;

    /* 1. 대상 범위 섹터 지우기 — 섹터마다 SE 전송 완료~WIP 해제를 재서 즉시 출력 (G-b, 로그 30 §4.4).
       배열 없이 min/max/sum 스칼라만; 중앙값은 호스트가 낸다 */
    u32 end = N_PAGES * PAGE_BYTES;
    u32 er_min = 0xFFFFFFFFu, er_max = 0, er_sum = 0, er_over = 0;
    for (u32 a = 0; a < end; a += SECTOR) {
        if (wren()) return 1;
        tx[0] = CMD_SE; addr3(&tx[1], a);
        if (xfer(tx, rx, 4)) return 1;
        XTime t0; XTime_GetTime(&t0);
        if (wait_wip_clear()) return 1;
        u32 us = us_since(t0);
        xil_printf("#PREP ERASE %u %u\r\n", a / SECTOR, us);
        if (us > ERASE_WARN_US) {
            er_over++;
            xil_printf("#PREP ERASE WARN sector %u %uus > %uus — 계속 진행\r\n", a / SECTOR, us, ERASE_WARN_US);
        }
        if (us < er_min) er_min = us;
        if (us > er_max) er_max = us;
        er_sum += us;
    }
    xil_printf("#PREP erase done (%u sectors)\r\n", (end + SECTOR - 1) / SECTOR);
    xil_printf("#PREP ERASE SUMMARY n=%u min=%u max=%u mean=%u over400ms=%u\r\n",
               end / SECTOR, er_min, er_max, er_sum / (end / SECTOR), er_over);

    /* 1b. 소거 직후 판독 — 소거한 범위만 (G-d 후반, 로그 30 §4.3). 전역이면 안 지운 영역을
       "소거 잔여"로 세게 된다. 판정 없음 */
    if (blank_scan("post", 0u, N_PAGES, BLANK_ADDR_CAP)) return 1;

    /* 2. 페이지 프로그램: 페이지 p ← PRBS15(시드 {1, p}) */
    for (u32 p = 0; p < N_PAGES; p++) {
        if (wren()) return 1;
        tx[0] = CMD_PP; addr3(&tx[1], p * PAGE_BYTES);
        prbs_load((u16)p);
        for (u32 i = 0; i < PAGE_BYTES; i++) tx[4 + i] = prbs_byte();
        if (xfer(tx, rx, PAGE_BYTES + 4) || wait_wip_clear()) return 1;
    }
    xil_printf("#PREP program done\r\n");

    /* 3. read-back 전수 비교 — 실패 페이지·바이트 수를 시끄럽게 보고 */
    u32 bad_pages = 0, bad_bytes = 0;
    for (u32 p = 0; p < N_PAGES; p++) {
        tx[0] = CMD_READ; addr3(&tx[1], p * PAGE_BYTES);
        for (u32 i = 0; i < PAGE_BYTES; i++) tx[4 + i] = 0;
        if (xfer(tx, rx, PAGE_BYTES + 4)) return 1;
        prbs_load((u16)p);
        u32 bad = 0;
        for (u32 i = 0; i < PAGE_BYTES; i++)
            if (rx[4 + i] != prbs_byte()) bad++;
        if (bad) {
            bad_pages++; bad_bytes += bad;
            xil_printf("#PREP page %u: %u bad bytes\r\n", p, bad);
        }
    }

    if (bad_pages == 0)
        xil_printf("#PREP PASS all %u pages verified — 스윕 진행 가능\r\n", N_PAGES);
    else
        xil_printf("#PREP FAIL %u/%u pages, %u bytes — 스윕 금지, 원인 조사"
                   " (BP 보호비트/전원/배선)\r\n", bad_pages, N_PAGES, bad_bytes);

    while (1) ;   /* 결과를 UART에 남긴 채 정지 */
    return 0;
}
