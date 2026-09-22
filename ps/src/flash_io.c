/*
 * flash_io.c — flash_io.h 구현. 코드는 flash_prep.c 에서 그대로 옮겼고,
 * flash_prep 도 이제 이 파일을 쓴다. 사본이 아니라 이전이다.
 *
 * 값은 하나도 바뀌지 않았다 — 프리스케일러 PRESCALE_64(≈2.6MHz) · UART 921600 ·
 * UID_LEN 8 · 4Bh 3회 읽기. 리팩터 전후 flash_prep.elf 의 UART 출력 문구
 * 19개가 전부 동일한 것으로 확인했다 (로그 36 §2-7).
 */

#include "flash_io.h"

#include "xspips.h"
#include "xuartps.h"

#define CMD_JEDEC   0x9F
#define CMD_UID     0x4B            /* Read Unique ID: [4Bh][더미 4][UID 8] = 13바이트, 주소 없음 */

/* W25Q64 (윈본드): 제조사 EF, 타입 40, 용량 17(=64Mbit) */
#define ID_MF       0xEF
#define ID_TYPE     0x40
#define ID_CAP      0x17

static XSpiPs spi;
static u8 tx[5 + UID_LEN], rx[5 + UID_LEN];     /* 최장 전송이 4Bh 13바이트 */

/* UART 보 레이트 — 첫 출력보다 먼저, 전 앱 공통 (2026-09-15, 로그 30 §10.3 B). 호스트 기본값도 921600.
   값은 전역 변수 — 호스트가 UART_BAUD 환경변수로 주면 program_*.tcl 이 ELF 를 올린 뒤 덮어쓴다.
   드라이버가 TRM 절차(TX/RX 정지 → CD·BDIV 기록 → FIFO 리셋 → 재개)로 바꾸고 분주비도 고른다:
   100MHz 기준 클럭에서 CD=18·BDIV=5 → 925,925bps (+0.47%, 허용치 3% 안) */
volatile u32 g_uart_baud = 921600u;   /* xsct 가 dow 뒤 con 앞에 덮어쓴다 (print -set) — 지민 PC 는 115200 */
static XUartPs uart;
void uart_set_baud(void)
{
    XUartPs_CfgInitialize(&uart, XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR), XPAR_XUARTPS_0_BASEADDR);
    XUartPs_SetBaudRate(&uart, g_uart_baud);
}

int flash_spi_init(void)
{
    return flash_spi_init_prescale(64u);                   /* ≈2.6MHz, JEDEC 검증치 */
}

int flash_spi_init_prescale(u32 div)
{
    u8 opt;
    switch (div) {                                          /* XSPIPS_CLK_PRESCALE_* 는 log2(div)-1 */
    case 4u:   opt = XSPIPS_CLK_PRESCALE_4;   break;
    case 8u:   opt = XSPIPS_CLK_PRESCALE_8;   break;
    case 16u:  opt = XSPIPS_CLK_PRESCALE_16;  break;
    case 32u:  opt = XSPIPS_CLK_PRESCALE_32;  break;
    case 64u:  opt = XSPIPS_CLK_PRESCALE_64;  break;
    case 128u: opt = XSPIPS_CLK_PRESCALE_128; break;
    case 256u: opt = XSPIPS_CLK_PRESCALE_256; break;
    default:   return -2;
    }
    /* 2024.2 SDT: LookupConfig 는 BASEADDR 을 받는다 */
    XSpiPs_Config *cfg = XSpiPs_LookupConfig(XPAR_XSPIPS_0_BASEADDR);
    if (!cfg || XSpiPs_CfgInitialize(&spi, cfg, cfg->BaseAddress) != XST_SUCCESS)
        return -1;
    XSpiPs_SetOptions(&spi, XSPIPS_MASTER_OPTION | XSPIPS_FORCE_SSELECT_OPTION);
    XSpiPs_SetClkPrescaler(&spi, opt);
    XSpiPs_SetSlaveSelect(&spi, 0);
    return 0;
}

int flash_xfer(u8 *t, u8 *r, u32 len)
{
    return (XSpiPs_PolledTransfer(&spi, t, r, len) == XST_SUCCESS) ? 0 : -1;
}

int flash_jedec_check(u8 id[3])
{
    tx[0] = CMD_JEDEC; tx[1] = tx[2] = tx[3] = 0;
    if (flash_xfer(tx, rx, 4)) return -1;
    id[0] = rx[1]; id[1] = rx[2]; id[2] = rx[3];
    return (id[0] == ID_MF && id[1] == ID_TYPE && id[2] == ID_CAP) ? 0 : 1;
}

int flash_read_uid(u8 out[UID_LEN])
{
    /* 전송 실패는 3회 재시도. 원본이 재시도 중에 xfer() 를 피한 것은 그것이
       "#PREP ERROR" 를 찍어 호스트 래퍼가 그 줄에서 중단하기 때문인데(로그 25 중요 1),
       여기 flash_xfer 는 아무것도 찍지 않으므로 그대로 쓴다 */
    u8 uid[3][UID_LEN];
    for (int k = 0; k < 3; k++) {
        int err = -1;
        for (int t = 0; t < 3 && err; t++) {
            tx[0] = CMD_UID;
            for (u32 i = 1; i < 5 + UID_LEN; i++) tx[i] = 0;
            err = flash_xfer(tx, rx, 5 + UID_LEN);
        }
        if (err) return -1;
        for (u32 i = 0; i < UID_LEN; i++) uid[k][i] = rx[5 + i];
    }
    for (int k = 1; k < 3; k++)
        for (u32 i = 0; i < UID_LEN; i++)
            if (uid[k][i] != uid[0][i]) return -2;
    for (u32 i = 0; i < UID_LEN; i++) out[i] = uid[0][i];
    return 0;
}
