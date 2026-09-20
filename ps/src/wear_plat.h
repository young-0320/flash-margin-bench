/*
 * wear_plat.h — 마모 엔진(flash_wear.c)이 플랫폼에 요구하는 전부.
 *
 * 엔진은 이 셋과 flash_io.h 만 부른다. Zynq 구현은 wear_plat_zynq.c(XUartPs 폴링 수신 ·
 * XTime), 호스트 시뮬레이션은 ps/sim/wear_plat_host.c(stdin/stdout · clock_gettime).
 * 같은 엔진 소스가 실칩과 호스트에서 같은 TB(host/tests/)로 채점되게 하려고 가른 것이다 (로그 45).
 */

#ifndef WEAR_PLAT_H
#define WEAR_PLAT_H

#include <stdint.h>

void     plat_init(void);            /* UART·타이머 준비 — 첫 출력보다 먼저 */
void     plat_puts(const char *s);   /* 행 하나(개행 포함)를 끝까지 보낸다 — 블로킹 */
int      plat_getc(void);            /* 수신 바이트 0..255, 없으면 -1. 블로킹하지 않는다 */
uint64_t plat_now_us(void);          /* 부팅 후 µs (u64) */

#endif /* WEAR_PLAT_H */
