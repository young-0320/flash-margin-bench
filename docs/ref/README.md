# docs/ref — 외부 레퍼런스 (데이터시트·매뉴얼)

설계·판독의 근거가 된 벤더 문서 보관소. **판번(rev)이 핵심** — 데이터시트는
개정되므로, 파일을 추가할 때 아래 표에 판번·출처·수록일을 반드시 기록한다.

규칙:

- 파일명: `<대상>_<문서종류>_rev<판번>.pdf` (예: `w25q64jv_datasheet_revc.pdf`).
  소문자 + 언더스코어 (`CONTRIBUTING.md` §2)
- 대용량이거나 재배포가 꺼려지는 문서는 파일 대신 링크만 표에 남겨도 된다
- 본문 문서(로그·개념·런북)에서 인용할 때는 판번까지 적을 것

| 파일 | 문서 | 판번 | 출처 | 수록일 | 우리가 쓰는 곳 |
| ---- | ---- | ---- | ---- | ------ | -------------- |
| `w25q64jv_datasheet_revc.pdf` | W25Q64JV Datasheet (3V 64M-bit Serial Flash) | **Revision C** (2016-06-03) | winbond.com | 2026-07-08 | JEDEC ID·명령셋(0x9F/0x03/0x0B/0x4B)·타이밍(tSE·tPP·tCLQV)·내구성 "Min. 100K per sector"·BP 보호비트 |
| `w25q64fv_datasheet_revl.pdf` | W25Q64FV Datasheet (3V 64M-bit Serial Flash) — **우리 칩의 실제 세대** | **Revision L** (2013-10-07) | alldatasheet.com 재배포본 (Winbond 원본이 단종으로 안 보여서) | 2026-10-05 | 4KB 섹터 소거 tSE **typ 60ms(끝자리 IG) · 45ms(IQ · IF)** · max 400ms(76쪽) · 페이지 프로그램 tPP typ 0.7 · max 3ms — 기준선 ① 의 데이터시트 기준. 칩 마킹은 `../chip_registry.md` |
| `zybo_z7_refmanual_rev20180221.pdf` | Zybo Z7 Board Reference Manual (보드 rev.B 대상) | **2018-02-21 개정** | digilent.com | 2026-07-08 | Pmod 종류(JB 고속/JE 200Ω)·핀 배정·JP5 부팅 모드 |

## 선행 연구 조사 문서

| 문서 | 범위 |
| ---- | ---- |
| `선행논문_조사.md` | 국내 — NAND · NOR 신뢰성 일반 |
| `해외논문_조사.md` | 해외 — NAND 문턱전압(Vth) · 내부 접근 계열 |
| `선행논문_재활용판별_NOR소거열화.md` | 같은 신호(소거 시간)의 재활용 플래시 판별(Sakib 2018 등) · NOR 소거 시간 열화 기전(LIU 2019). 확인 수준(본문 · 초록 · 검색만) 표기 (2026-10-05) |

