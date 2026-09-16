/*
 * flash_io.h — 베어메탈 앱 공용 배관 (UART·PS SPI0·JEDEC·UID)
 *
 * 앱들이 각자 들고 있던 같은 코드를 모은 부품. main() 이 없다.
 * 구현은 flash_prep.c 의 검증된 코드를 그대로 옮긴 것이며 값(프리스케일러,
 * 보 레이트, UID_LEN, 3회 읽기)을 바꾸지 않았다.
 *
 * 지금 쓰는 앱: flash_id.  마모 엔진(flash_wear) 때 flash_prep·flash_jedec 을
 * 여기로 옮긴다 — 그 전까지 기존 4개 앱은 건드리지 않는다 (로그 36).
 *
 * 이 부품은 아무것도 출력하지 않는다. 실패 문구의 접두(#PREP / #G2)가 앱마다
 * 다르고 호스트 파서가 그 접두로 종료를 판정하므로, 판정과 출력은 앱이 한다.
 */

#ifndef FLASH_IO_H
#define FLASH_IO_H

#include "xil_types.h"

#define UID_LEN     8u              /* 4Bh 가 돌려주는 개체 식별자 길이 */

/* UART 921600 — 전 앱 공통. 첫 출력보다 먼저 부를 것 */
void uart_set_baud(void);

/* PS SPI0 초기화 + 프리스케일러(≈2.6MHz). 0=성공, 비영=실패 */
int  flash_spi_init(void);

/* 폴드 전송. 0=성공, -1=실패 (출력 없음 — 부르는 쪽이 찍는다) */
int  flash_xfer(u8 *t, u8 *r, u32 len);

/* 0x9F 를 읽어 id[3] 에 넣고 EF 40 17 과 대조.
   0=일치, 1=불일치(id 는 읽힌 값), -1=전송 실패(id 불정) */
int  flash_jedec_check(u8 id[3]);

/* 4Bh 를 3회 읽어 전부 일치할 때만 out 에 넣는다 (SPI 에 체크섬이 없어
   접촉이 튀면 XST_SUCCESS 로 틀린 값이 온다 — 로그 23 §5).
   0=성공, -1=전송 3회 실패, -2=3회 읽기 불일치 */
int  flash_read_uid(u8 out[UID_LEN]);

#endif  /* FLASH_IO_H */
