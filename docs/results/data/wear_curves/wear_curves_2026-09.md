# wear_curves_2026-09 — 교정 칩의 섹터별 소거·프로그램 시간 곡선 (수명 역산 교정 표)

> 수치와 규칙만 둔다. 모델과 판정은 역산 해석 문서(작성 예정)에서 한다.

- **무엇**: 파일럿 chip01(0 → 300k)과 종단 chip03·chip04·chip07 · 교정 chip09 · 새 배치 chip18(0 → 100k, 2026-10-04)의 마모 루프 A 행(사이클 × 섹터 7개의
  소거·프로그램 시간)을 **1,000사이클 구간 × 섹터**로 묶은 분위수 표. 칩당 CSV 한 장 `wear_curves_<chip>_2026-09.csv`.
  수명 역산 모델(S-1 §15 두 층 역산)이 읽는 유일한 교정 입력이다 — A.txt(666MB, 리포 밖)를 다시 열지 않는다
- **왜 이 묶음인가**: 결과 문서 네 편의 §3-§5 가 같은 묶음(`(cycle−1)//1000` 구간 · 섹터 중앙값)으로 계단·프로그램 상승을
  읽었다. 그 집계는 일회성 코드였고, 이 표가 그 정본이다. 분위수 p10·p90 을 더한 것은 블라인드 개봉 prep 이 섹터당
  **한 번의 소거**라 중앙값이 아니라 한 표본이기 때문이다 — 구간 안 산포가 곧 한 표본의 기대 흔들림이다
- **생산**: `host/analysis/wear_curves.py` → `build/data/wear_curves_<chip>.csv`. 사람이 이 폴더(`docs/results/data/wear_curves/`)로 옮기며 이름에 `_2026-09` 를 붙인다.
  **2026-10-03 부터 교정 = 접미사 없는 이름** `wear_curves_<chip>_<YYYY-MM>.csv`(달은 마지막 체크포인트) — `wear_inverse.py`·`plot_wear_curves.py` 의 glob 이
  `wear_curves_chip[0-9][0-9]_20[0-9][0-9]-[0-9][0-9].csv` 다. 교정 밖은 접미사(`_65C` 온도 · `_ali` · `_nocal`). `host/analysis/pe_end.py` 가 이름을 붙인다(워크플로 13)
- **짝 그림**: `../../plots/wear_curves_<chip>_<YYYY-MM>.png` — 교정 칩마다 한 장(2026-10-02 부터 · 지금 chip01·03·04·07·09·18), 섹터 0-6 의 소거
  p50 선과 p10-p90 띠. y 는 모든 장이 같다(전 칩 p90 최대) — 나란히 놓으면 무리 사이 절대값 차이가 보인다. x 는 칩별(chip01 만 300k).
  표에 없는 구간은 선을 끊었다. 9월 4칩을 한 장에 담은 2×2 `../../plots/wear_curves_2026-09.png` 는 그때의 기록으로 둔다(10/2 보고서 재료가 가리킨다)
- **짝 그림 2**: `../../plots/wear_ratio_curves_2026-10.png` — 교정 5칩의 섹터 0-6 p50 중앙값 ÷ 신품값(집계표), 무리별 두 칸, 0-100k. 빠른 칸의 점선은
  chip06 블라인드 관측 배율 1.63. `plot_wear_curves.py --ratio --mark 1.63 --mark-label '…'`
  **그 그림은 10/2 교정 5칩의 기록으로 둔다**(블라인드 chip06 · 보고서 재료가 가리킨다). 현행 교정 묶음은 `../../plots/wear_ratio_curves_calib.png`
  — 칸은 교정 glob 의 칩을 무리별로 신품 소거 내림차순, `pe_end.py --promote` 가 교정 칩이 들 때마다 다시 그린다(2026-10-04, 지금 6칩)

## 교정 밖 — 온도 칩

`wear_curves_chip17_65C_2026-10.csv` 는 chip17 을 **칩 위 약 65°C** 에서 0 → 100k 마모한 같은 묶음의 표다(박지민 보드 B, 세션
`1790851785` · `1790879592`, A 행 700,000 · 뺀 사이클 없음). 이름의 `_65C` 접미사가 교정 glob 에 걸리지 않게
한다 — **교정 칩이 아니다**. 수치는 `../wear/wear_endurance_chip17_2026-10.md` §2, 교정에 넣었을 때의 LOCO 는 `../chip17_loco_2026-10.md`.

## 열

| 열 | 뜻 |
|---|---|
| `chip` | 라벨 (`docs/chip_registry.md`) |
| `bin_start` · `bin_end` | 구간, 닫힌 사이클 범위 (1-1,000 · 1,001-2,000 · …). x 축은 tally 눈금 |
| `sector` | 0-6 (마모 그룹) |
| `n` | 그 칸의 A 행 수. 1,000 미만이면 공백·결측·구간 끝 |
| `erase_us_p10` · `_p50` · `_p90` | 소거 시간 분위수 (µs) |
| `program_us_p10` · `_p50` · `_p90` | 프로그램 시간 분위수 (µs) — 0x00 프로그램. prep(PRBS)과는 눈금이 다르다(chip07 §8) |

## 정제 규칙 (칩별)

공통: 체크섬이 깨진 행은 버린다. 같은 (사이클, 섹터)가 두 세션에 있으면 **뒤 세션**(되돌려 재개한 쪽)이 이긴다 — x 축이 tally 를 따르기
때문이다. 값으로는 거르지 않고 아래 명시한 사이클만 뺀다.

| 칩 | 세션 (시간 순) | 뺀 사이클 | 근거 |
|---|---|---|---|
| chip01 | `1790091548` · `1790212214` | 없음 | 122,164 `wip_timeout`(타이머 넘침) 뒤 재개. 섹터 6 재소거 ±1 은 A 행이 아니다 (`../wear/wear_pilot_chip01_2026-09.md`) |
| chip03 | `1790408609` | 없음 | 정상 종료 (`../wear/wear_endurance_chip03_2026-09.md`) |
| chip04 | `1790423530` · `1790482991` · `1790491294` | **66,654-66,671** | SPI 접촉 불량 — 소거 8µs · 프로그램 130µs 행 120개. 66,601-66,653 은 두 번 돌아 재개 세션 값 (`../wear/wear_endurance_chip04_2026-09.md` §8) |
| chip07 | `1790494073` · `1790562456` · `1790643103` | 없음 | 52,671-60,000 · 76,170-80,000 은 호스트 사망으로 A 행 자체가 없다 → 그 구간은 표에 없거나 `n` 이 작다 (`../wear/wear_endurance_chip07_2026-09.md` §6) |
| chip18 | `1790989701` | 없음 | 끊김 · 재개 없는 첫 종단 (`../wear/wear_endurance_chip18_2026-10.md`) |

## 재현

```bash
uv run python host/analysis/wear_curves.py --chip chip01 data/wear/1790091548 data/wear/1790212214
uv run python host/analysis/wear_curves.py --chip chip03 data/wear/1790408609
uv run python host/analysis/wear_curves.py --chip chip04 data/wear/1790423530 data/wear/1790482991 data/wear/1790491294 --drop-cycles 66654-66671
uv run python host/analysis/wear_curves.py --chip chip07 data/wear/1790494073 data/wear/1790562456 data/wear/1790643103
uv run python host/analysis/wear_curves.py --chip chip09 data/wear/1790786787 -o docs/results/data/wear_curves/wear_curves_chip09_2026-09.csv
uv run python host/analysis/pe_end.py --chip chip18                       # → build/pe_end/chip18/wear_curves_chip18_2026-10.csv, --promote 로 승격
uv run python host/analysis/plot_wear_curves.py --per-chip build/plots   # 교정 CSV 마다 → build/plots/wear_curves_<chip>_2026-09.png
uv run python host/analysis/plot_wear_curves.py   # 9월 4칩 2×2 → build/plots/wear_curves_2026-09.png
uv run python host/analysis/wear_curves.py --chip chip17 data/wear/1790851785 data/wear/1790879592 -o docs/results/data/wear_curves/wear_curves_chip17_65C_2026-10.csv   # 교정 밖 (65°C)
```

각 명령이 stdout 에 읽은 행 수 · 깨진 행 수 · `n<1000` 구간을 찍는다. 그 줄을 아래 표에 옮긴다.

## 실행 기록

| 칩 | A 행 | 깨진 행 | `n<1000` 구간 | 실행일 |
|---|---|---|---|---|
| chip01 | 2,100,000 (cycle 1-300,000) | 0 | 없음 | 2026-09-30 |
| chip03 | 700,000 (cycle 1-100,000) | 0 | 없음 | 2026-09-30 |
| chip04 | 699,874 (cycle 1-100,000) | 0 | 1개: 66,001-67,000 (섹터당 n 982) | 2026-09-30 |
| chip07 | 621,872 (cycle 1-100,000) | 0 | 2개: 52,001-53,000 (n 670, 섹터 6 669) · 76,001-77,000 (n 169). 53,001-60,000 · 77,001-80,000 구간 10개는 표에 없음 | 2026-09-30 |
| chip09 | 700,000 (cycle 1-100,000) | 0 | 없음. 파일 이름의 2026-09 는 교정 묶음 이름(마모는 2026-09-30 - 10-01) | 2026-10-01 |
| chip18 | 700,000 (cycle 1-100,000) | 0 | 없음 | 2026-10-04 |
