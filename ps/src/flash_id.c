/*
 * flash_id.c — 읽기 전용 신원 확인 (JEDEC + UID). P/E 를 쓰지 않는다.
 *
 * 왜 있나: --mode sweep(등록된 칩 재측정)은 칩 신원을 사람 선언에 의존했다.
 * UID 는 g2 비트스트림(PS SPI) 위에서만 읽히는데 그 위에서 돌던 앱이 flash_prep
 * 하나뿐이고 걔는 반드시 소거·쓰기를 한다. 10칩 배치에서 앵커를 사이사이 끼우면
 * 잘못 집은 측정이 엉뚱한 칩에 영구히 귀속되므로(CSV 에 UID 가 박힌다) 읽기만
 * 하는 앱이 필요해졌다 — 로그 23 부록 A 가 "W5-M 에서는 다르다" 로 예고한 조건.
 *
 * 이 앱은 플래시에 쓰기 명령을 한 바이트도 내보내지 않는다 (소거·프로그램·WREN 없음).
 * 그것이 이 앱의 존재 이유다.
 *
 * 빌드:       vitis -s ps/scripts/build_flash_id.py      (G2 XSA 재사용, Vivado 재빌드 없음)
 * 프로그래밍: xsct ps/scripts/program_g2.tcl build/vitis_id/flash_id/build/flash_id.elf
 * 소비자:     host/run/run_sweep_chip.py --mode sweep 의 세션 1 (UID 대조)
 *
 * JEDEC 을 UID 와 같이 읽는 이유: UID 가 읽히면 통신은 이미 증명된다. JEDEC 의
 * 값어치는 실패했을 때 원인을 가르는 것뿐이다 (FF FF FF 무칩·오배선 / 00 00 00
 * 전원·CS / 그 외 다른 칩·간헐 접촉). 판정 문구는 flash_jedec.c 와 같다.
 */

#include "flash_io.h"
#include "xil_printf.h"

int main(void)
{
    u8 id[3], uid[UID_LEN];
    int rc;

    uart_set_baud();                        /* UART 921600 — 첫 출력 전에 (전 앱 공통) */

    if (flash_spi_init()) {
        xil_printf("#G2 ERROR spi init\r\n");
        return 1;
    }

    xil_printf("\r\n#G2 ID — 읽기 전용 신원 확인 (소거·쓰기 없음)\r\n");

    rc = flash_jedec_check(id);
    if (rc < 0) {
        xil_printf("#G2 ERROR spi transfer (jedec)\r\n");
        return 1;
    }
    xil_printf("#G2 JEDEC %02x %02x %02x ", id[0], id[1], id[2]);
    if (rc) {
        if (id[0] == 0xFF && id[1] == 0xFF && id[2] == 0xFF)
            xil_printf("[FAIL] 응답 없음(FF) — 무칩/오배선: D0 배선표 + /WP·/HOLD 3V3 확인\r\n");
        else if (id[0] == 0x00 && id[1] == 0x00 && id[2] == 0x00)
            xil_printf("[FAIL] 응답 없음(00) — 무칩/오배선/전원: VCC·GND·CS 확인\r\n");
        else
            xil_printf("[FAIL] 기대 밖 ID — 다른 칩이거나 간헐 접촉 의심\r\n");
        return 1;
    }
    xil_printf("[OK] W25Q64 확인 — 보드-모듈 통신 정상\r\n");

    rc = flash_read_uid(uid);
    if (rc == -1) {
        xil_printf("#G2 [FAIL] uid transfer (4Bh) 3회 실패 — 배선/전원 확인\r\n");
        return 1;
    }
    if (rc) {
        xil_printf("#G2 [FAIL] uid mismatch across 3 reads — SPI 경로 불안정\r\n");
        return 1;
    }
    xil_printf("#G2 UID ");             /* 16hex 대문자 — 호스트 파서와 맞춤 (xil_printf는 64비트 미지원이라 바이트별) */
    for (u32 i = 0; i < UID_LEN; i++) xil_printf("%02X", uid[i]);
    xil_printf("\r\n");

    while (1) ;   /* 결과를 UART 에 남긴 채 정지 */
    return 0;
}
