# 칩 P/E 이력 (append-only)

Updated: 2026-09-20

칩별·섹터 범위별 **P/E(Program/Erase) 증분의 이력**이다. 누적값을 들지 않는다 — 누적은
파생량이고 이력이 원시값이다(계약 §6의 "파생량은 저장하지 않는다"와 같은 태도). 합산이
필요하면 읽는 쪽이 라벨·섹터 범위로 골라 더한다.

왜 이력인가 (로그 23 부록 B): 마모 실험은 한 칩 안에서 섹터 그룹마다 마모량을 다르게
간다(S-1: 0\~6 마모 / 7\~13 근접 대조 / 121\~127 원격 대조). 칩 단위 누적값 하나로는
표현이 안 되고, 범위별 누적값을 두면 새 작업이 올 때마다 기존 행을 분할·병합해야 해서
파일이 망가질 여지가 크다. 증분만 덧붙이면 기계가 기존 행을 건드릴 일이 없고, `git diff`가
항상 추가만이라 사람이 확인하기 쉬우며, 마모 체크포인트마다 "언제 어떤 작업이 얼마를
넣었나"가 남는다 — **교정 곡선의 x축이 여기서 나온다.**

## 규칙

- **append-only.** 기존 행을 수정·삭제하지 않는다. 잘못된 행은 지우지 말고 정정 행을
  아래에 덧붙인다(비고에 사유, 증분은 상쇄값)
- 행 하나 = 작업 하나. `flash_prep` 1회 = 그 범위 P/E +1 (현재 prep은 항상 전 범위 `0~127`)
- 기계가 쓴다: `host/run/run_sweep_chip.py`가 `flash_prep`을 돌릴 때마다 한 줄
  (`host/run/chip_pe.py`). 사람은 정정 행과 소급 행만 쓴다
- `--blind`가 켜진 배치는 증분 대신 **`(MASK)`** 를 적는다. 행은 남고 값만 가린다. 2026-09-30 까지는 `(봉인)` 이었다 —
  `(미확보)` 와 같은 괄호 꼴이라 파서가 같은 규칙으로 거른다([U48-7]). 블라인드 절차는 S-1 §15 2026-09-30 추기
- `UID`는 등록부(`docs/chip_registry.md`)와 같은 대문자 16 hex. UID를 읽기 전 작업은
  `(미확보)`
- 정본 관계: 누적 P/E의 **정본은 칩 자신의 tally 섹터**(S-1 §8)다. 이 파일은 호스트 측
  이력이며 tally와 어긋나면 칩이 진실이다. 등록부는 값을 두지 않고 이 파일을 가리킨다

## 이력

| 일자 | 라벨 | UID | 섹터 범위 | P/E 증분 | 출처 | 비고 |
| ---- | ---- | --- | --------- | -------- | ---- | ---- |
| 2026-07-08 | chip01 | (미확보) | 0~127 | 미상(≥1) | flash_prep | 횟수 미기록 — 소급 불가. 로그 13·14·15 어디에도 실행 횟수 없음. 추정치를 넣지 않는다 |
| 2026-09-15 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260915T150530Z) |  |
| 2026-09-15 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260915T150248Z) | UART 단절로 호스트만 중단, 보드는 완주 — 다음 런 blank_pre가 증명(bits=2097152 = 페이지 0~2047 비트의 정확히 절반 = PRBS). 출고 blank 미관측 |
| 2026-09-15 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260915T152106Z) |  |
| 2026-09-15 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260915T153852Z) |  |
| 2026-09-15 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260915T154507Z) |  |
| 2026-09-15 | chip03 | D1628C10C3433F33 | 0~127 | +1 | flash_prep (batch 20260915T155433Z) |  |
| 2026-09-16 | chip04 | D16484578B525622 | 0~127 | +1 | flash_prep (batch 20260916T125643Z) |  |
| 2026-09-16 | chip01 | D1654CB09B352233 | 0~127 | +1 | flash_prep (batch 20260916T080924Z) |  |
| 2026-09-16 | chip02 | D1642C74E7134527 | 0~127 | +1 | flash_prep (batch 20260916T161728Z) |  |
| 2026-09-16 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260916T162838Z) |  |
| 2026-09-20 | chip07 | D1629835DB334534 | 0~127 | +1 | flash_prep (batch 20260920T071531Z) |  |
| 2026-09-20 | chip09 | D1657C9713633921 | 0~127 | +1 | flash_prep (batch 20260920T072000Z) |  |
| 2026-09-20 | chip08 | D16414615B564524 | 0~127 | +1 | flash_prep (batch 20260920T072456Z) |  |
| 2026-09-20 | chip10 | DF685453E7791531 | 0~127 | +1 | flash_prep (batch 20260920T072822Z) |  |
| 2026-09-21 | chip02 | D1642C74E7134527 | 1000~1006 | +100 | run_wear accept (session 1789984537) | cycle 0→100 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~127 | +1 | flash_prep (batch 20260922T153213Z) |  |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~127 | +1 | flash_prep (batch 20260922T153648Z) |  |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +100 | run_wear accept (session 1790091548) | cycle 0→100 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +200 | run_wear accept (session 1790091548) | cycle 100→300 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 300 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +300 | run_wear accept (session 1790091548) | cycle 300→600 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 600 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +800 | run_wear accept (session 1790091548) | cycle 600→1400 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 1400 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1600 | run_wear accept (session 1790091548) | cycle 1400→3000 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +3400 | run_wear accept (session 1790091548) | cycle 3000→6400 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 6400 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +7400 | run_wear accept (session 1790091548) | cycle 6400→13800 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 13800 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +15800 | run_wear accept (session 1790091548) | cycle 13800→29600 |
| 2026-09-22 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 29600 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-23 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790091548) | cycle 29600→59600 |
| 2026-09-23 | chip01 | D1654CB09B352233 | 0~6 | +4100 | run_wear accept (session 1790091548) | cycle 59600→63700 |
| 2026-09-23 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790091548) | 체크포인트 63700 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-23 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790091548) | cycle 63700→93700 |
| 2026-09-23 | chip01 | D1654CB09B352233 | 0~6 | +28464 | run_wear accept (session 1790091548) | cycle 93700→122164 · error |
| 2026-09-24 | chip01 | D1654CB09B352233 | 6 | ±1 | run_wear resume (session 1790211816) | reerase · ±1 |
| 2026-09-24 | chip01 | D1654CB09B352233 | 0~6 | +14836 | run_wear accept (session 1790212214) | cycle 122164→137000 |
| 2026-09-24 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790212214) | 체크포인트 137000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-24 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790212214) | cycle 137000→167000 |
| 2026-09-24 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790212214) | cycle 167000→197000 |
| 2026-09-25 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790212214) | cycle 197000→227000 |
| 2026-09-25 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790212214) | cycle 227000→257000 |
| 2026-09-26 | chip01 | D1654CB09B352233 | 0~6 | +30000 | run_wear accept (session 1790212214) | cycle 257000→287000 |
| 2026-09-26 | chip01 | D1654CB09B352233 | 0~6 | +7500 | run_wear accept (session 1790212214) | cycle 287000→294500 |
| 2026-09-26 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790212214) | 체크포인트 294500 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip01 | D1654CB09B352233 | 0~6 | +5500 | run_wear accept (session 1790212214) | cycle 294500→300000 |
| 2026-09-26 | chip01 | D1654CB09B352233 | 0~6 | +1 | run_wear checkpoint (session 1790212214) | 체크포인트 300000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +100 | run_wear accept (session 1790408609) | cycle 0→100 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +900 | run_wear accept (session 1790408609) | cycle 100→1000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +2000 | run_wear accept (session 1790408609) | cycle 1000→3000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +7000 | run_wear accept (session 1790408609) | cycle 3000→10000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 10000→20000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 20000→30000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 30000→40000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 40000→50000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 50000→60000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 60000→70000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 70000→80000 |
| 2026-09-26 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 80000→90000 |
| 2026-09-27 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip03 | D1628C10C3433F33 | 0~6 | +10000 | run_wear accept (session 1790408609) | cycle 90000→100000 |
| 2026-09-27 | chip03 | D1628C10C3433F33 | 0~6 | +1 | run_wear checkpoint (session 1790408609) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip03 | D1628C10C3433F33 | 0~127 | +1 | flash_prep (batch 20260927T034035Z) |  |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +100 | run_wear accept (session 1790494073) | cycle 0→100 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +900 | run_wear accept (session 1790494073) | cycle 100→1000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +2000 | run_wear accept (session 1790494073) | cycle 1000→3000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +7000 | run_wear accept (session 1790494073) | cycle 3000→10000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790494073) | cycle 10000→20000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790494073) | cycle 20000→30000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790494073) | cycle 30000→40000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790494073) | cycle 40000→50000 |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790494073) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790494073) | cycle 50000→60000 — 호스트 USB 끊김(09-28 01:20:56 KST) 뒤 엔진 단독 완주, resume 채택값 60000 (tally 두 벌 일치 · A 로그 52,670 까지) |
| 2026-09-28 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790562456) | cycle 60000→70000 |
| 2026-09-28 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790562456) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-28 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790562456) | cycle 70000→80000 — 호스트 USB 끊김(09-29 01:18:21 KST) 뒤 엔진 단독 완주, resume 채택값 80000 (A 로그 76,169 까지) |
| 2026-09-29 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790643103) | cycle 80000→90000 |
| 2026-09-29 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790643103) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-29 | chip07 | D1629835DB334534 | 0~6 | +10000 | run_wear accept (session 1790643103) | cycle 90000→100000 |
| 2026-09-29 | chip07 | D1629835DB334534 | 0~6 | +1 | run_wear checkpoint (session 1790643103) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip07 | D1629835DB334534 | 0~127 | +1 | flash_prep (batch 20260930T041700Z) |  |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +100 | run_wear accept (session 1790423530) | cycle 0→100 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +900 | run_wear accept (session 1790423530) | cycle 100→1000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +2000 | run_wear accept (session 1790423530) | cycle 1000→3000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +7000 | run_wear accept (session 1790423530) | cycle 3000→10000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790423530) | cycle 10000→20000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790423530) | cycle 20000→30000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790423530) | cycle 30000→40000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790423530) | cycle 40000→50000 |
| 2026-09-26 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790423530) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790423530) | cycle 50000→60000 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | 수기 체크포인트 prep (session 1790423530) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) · DUMP 62/64 중단 뒤 수작업 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +6671 | run_wear accept (session 1790482991) | cycle 60000→66671 · error |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | 수기 복구 prep (session 1790482991) | wip_timeout@66671 후 복구 기준 66600 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +3400 | run_wear accept (session 1790491294) | cycle 66600→70000 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790491294) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790491294) | cycle 70000→80000 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790491294) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790491294) | cycle 80000→90000 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790491294) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +10000 | run_wear accept (session 1790491294) | cycle 90000→100000 |
| 2026-09-27 | chip04 | D16484578B525622 | 0~6 | +1 | run_wear checkpoint (session 1790491294) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-27 | chip04 | D16484578B525622 | 0~127 | +1 | flash_prep (batch 20260927T173048Z) |  |
| 2026-09-30 | chip12 | D165B43013742436 | 0~127 | +1 | flash_prep (batch 20260930T160205Z) |  |
| 2026-09-30 | chip15 | D16314314B671B24 | 0~127 | +1 | flash_prep (batch 20260930T161054Z) |  |
| 2026-09-30 | chip18 | D1652C218B613936 | 0~127 | +1 | flash_prep (batch 20260930T161746Z) |  |
| 2026-09-30 | chip17 | D1642C325331242E | 0~127 | +1 | flash_prep (batch 20260930T162156Z) |  |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +100 | run_wear accept (session 1790786787) | cycle 0→100 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +900 | run_wear accept (session 1790786787) | cycle 100→1000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +2000 | run_wear accept (session 1790786787) | cycle 1000→3000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +7000 | run_wear accept (session 1790786787) | cycle 3000→10000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 10000→20000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 20000→30000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 30000→40000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 40000→50000 |
| 2026-09-30 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 50000→60000 |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 60000→70000 |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 70000→80000 |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 80000→90000 |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +10000 | run_wear accept (session 1790786787) | cycle 90000→100000 · 호스트가 정지 직후 종료해 자동 기록 누락 — resume 채택값 100000(tally 2벌 일치·잔류 0)으로 정정 |
| 2026-10-01 | chip09 | D1657C9713633921 | 0~6 | +1 | run_wear checkpoint (session 1790786787) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip14 | DF678C14CF384F30 | 0~127 | +1 | flash_prep (batch 20261001T060304Z) | 라벨 입력 전 Ctrl-C — 장부 자동 기록 누락, 세션 로그(#PREP PASS)로 정정 |
| 2026-10-01 | chip14 | DF678C14CF384F30 | 0~127 | +1 | flash_prep (batch 20261001T061018Z) | 라벨 입력 전 Ctrl-C — 장부 자동 기록 누락, 세션 로그(#PREP PASS)로 정정 |
| 2026-10-01 | chip14 | DF678C14CF384F30 | 0~127 | +1 | flash_prep (batch 20261001T061625Z) |  |
| 2026-10-01 | chip14 | DF678C14CF384F30 | 0~127 | +1 | flash_prep (batch 20261001T062828Z) |  |
| 2026-10-01 | chip16 | D165906063442A33 | 0~127 | +1 | flash_prep (batch 20261001T063724Z) |  |
| 2026-10-01 | chip06 | D16428231B4E182B | 0~6 | +100 | run_wear accept (수기 복구, 호스트 로그 유실) | cycle 0→100 — 칩 내부 tally 확인 후 장부 보정 |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +900 | run_wear accept (session 1790788847) | cycle 100→1000 |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +1 | run_wear checkpoint (session 1790788847) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +2000 | run_wear accept (session 1790788847) | cycle 1000→3000 |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +1 | run_wear checkpoint (session 1790788847) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +7000 | run_wear accept (session 1790788847) | cycle 3000→10000 |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +1 | run_wear checkpoint (session 1790788847) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +2000 | run_wear accept (session 1790788847) | cycle 10000→12000 |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~6 | +1 | run_wear checkpoint (session 1790788847) | 체크포인트 12000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260930T210515Z) |  |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260930T211318Z) |  |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260930T224142Z) |  |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260930T224956Z) |  |
| 2026-09-30 | chip06 | D16428231B4E182B | 0~127 | +1 | flash_prep (batch 20260930T225928Z) |  |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +100 | run_wear accept (session 1790852877) | cycle 0→100 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790852877) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +900 | run_wear accept (session 1790852877) | cycle 100→1000 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790852877) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +2000 | run_wear accept (session 1790852877) | cycle 1000→3000 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790852877) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +4400 | run_wear accept (session 1790852877) | cycle 3000→7400 · error |
| 2026-10-01 | chip12 | D165B43013742436 | 1 | ±1 | run_wear resume (session 1790864208) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 6 | ±1 | run_wear resume (session 1790864208) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 2 | ±1 | run_wear resume (session 1790880901) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 3 | ±1 | run_wear resume (session 1790880901) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 4 | ±1 | run_wear resume (session 1790880901) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 5 | ±1 | run_wear resume (session 1790880901) | reerase · ±1 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +2600 | run_wear accept (session 1790880923) | cycle 7400→10000 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 10000→20000 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 20000→30000 |
| 2026-10-01 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 30000→40000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 40000→50000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 50000→60000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +100 | run_wear accept (session 1790851785) | cycle 0→100 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +900 | run_wear accept (session 1790851785) | cycle 100→1000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +2000 | run_wear accept (session 1790851785) | cycle 1000→3000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +7000 | run_wear accept (session 1790851785) | cycle 3000→10000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790851785) | cycle 10000→20000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790851785) | cycle 20000→30000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790851785) | cycle 30000→40000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790851785) | cycle 40000→50000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790851785) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790879592) | cycle 50000→60000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790879592) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790879592) | cycle 60000→70000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790879592) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790879592) | cycle 70000→80000 |
| 2026-10-01 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790879592) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790879592) | cycle 80000→90000 |
| 2026-10-02 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790879592) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip17 | D1642C325331242E | 0~6 | +10000 | run_wear accept (session 1790879592) | cycle 90000→100000 |
| 2026-10-02 | chip17 | D1642C325331242E | 0~6 | +1 | run_wear checkpoint (session 1790879592) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 60000→70000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 70000→80000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 80000→90000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +10000 | run_wear accept (session 1790880923) | cycle 90000→100000 |
| 2026-10-02 | chip12 | D165B43013742436 | 0~6 | +1 | run_wear checkpoint (session 1790880923) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip12 | D165B43013742436 | 0~127 | +1 | flash_prep (batch 20261003T003713Z) |  |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +100 | run_wear accept (session 1790989701) | cycle 0→100 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 100 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +900 | run_wear accept (session 1790989701) | cycle 100→1000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 1000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +2000 | run_wear accept (session 1790989701) | cycle 1000→3000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 3000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +7000 | run_wear accept (session 1790989701) | cycle 3000→10000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 10000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 10000→20000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 20000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 20000→30000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 30000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 30000→40000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 40000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 40000→50000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 50000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 50000→60000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 60000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 60000→70000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 70000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 70000→80000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 80000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 80000→90000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 90000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +10000 | run_wear accept (session 1790989701) | cycle 90000→100000 |
| 2026-10-03 | chip18 | D1652C218B613936 | 0~6 | +1 | run_wear checkpoint (session 1790989701) | 체크포인트 100000 — 소거+PRBS (측정용, 마모 카운터에는 안 센다) |
| 2026-10-04 | chip18 | D1652C218B613936 | 0~127 | +1 | flash_prep (batch 20261004T003236Z) |  |
