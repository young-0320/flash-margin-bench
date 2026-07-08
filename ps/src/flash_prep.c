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
 * PRBS-15 (계약 결정 19): x^15+x^14+1, 시드 {1, page[13:0]}, dout=lfsr[14] 후
 * 시프트, MSB-first 바이트 패킹 — flash_prbs15.v와 비트 단위 동일 (시드·방출
 * 컨벤션이 어긋나면 스윕이 전부 에러로 보인다).
 *
 * 주의: 실칩 스윕에서 B는 2,048비트(=1페이지) 고정 — B>2,048은 읽기가 페이지
 * 경계를 넘어 시드가 어긋나므로 무의미한 설정이다 (버스트당 시드 = 페이지 단위).
 */

#include "xspips.h"
#include "xil_printf.h"

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

int main(void)
{
    XSpiPs_Config *cfg = XSpiPs_LookupConfig(XPAR_XSPIPS_0_BASEADDR);
    if (!cfg || XSpiPs_CfgInitialize(&spi, cfg, cfg->BaseAddress) != XST_SUCCESS) {
        xil_printf("#PREP ERROR spi init\r\n");
        return 1;
    }
    XSpiPs_SetOptions(&spi, XSPIPS_MASTER_OPTION | XSPIPS_FORCE_SSELECT_OPTION);
    XSpiPs_SetClkPrescaler(&spi, XSPIPS_CLK_PRESCALE_64);   /* ≈2.6MHz, JEDEC 검증치 */
    XSpiPs_SetSlaveSelect(&spi, 0);

    /* 0. JEDEC 선검사 — 배선·칩 자체가 정상일 때만 지우기 시작 */
    tx[0] = CMD_JEDEC; tx[1] = tx[2] = tx[3] = 0;
    if (xfer(tx, rx, 4)) return 1;
    xil_printf("#PREP JEDEC %02x %02x %02x\r\n", rx[1], rx[2], rx[3]);
    if (rx[1] != 0xEF || rx[2] != 0x40 || rx[3] != 0x17) {
        xil_printf("#PREP FAIL jedec mismatch (want EF 40 17) — 배선/전원 확인\r\n");
        return 1;
    }

    xil_printf("#PREP BEGIN n_pages=%u prbs15 seed={1,page}\r\n", N_PAGES);

    /* 1. 대상 범위 섹터 지우기 */
    u32 end = N_PAGES * PAGE_BYTES;
    for (u32 a = 0; a < end; a += SECTOR) {
        if (wren()) return 1;
        tx[0] = CMD_SE; addr3(&tx[1], a);
        if (xfer(tx, rx, 4) || wait_wip_clear()) return 1;
    }
    xil_printf("#PREP erase done (%u sectors)\r\n", (end + SECTOR - 1) / SECTOR);

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
