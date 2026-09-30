# results — 보고서·발표 게재물

`docs/results/` 에 있다는 것 자체가 "게재한다" 는 선언이다. 사람이 `build/` 에서 골라 승격하고, 생산 스크립트는
여기에 직접 쓰지 않는다 (`docs/CONTRIBUTING.md`).

| 자리 | 무엇 | 규칙 |
|---|---|---|
| 바로 아래 `*.md` | **해석** — 결론, 가설 판정, 한계, 보고서 문장 | 표를 다시 싣지 않고 `data/` 를 인용한다 |
| `data/` | **수치** — 파싱한 요약 CSV + 동명 md(유래·조건·표·재현 명령) | 해석을 쓰지 않는다. `_reads` 원본은 올리지 않는다(리포 루트 `data/` 에 보관) |
| `plots/` | 그림 | 짝 데이터의 md 에서 가리킨다 |
| `captures/g<N>/` | 화면·사진 증거 | 파일명에서 게이트 접두 생략, 동명 md |

이 구분은 2026-09-26 부터다. 그 전에 올린 `data/` 의 md 중 `newchip_survey_2026-09.md` 는 같은 날 나눴고, 나머지(7월·8월분)는
짧은 유래 문서라 그대로 둔다.

## 해석 문서

- [`newchip_survey.md`](newchip_survey.md) — 신품 전수 측정(S-2) n=9: 소거 시간 개체차, 재장착 σ 13.86ps, chip10 개체 특성, 앵커 chip02 고장
- [`wear_pilot_chip01.md`](wear_pilot_chip01.md) — P/E 파일럿 chip01 0 → 300k: 폭 불변(H1), 소거 5.2배(H2), 섹터별 계단
- [`wear_endurance_chip03.md`](wear_endurance_chip03.md) — 종단 chip03 0 → 100k: 폭 불변(H1′), 프로그램 20k 부터(H2′ 거짓), 계단 없음, 근접 대조군 128KB 교란
- [`wear_endurance_chip04.md`](wear_endurance_chip04.md) — 종단 chip04 0 → 100k: 폭 불변(H1′), 프로그램 불변(H2′ 참), 7섹터 계단 25-47k·높이 18.5-22.7ms·착지 약 111ms(H6 참), H4 거짓, 128KB 교란 가장 큼
- [`wear_endurance_chip07.md`](wear_endurance_chip07.md) — 종단 chip07 0 → 100k: 계단 없음(예측 참), 프로그램 5k 부터 2.1배(H2′ 거짓), 폭 25MHz 불변(계측 사건 전후 사후 처리 · 75/45MHz 판정 불가), 60k·80k 결측, 128KB 소거 교란 재현, prep 프로그램 시간은 A 행과 눈금이 다름
