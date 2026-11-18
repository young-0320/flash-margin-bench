# bathtub — 욕조 곡선 그림

버전은 **측정 방식**(펌웨어가 위상 스텝마다 읽기를 어떻게 배치하나)으로 나눈다. 같은 데이터를 축만 바꿔 다시 그린 그림은 그 데이터의 버전에 둔다.

| 버전 | 측정 방식 | 기간 |
|---|---|---|
| `v1/` | 위상 전 구간을 같은 간격 · 같은 읽기 수로 스윕 (`bathtub_analysis.py` 산출, 계약 v1 CSV) | 2026-07 - 2026-11 |
| `v2/` | 벽 집중 측정 — 가운데를 건너뛰고 양쪽 벽에 읽기를 몰아 깊은 BER 까지 본다. 11/2 교수님 피드백 ([로그 55](../../../log/young/55.professor_feedback_bathtub_2026-11-02.md)) | 2026-11-17 - |

## `v1/walls_zoom/` — v1 데이터를 가운데 바닥을 잘라 두 벽만 키워 다시 그림 (2026-11-17)

11/2 교수님 피드백 1 · 2 · 4 형식([D55-3]) — 가운데 바닥은 잘라 길이만 적고, 양쪽 벽을 1,000ps 폭으로 키워 그린다. 데이터는 v1 그대로(칩 31 · 런 393, 25MHz)라 `v1/` 아래에 둔다. 산출 `host/analysis/bathtub_p1_figures.py` → `build/bathtub/v1/`.

- `p1_chip_<chip>.png` — 칩마다 전 런(옅은 선) + 칩 평균(진한 선)
- `p1_run_chip01_20260708T164931Z.png` — 게재 런 한 장
- `p1_walls_chip01_20260708T164931Z.png` — 같은 런의 좌우 벽 겹침

벽이 1,000ps 창보다 긴 런 37개(chip10 · 14 · 32-35 · 39)는 그림에 「잘림」 경고가 붙는다. 발표에 쓸지는 정하지 않았다.

## `v2/` — 욕조 v2 첫 실칩 (2026-11-17)

chip02 섹터 0, 25MHz `std` — 수정안 #4 A4 런(`bathtub2_chip02_D1642C74E7134527_20261117T142542Z`). 산출 `host/analysis/bathtub2_analysis.py` → `build/bathtub/v2/`. A4 · A5 를 통과해 에지별 그림을 쓸 수 있다(S-6 §5). 수치 · 해석은 `docs/results/bathtub_v2_chip02.md`.

- `bathtub_v2_chip02_s0_20261117T142542Z_p1.png` — 끊긴 축 욕조. 벽 집중(천장 N 112 · 벽 N 8,064)이 BER 약 2e-7 까지, 1회 훑기는 약 1.5e-3 까지
- `bathtub_v2_chip02_s0_20261117T142542Z_edges.png` — 에지별 도착 분포(CDF · pdf) — 상승 · 하강이 갈라진다, DCD 163.6ps
- `bathtub_v2_chip02_s0_deep_20261118T034128Z_p1.png` · `bathtub_v2_chip02_s64_deep_20261118T074821Z_p1.png` — 초심부(벽 N 2,064,384) 섹터 0 · 64. 벽 바깥 오류 0 칸이 BER 7.1e-10 미만, 안쪽 드문 오류는 2e-8 까지 직접 (11/18)
- `…_s0_deep_20261118T034128Z_edges.png` · `…_s64_deep_20261118T074821Z_edges.png` — 같은 런의 에지 분포. 상승 도착의 99% 가 한 칸에 들어, 상승 폭 1.9-2.3ps 는 격자 위치를 읽은 값이다 (결과 문서 「초심부」 절)
- `bathtub_v2_chip03_s0_20261118T130721Z_p1.png` · `…_edges.png` — 둘째 칩 chip03(느린 무리) 섹터 0 표준 런. DCD 304ps, 하강 에지가 두 봉우리 (결과 `docs/results/bathtub_v2_chip03.md`)
- `bathtub_v2_wear_compare_chip02_chip03.png` — 발표용 한 장: 두 칩의 창 8곳 DCD(런별 · 창 평균)와 안 닳은 6창 95% 예측 구간 — 닳은 창이 두 칩 모두 구간 안, 차이 −0.99 · +0.45ps. 산출 `host/analysis/bathtub2_wear_figure.py` (11/18)
