# wear_curves_2026-09 — 마모 4칩의 섹터별 소거·프로그램 시간 곡선 (수명 역산 교정 표)

> 수치와 규칙만 둔다. 모델과 판정은 역산 해석 문서(작성 예정)에서 한다.

- **무엇**: 파일럿 chip01(0 → 300k)과 종단 chip03·chip04·chip07(0 → 100k)의 마모 루프 A 행(사이클 × 섹터 7개의
  소거·프로그램 시간)을 **1,000사이클 구간 × 섹터**로 묶은 분위수 표. 칩당 CSV 한 장 `wear_curves_<chip>_2026-09.csv`.
  수명 역산 모델(S-1 §15 두 층 역산)이 읽는 유일한 교정 입력이다 — A.txt(666MB, 리포 밖)를 다시 열지 않는다
- **왜 이 묶음인가**: 결과 문서 네 편의 §3-§5 가 같은 묶음(`(cycle−1)//1000` 구간 · 섹터 중앙값)으로 계단·프로그램 상승을
  읽었다. 그 집계는 일회성 코드였고, 이 표가 그 정본이다. 분위수 p10·p90 을 더한 것은 블라인드 개봉 prep 이 섹터당
  **한 번의 소거**라 중앙값이 아니라 한 표본이기 때문이다 — 구간 안 산포가 곧 한 표본의 기대 흔들림이다
- **생산**: `host/analysis/wear_curves.py` → `build/data/wear_curves_<chip>.csv`. 사람이 이 폴더(`docs/results/data/wear_curves/`)로 옮기며 이름에 `_2026-09` 를 붙인다
- **짝 그림**: `../../plots/wear_curves_2026-09.png` — 칩별 칸(윗줄 빠른 무리 chip01·04 · 아랫줄 느린 무리 chip03·07), 섹터 0-6 의 소거 p50 선과
  p10-p90 띠. y 는 네 칸 공유(ms), x 는 칩별(chip01 만 300k). 표에 없는 구간은 선을 끊었다

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

## 재현

```bash
uv run python host/analysis/wear_curves.py --chip chip01 data/wear/1790091548 data/wear/1790212214
uv run python host/analysis/wear_curves.py --chip chip03 data/wear/1790408609
uv run python host/analysis/wear_curves.py --chip chip04 data/wear/1790423530 data/wear/1790482991 data/wear/1790491294 --drop-cycles 66654-66671
uv run python host/analysis/wear_curves.py --chip chip07 data/wear/1790494073 data/wear/1790562456 data/wear/1790643103
uv run python host/analysis/wear_curves.py --chip chip09 data/wear/1790786787 -o docs/results/data/wear_curves/wear_curves_chip09_2026-09.csv
uv run python host/analysis/plot_wear_curves.py   # 승격한 CSV 4장 → build/plots/wear_curves_2026-09.png
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
