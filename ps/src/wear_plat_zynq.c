/*
 * wear_plat_zynq.c — wear_plat.h 의 Zynq 구현 (PS UART0 폴링 수신 · 글로벌 타이머).
 *
 * UART 수신은 이 리포에 처음 생기는 배관이다 — 기존 앱은 전부 송신만 한다. RX FIFO 가 64B 라
 * 엔진이 사이클 경계마다 비우고, 호스트는 명령 하나를 보내면 응답을 받은 뒤에만 다음을 보낸다
 * (S-4 §5.2 · 로그 45). 보 레이트는 flash_io 의 uart_set_baud() (921600, 전 앱 공통).
 *
 * 타이머: 2025.2 BSP(xiltimer)는 crt0 에서 글로벌 타이머를 켜지 않는다 — 안 켜면 XTime_GetTime 이
 * 상수를 돌려줘 시간이 전부 0 으로 조용히 틀린다. COUNTS_PER_SECOND 는 괄호 없는 매크로라
 * 나눗셈에 직접 쓰면 4배 작아진다 — 둘 다 flash_prep.c 의 함정 그대로 (로그 30 · 36).
 */

#include "wear_plat.h"
#include "flash_io.h"

#include "xuartps.h"
#include "xiltimer.h"
#include "xil_io.h"

void plat_init(void)
{
    uart_set_baud();                                        /* 921600 — 첫 출력 전에 */
    Xil_Out32(XPAR_GLOBAL_TMR_BASEADDR + 0x08u, 1u);       /* 글로벌 타이머 enable */
}

void plat_puts(const char *s)
{
    while (*s)
        XUartPs_SendByte(XPAR_XUARTPS_0_BASEADDR, (u8)*s++);
}

int plat_getc(void)
{
    if (!XUartPs_IsReceiveData(XPAR_XUARTPS_0_BASEADDR))
        return -1;
    return (int)(XUartPs_ReadReg(XPAR_XUARTPS_0_BASEADDR, XUARTPS_FIFO_OFFSET) & 0xFFu);
}

uint64_t plat_now_us(void)
{
    const u64 cps = COUNTS_PER_SECOND;                      /* 대입으로 한 번 온전히 평가 */
    XTime t; XTime_GetTime(&t);
    /* t × 10⁶ 은 부팅 후 15.37시간(2⁶⁴ ÷ 10⁶ ÷ 333,333,333)에 64비트를 넘친다 — 2026-09-24 파일럿
       122,164사이클에서 실제로 넘쳐 시각이 43µs 로 돌아가고 wait_wip 이 가짜 wip_timeout 을 냈다
       (로그 45 §17). 초 부분과 나머지를 나눠 곱하면 넘치지 않는다 (나머지 < cps 라 곱이 3.3e14) */
    return (uint64_t)((t / cps) * 1000000ULL + ((t % cps) * 1000000ULL) / cps);
}
