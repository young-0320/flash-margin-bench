/*
 * flash_jedec.c — 게재 2번: 보드↔W25Q64 모듈 통신 증거 (G2 JEDEC 브링업)
 *
 * 작성: Young 초안 (2026-07-08, 로그 14) — 스펙·검토·게재물 캡처 소유: 장세은 (로그 9 ③)
 *
 * PS 하드 SPI0(EMIO→JB, PL 로직 0 — 로그 9)으로 JEDEC ID(0x9F)를 1초 주기로
 * 읽어 판정 문구와 함께 반복 출력한다. "EF 40 17 [OK]" 화면 캡처 1장이 그대로
 * 게재물 (런북 3 D1). SPI 초기화·프리스케일러는 flash_prep.c 검증치 그대로 —
 * flash_prep(사전 쓰기)과 같은 G2 인프라를 쓰는 형제 유틸리티라 flash_* 가족.
 *
 * 빌드:       vitis -s ps/scripts/build_flash_jedec.py   (G2 XSA 소비)
 * 프로그래밍: xsct ps/scripts/program_g2.tcl build/vitis_jedec/flash_jedec/build/flash_jedec.elf
 * 결과 확인:  .venv/bin/python -m serial.tools.miniterm /dev/ttyUSB1 115200
 *
 * 판독 (런북 3 표 E): FF FF FF / 00 00 00 = 무칩·오배선 — D0 배선표 + /WP·/HOLD 3V3 확인
 */

#include "xspips.h"
#include "xil_printf.h"
#include "sleep.h"

#define CMD_JEDEC   0x9F

/* W25Q64 (윈본드): 제조사 EF, 타입 40, 용량 17(=64Mbit) */
#define ID_MF       0xEF
#define ID_TYPE     0x40
#define ID_CAP      0x17

static XSpiPs spi;

int main(void)
{
    /* 초기화 — flash_prep.c와 동일 (2024.2 SDT: LookupConfig는 BASEADDR을 받는다) */
    XSpiPs_Config *cfg = XSpiPs_LookupConfig(XPAR_XSPIPS_0_BASEADDR);
    if (!cfg || XSpiPs_CfgInitialize(&spi, cfg, cfg->BaseAddress) != XST_SUCCESS) {
        xil_printf("#G2 ERROR spi init\r\n");
        return 1;
    }
    XSpiPs_SetOptions(&spi, XSPIPS_MASTER_OPTION | XSPIPS_FORCE_SSELECT_OPTION);
    XSpiPs_SetClkPrescaler(&spi, XSPIPS_CLK_PRESCALE_64);   /* ≈2.6MHz, JEDEC은 저속 충분 */
    XSpiPs_SetSlaveSelect(&spi, 0);

    xil_printf("\r\n#G2 JEDEC BRINGUP — W25Q64 기대 ID: %02x %02x %02x (1초 주기 반복)\r\n",
               ID_MF, ID_TYPE, ID_CAP);

    for (u32 n = 1; ; n++, sleep(1)) {
        u8 tx[4] = {CMD_JEDEC, 0, 0, 0};
        u8 rx[4] = {0, 0, 0, 0};

        if (XSpiPs_PolledTransfer(&spi, tx, rx, 4) != XST_SUCCESS) {
            xil_printf("#G2 ERROR spi transfer (n=%u)\r\n", n);
            continue;
        }

        xil_printf("#G2 JEDEC %02x %02x %02x ", rx[1], rx[2], rx[3]);

        if (rx[1] == ID_MF && rx[2] == ID_TYPE && rx[3] == ID_CAP) {
            xil_printf("[OK] W25Q64 확인 — 보드-모듈 통신 정상 (n=%u)\r\n", n);
        } else if (rx[1] == 0xFF && rx[2] == 0xFF && rx[3] == 0xFF) {
            xil_printf("[FAIL] 응답 없음(FF) — 무칩/오배선: D0 배선표 + /WP·/HOLD 3V3 확인\r\n");
        } else if (rx[1] == 0x00 && rx[2] == 0x00 && rx[3] == 0x00) {
            xil_printf("[FAIL] 응답 없음(00) — 무칩/오배선/전원: VCC·GND·CS 확인\r\n");
        } else {
            xil_printf("[FAIL] 기대 밖 ID — 다른 칩이거나 간헐 접촉 의심\r\n");
        }
    }
}
