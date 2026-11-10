/* xuartps.h 심 — 보 레이트 설정은 호스트에서 할 일이 없다 */
#ifndef XUARTPS_H
#define XUARTPS_H
#include "xil_types.h"
typedef struct { u32 BaseAddress; } XUartPs_Config;
typedef struct { XUartPs_Config Config; } XUartPs;
XUartPs_Config *XUartPs_LookupConfig(u32 base);
int XUartPs_CfgInitialize(XUartPs *p, XUartPs_Config *c, u32 base);
int XUartPs_SetBaudRate(XUartPs *p, u32 baud);
#endif
