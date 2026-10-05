# results — 보고서·발표 게재물

`docs/results/` 에 있다는 것 자체가 "게재한다" 는 선언이다. 사람이 `build/` 에서 골라 승격하고, 생산 스크립트는
여기에 직접 쓰지 않는다 (`docs/CONTRIBUTING.md`).

| 자리 | 무엇 | 규칙 |
|---|---|---|
| 바로 아래 `*.md` · `wear/` | **해석** — 결론, 가설 판정, 한계, 보고서 문장. 칩마다 한 편씩 쌓이는 마모 결과만 `wear/`, 나머지는 바로 아래 | 표를 다시 싣지 않고 `data/` 를 인용한다 |
| `data/` | **수치** — 파싱한 요약 CSV + 동명 md(유래·조건·표·재현 명령) | 해석을 쓰지 않는다. 칩마다 쌓이는 두 계열만 폴더(아래), 나머지는 바로 아래. `_reads` 원본은 올리지 않는다(리포 루트 `data/` 에 보관) |
| `plots/` | 그림 | 짝 데이터의 md 에서 가리킨다 |
| `captures/` | 화면·사진 증거 | 동명 md — 어느 게이트의 증거인지는 md 에 |
| `reports/` | 보고서 재료 — 본문에 옮길 숫자·표를 출처와 함께 · 계획서 원본 | 해석의 정본은 각 출처 문서 |

하위 문서가 2-3개뿐인 폴더는 두지 않는다 (2026-10-02 — 그 전엔 `data/` 를 축마다 나눴다). 폴더로 남은 것:

| 폴더 | 무엇 |
|---|---|
| `wear/` | 마모 결과 해석 — 칩마다 한 편 (파일럿 chip01 · 종단 chip03·04·07 · 온도 chip17 · 구매처 미검증 chip12 · 새 배치 chip18·15) |
| `data/wear/` | 마모 체크포인트 요약 — 칩마다 CSV + md (chip01 · 03 · 04 · 07 · 09 · 12 · 15 · 17 · 18). 칩 × 체크포인트 한눈 표 `wear_checkpoint_table_2026-10.md` 와 폭 변화·프로그램 칩 간 그림 `plots/wear_checkpoint_width_program_2026-10.png` (둘 다 `wear_checkpoint_table.py` 산출) |
| `data/wear_curves/` | 수명 역산 교정 표 — A 행을 1k 구간 × 섹터로 묶은 분위수 (`wear_curves.py` 산출). 교정 = 접미사 없는 `wear_curves_<chip>_<YYYY-MM>.csv`, 교정에 안 넣는 칩은 접미사로 glob 에서 뺀다(chip17 `_65C` · chip12 `_ali` · `pe_end.py --no-calib` 은 `_nocal`) |

`data/` 바로 아래: 몬테카를로 사전 등록(`monte_carlo_*`) · 단일 스윕(`sweep_*` — 7월 chip01 반복 5회 · G0 루프백) · 신품 전수
집계표(`newchip_survey_2026-09.*`) · 블라인드 추정(`blind_chip06_2026-10.md` · `chip06_estimate_*.txt` — 개봉 전 커밋한 것 그대로) ·
역산 모델 검증(`synthetic_recovery_*` · `chip17_loco_*` · v3 전 탐색 `inverse_v3_probe_2026-10.md` — Δx · R · 대표값) · 온도 마모 런의 칩 위 온도(`temp_chip17_*`).

이 구분은 2026-09-26 부터다. 그 전에 올린 `data/` 의 md 중 `newchip_survey_2026-09.md` 는 같은 날 나눴고, 나머지(7월·8월분)는
짧은 유래 문서라 그대로 둔다.

## 해석 문서

- [`newchip_survey.md`](newchip_survey.md) — 신품 전수 측정(S-2) n=9: 소거 시간 개체차, 재장착 σ 13.86ps, chip10 개체 특성, 앵커 chip02 고장
- [`wear_pilot_chip01.md`](wear/wear_pilot_chip01.md) — P/E 파일럿 chip01 0 → 300k: 폭 불변(H1), 소거 5.2배(H2), 섹터별 계단
- [`wear_endurance_chip03.md`](wear/wear_endurance_chip03.md) — 종단 chip03 0 → 100k: 폭 불변(H1′), 프로그램 20k 부터(H2′ 거짓), 계단 없음, 근접 대조군 128KB 교란
- [`wear_endurance_chip04.md`](wear/wear_endurance_chip04.md) — 종단 chip04 0 → 100k: 폭 불변(H1′), 프로그램 불변(H2′ 참), 7섹터 계단 25-47k·높이 18.5-22.7ms·착지 약 111ms(H6 참), H4 거짓, 128KB 교란 가장 큼
- [`wear_endurance_chip07.md`](wear/wear_endurance_chip07.md) — 종단 chip07 0 → 100k: 계단 없음(예측 참), 프로그램 5k 부터 2.1배(H2′ 거짓), 폭 25MHz 불변(계측 사건 전후 사후 처리 · 75/45MHz 판정 불가), 60k·80k 결측, 128KB 소거 교란 재현, prep 프로그램 시간은 A 행과 눈금이 다름
- [`wear_endurance_chip12.md`](wear/wear_endurance_chip12.md) — 구매처 미검증 chip12(알리익스프레스) 0 → 100k: 같은 칩으로 보지 않는다 — 소거 2.58배로 빠른 무리만큼 늘었지만 계단 없음, 프로그램은 그대로(느린 무리와 다름), 폭 불변(재장착 단차 약 30ps 포함), 기준 섹터 0.99, 현장 역산은 판정 보류(입력 C 불일치 · 밴드 밖)
- [`wear_endurance_chip18.md`](wear/wear_endurance_chip18.md) — 새 배치 chip18(빠른 무리) 0 → 100k: 옛 로트 빠른 무리 띠 안 — 소거 100k 3.68배, 5/7섹터 53-100k 계단(H6 참 · 높이 19.7-23.1ms), 프로그램·폭 불변(H1′·H2′ 참), 교정 편입 — 넣기 전 현장 역산은 MAP 54k 로 낮게 봄, 교정 6칩 LOCO 68% 60/70 · 95% 70/70
- [`wear_endurance_chip15.md`](wear/wear_endurance_chip15.md) — 새 배치 chip15(느린 무리) 0 → 100k: 옛 로트 느린 무리처럼 — 소거 100k 1.75배(chip03 1.74 와 겹침), 계단 없음(H6 판정 불가), 프로그램 24-37k 부터 7섹터 함께 +21%(H2′ 거짓 · 느린 무리 세 칩째), 폭 25MHz 불변(H1′ 참), 69,109 USB 사건(결측 없음), 교정 편입 — 넣기 전 현장 역산 MAP 62k(95% 안) · 입력 C 경고 헛울림, 교정 7칩 LOCO 68% 72/82 · 95% 82/82
- [`wear_temperature_chip17.md`](wear/wear_temperature_chip17.md) — 온도 마모 chip17 칩 위 65°C 0 → 100k: 폭 불변(H1′ 참), 소거는 상온 빠른 무리보다 덜 늘어 100k 2.44배(상온 2.80-3.97) — 65°C 효과는 개체차와 구별 불가·계단 없음(H6 수준 미달), 프로그램 +20%(H2′ 거짓), 상온 모델 v2 는 사용량을 0.15-0.35배로 낮게 봄(LOCO 68% 2/12) → 교정에 넣지 않음
- [`blind_chip06.md`](blind_chip06.md) — 블라인드 chip06 정답 12,000: 판정용 v2 가 68%·95% 구간에 품음(49번째 백분위), 기준 ①② 통과 · ③ 불통과, 교정 4칩 v1 은 68% 밖
