/* xil_io.h 심 — 호스트 시뮬레이션에서 레지스터 접근을 가짜 core(bt2_core_fake.c)로 돌린다 */
#ifndef XIL_IO_H
#define XIL_IO_H
#include "xil_types.h"
typedef uintptr_t UINTPTR;
u32  Xil_In32(UINTPTR addr);
void Xil_Out32(UINTPTR addr, u32 value);
#endif
