# results — 보고서·발표 게재물

`docs/results/` 에 있다는 것 자체가 "게재한다" 는 선언이다. 사람이 `build/` 에서 골라 승격하고, 생산 스크립트는
여기에 직접 쓰지 않는다 (`docs/CONTRIBUTING.md`).

| 자리 | 무엇 | 규칙 |
|---|---|---|
| 바로 아래 `*.md` · `wear/` | **해석** — 결론, 가설 판정, 한계, 보고서 문장. 칩마다 한 편씩 쌓이는 마모 결과만 `wear/`, 나머지는 바로 아래 | 표를 다시 싣지 않고 `data/` 를 인용한다 |
| `data/` | **수치** — 파싱한 요약 CSV + 동명 md(유래·조건·표·재현 명령) | 해석을 쓰지 않는다. 칩마다 쌓이는 두 계열만 폴더(아래), 나머지는 바로 아래. `_reads` 원본은 올리지 않는다(리포 루트 `data/` 에 보관) |
| `plots/` | 그림 | 짝 데이터의 md 에서 가리킨다 |
| `captures/` | 화면·사진 증거 | 동명 md — 어느 게이트의 증거인지는 md 에 |
| `reports/` | 보고서 재료 — 본문에 옮길 숫자·표를 출처와 함께 · 계획서 원본 · 최종 발표 대본 초안(`최종발표대본초안.md`) | 해석의 정본은 각 출처 문서 |

하위 문서가 2-3개뿐인 폴더는 두지 않는다 (2026-10-02 — 그 전엔 `data/` 를 축마다 나눴다). 폴더로 남은 것:

| 폴더 | 무엇 |
|---|---|
| `wear/` | 마모 결과 해석 — 칩마다 한 편 (파일럿 chip01 · 종단 chip03·04·07 · 온도 chip17·16 · 구매처 미검증 chip12 · 새 배치 chip18·15 · JV chip10·14) · 200k 연장은 한 편(`wear_endurance_200k.md`, chip06 · 09 · 03 · 15 · 21 · 07 · 02) |
| `data/wear/` | 마모 체크포인트 요약 — 칩마다 CSV + md (chip01 · 03 · 04 · 07 · 09 · 10 · 12 · 15 · 17 · 18). 칩 × 체크포인트 한눈 표 `wear_checkpoint_table_2026-10.md` 와 폭 변화·프로그램 칩 간 그림 `plots/wear_checkpoint_width_program_2026-10.png` (둘 다 `wear_checkpoint_table.py` 산출) |
| `data/wear_curves/` | 수명 역산 교정 표 — A 행을 1k 구간 × 섹터로 묶은 분위수 (`wear_curves.py` 산출). 교정 = 접미사 없는 `wear_curves_<chip>_<YYYY-MM>.csv`, 교정에 안 넣는 칩은 접미사로 glob 에서 뺀다(chip17 `_65C` · chip16 `_64C` · chip12 `_ali` · `pe_end.py --no-calib` 은 `_nocal`) |

`data/` 바로 아래: 몬테카를로 사전 등록(`monte_carlo_*`) · 단일 스윕(`sweep_*` — 7월 chip01 반복 5회 · G0 루프백) · 신품 전수
집계표(`newchip_survey_2026-09.*`) · 블라인드 추정(`blind_chip06_2026-10.md` · `chip06_estimate_*.txt` — 개봉 전 커밋한 것 그대로) ·
칩별 0 → 100k 추이 표(`wear_curves/wear_erase_trajectory_2026-10.md` · `wear_program_trajectory_2026-10.md` — 빠른 · 느린 무리, 1k 구간 중앙값과 배율) · 역산 모델 검증(`synthetic_recovery_*` · `chip17_loco_*` · `chip16_loco_*` · v3 전 탐색 `inverse_v3_probe_2026-10.md` — Δx · R · 대표값 · v4 부분 탐색 `inverse_v4_probe_2026-10.md` — 정렬 · R 유도 · n_eff · v4 등록 측정 `inverse_v4_eval_2026-10.md` — ρ · LOCO · 합성 · 칩별 · v4.1 측정 `inverse_v4_1_eval_2026-10.md` — chip06 을 더한 9칩으로 같은 측정 · v4.3 5장 판 `inverse_v4_3_eval_2026-10.md` — 100k 너머 곡선 5장, 68% 개선 · 점 추정 절단 편향 확인) · 기준선 비교(`baseline_compare_2026-10.md`) · 온도 마모 런의 칩 위 온도(`temp_chip17_*`).

이 구분은 2026-09-26 부터다. 그 전에 올린 `data/` 의 md 중 `newchip_survey_2026-09.md` 는 같은 날 나눴고, 나머지(7월·8월분)는
짧은 유래 문서라 그대로 둔다.

## 해석 문서

- [`newchip_survey.md`](newchip_survey.md) — 신품 전수 측정(S-2) n=9: 소거 시간 개체차, 재장착 σ 13.86ps, chip10 개체 특성, 앵커 chip02 고장
- [`wear_pilot_chip01.md`](wear/wear_pilot_chip01.md) — P/E 파일럿 chip01 0 → 300k: 폭 불변(H1), 소거 5.2배(H2), 섹터별 계단
- [`wear_endurance_chip03.md`](wear/wear_endurance_chip03.md) — 종단 chip03 0 → 100k: 폭 불변(H1′), 프로그램 20k 부터(H2′ 거짓), 계단 없음, 근접 대조군 128KB 교란 (100k → 200k 는 `wear_endurance_200k.md` §6)
- [`wear_endurance_chip04.md`](wear/wear_endurance_chip04.md) — 종단 chip04 0 → 100k: 폭 불변(H1′), 프로그램 불변(H2′ 참), 7섹터 계단 25-47k·높이 18.5-22.7ms·착지 약 111ms(H6 참), H4 거짓, 128KB 교란 가장 큼
- [`wear_endurance_chip07.md`](wear/wear_endurance_chip07.md) — 종단 chip07 0 → 100k: 계단 없음(예측 참), 프로그램 5k 부터 2.1배(H2′ 거짓), 폭 25MHz 불변(계측 사건 전후 사후 처리 · 75/45MHz 판정 불가), 60k·80k 결측, 128KB 소거 교란 재현, prep 프로그램 시간은 A 행과 눈금이 다름
- [`wear_endurance_chip12.md`](wear/wear_endurance_chip12.md) — 구매처 미검증 chip12(알리익스프레스) 0 → 100k: 같은 칩으로 보지 않는다 — 소거 2.58배로 빠른 무리만큼 늘었지만 계단 없음, 프로그램은 그대로(느린 무리와 다름), 폭 불변(재장착 단차 약 30ps 포함), 기준 섹터 0.99, 현장 역산은 판정 보류(입력 C 불일치 · 밴드 밖) — **10/19 추기: 같은 꼴이 chip21(3차 구매, FV 1647)에서 재현돼 구매처가 아니라 종류로 본다(`wear_endurance_200k.md` §8)**
- [`wear_endurance_chip14.md`](wear/wear_endurance_chip14.md) — W25Q64JV 두 번째(마킹 `25Q64JVSIQ` `1749`) chip14 0 → 100k, chip10 과 「JV 둘」: 소거 계단 없이 100k 2.65배(7섹터 모두 84ms 를 넘고도 계단 없음 — H6 는 FV 규칙), 프로그램 1.03, 폭 12점 중 11점 3σ 안(90k 는 창 이동 자리) · 교정 밖 · FV 모델 현장 역산 59-60k(JV 둘 다 약 0.6배로 낮게 봄) · 근접 대조군 1.10 기록
- [`wear_endurance_chip10.md`](wear/wear_endurance_chip10.md) — W25Q64JV(마킹 `25Q64JVSIQ` `1850`, 다른 칩은 FV) chip10 0 → 100k, 한 칩만: 소거 계단 없이 100k 2.55배(85-87ms 포화 가설), 프로그램 1.11배로 늦게 가속(H2′ 거짓), 폭 불변(H1′ 참), 대조군 교란 없음, FV 모델은 사용량을 약 절반으로 봄 — 교정 밖 · 다른 칩과 비교 보류
- [`wear_endurance_chip18.md`](wear/wear_endurance_chip18.md) — 새 배치 chip18(빠른 무리) 0 → 100k: 옛 로트 빠른 무리 띠 안 — 소거 100k 3.68배, 5/7섹터 53-100k 계단(H6 참 · 높이 19.7-23.1ms), 프로그램·폭 불변(H1′·H2′ 참), 교정 편입 — 넣기 전 현장 역산은 MAP 54k 로 낮게 봄, 교정 6칩 LOCO 68% 60/70 · 95% 70/70
- [`wear_endurance_200k.md`](wear/wear_endurance_200k.md) — chip06 · chip09(빠른) · chip03 · chip15(느린) 100k → 200k 연장 · chip21 0 → 200k(역산 답 범위 150k 너머용): 빠른 두 칩은 100k 안에 계단이 없던 12섹터 전부 110k-158k 에 약 21ms 계단(H3 안) · 160k-200k 104-109ms 평탄 · 프로그램 1.9배 / 1.01 로 갈림 · H6 ② 착지 띠는 직전 + 21ms, 느린 chip03 · 15 는 같은 85-93ms 에서 출발해 계단 없이 미끄럼(한 구간 상승 4-12ms · 분포 폭 18-25ms · 배율 2.10 · 2.25, chip03 은 10/14 예측 틀림 · chip15 는 10/16 예측 맞음) — 계단의 유무가 두 무리를 가름, 폭 넷 다 200k 까지 3σ 안, 느린 100k 너머가 두 장이라 LOCO 가능. **chip21 은 신품 48.9ms(느린)인데 빠른 무리 속도(200k 2.93배 · 미끄럼 · 프로그램 불변)로 늙어 chip12 와 같은 꼴 — 느린 신품 5칩 중 2칩, 상온 9칩 모델이 68% 0/12 로 전부 틀림 → 교정에서 뺌(`_nocal`, [D52-12]), v4.3 은 다섯 장으로 답 범위만, 두 종류는 v4.4 [U52-7]**
- [`wear_endurance_chip15.md`](wear/wear_endurance_chip15.md) — 새 배치 chip15(느린 무리) 0 → 100k: 옛 로트 느린 무리처럼 — 소거 100k 1.75배(chip03 1.74 와 겹침), 계단 없음(H6 판정 불가), 프로그램 24-37k 부터 7섹터 함께 +21%(H2′ 거짓 · 느린 무리 세 칩째), 폭 25MHz 불변(H1′ 참), 69,109 USB 사건(결측 없음), 교정 편입 — 넣기 전 현장 역산 MAP 62k(95% 안) · 입력 C 경고 헛울림, 교정 7칩 LOCO 68% 72/82 · 95% 82/82 (100k → 200k 는 `wear_endurance_200k.md` §7)
- [`wear_temperature_chip17.md`](wear/wear_temperature_chip17.md) — 온도 마모 chip17 칩 위 65°C 0 → 100k: 폭 불변(H1′ 참), 소거는 상온 빠른 무리보다 덜 늘어 100k 2.44배(상온 2.80-3.97) — 65°C 효과는 개체차와 구별 불가·계단 없음(H6 수준 미달), 프로그램 +20%(H2′ 거짓), 상온 모델 v2 는 사용량을 0.15-0.35배로 낮게 봄(LOCO 68% 2/12) → 교정에 넣지 않음
- [`wear_temperature_chip16.md`](wear/wear_temperature_chip16.md) — 온도 마모 chip16 히터 설정 65°C(센서 평균 64°C) 0 → 100k: 폭 불변(H1′ 참), 소거는 chip17 과 반대로 상온 빠른 무리의 빠른 쪽(100k 4.34배 · 계단 있음 · 프로그램 불변), 상온 v4 모델이 10/12 맞힘 — 온도 로그가 히터 상태와 안 맞아 칩 온도 미확인 · 교정 밖 [D53-4]
- [`wear_temperature_85C.md`](wear/wear_temperature_85C.md) — 설정 85°C chip24(빠른) · chip22(느린) 0 → 100k: chip24 는 상온 빠른 띠 한가운데(3.47배 · 계단 · 프로그램 불변 · 상온 모델 12/12), chip22 는 상온 느린 띠 위(1.90배 · 68% 3/12 · 95% 12/12) — 65 · 85°C 네 칩 합쳐 개체 산포 안, 상온 모델 95% 47/48 · 68% 22/48, 온도 축 없음
- [`blind_chip06.md`](blind_chip06.md) — 블라인드 chip06 정답 12,000: 판정용 v2 가 68%·95% 구간에 품음(49번째 백분위), 기준 ①② 통과 · ③ 불통과, 교정 4칩 v1 은 68% 밖
- [`baseline_compare.md`](baseline_compare.md) — 기준선 비교(10-07 판 — 교정 8칩 LOCO 94점 · 신품 15칩): 선행식 이진 판별은 데이터시트 기준 검출 64/94(빠른 무리 2만 회 이하 2/20) · 정규화 뒤 74/94(빠른 무리 13/20) · 오경보 0, 단순 회귀 오차 중앙값 10,000 대 현행 모델 7,500 — 점 추정도 현행이 덜 빗나가고(느린 무리만 회귀가 낫다) 차이의 본체는 구간(68% 67/94 · 95% 93/94)
