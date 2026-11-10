# host/analysis

**소유자: 한영웅** — 타인 수정은 PR로만.

측정·분석의 두뇌 (PC Python). 스윕 자동화, 교정 곡선, 오차 정량화.

## TODO

- [x] 몬테카를로 golden model (1-1 → 1-3) — `host/analysis/monte_carlo_sweep_params.py`
- [x] sweep_runner (시나리오 자동화) — `host/run/run_sweep_chip.py` (host/run 에 있다)
- [x] 교정 곡선(band) 구축 — `host/analysis/wear_curves.py` · `host/analysis/wear_inverse.py`
- [x] 개체 산포 σ vs 노화 이동량 Δ 분리 — `host/analysis/wear_inverse.py`
- [x] 블라인드 추정 오차 정량화 — `host/analysis/inverse_learning_curve.py` · `host/analysis/baseline_compare.py`
