/* xil_printf.h 심 — stdout 으로. 「#G0 SWEEP END」 · 「#G0 ERROR」 를 찍으면 프로세스를 끝낸다 (보드의 while(1) 정지 대신) */
#ifndef XIL_PRINTF_H
#define XIL_PRINTF_H
void xil_printf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#endif
