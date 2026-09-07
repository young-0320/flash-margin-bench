# sim

시뮬레이터에서 도는 것 전부. RTL을 Python으로 검증하는 경계 영역이라 `fpga/`에도 `host/`에도 넣지 않고 독립.

소유 분할 — 타인 영역 수정은 PR로만:

- `tb/` — **팀원 A**: cocotb 환경, Winbond 행동 모델 통합, 회귀 실행
- `golden/` — **한영웅**: golden model(몬테카를로)
- `smoke/` — **한영웅**: 블록 단위 스모크 TB (iverilog 순수 Verilog, cocotb 회귀 확립 전 임시 최소 회귀)
- `check_coverage.py` — **한영웅**: 회귀가 합격 기준 23항목을 다 덮었는지 대조. 기준 쪽 산출물이라 채점 대상(`tb/`)과 소유를 분리한다

회귀 승인 기준은 한영웅의 테스트 계획 문서 — `docs/spec/s3.g1_test_plan.md` (**2026-08-23 동결, 같은 날 개정 2**).
판정은 3단이다 — ① 어서션이 기준을 재는가(한영웅) → ② 회귀 통과 여부(자동) → ③ 블록 승인 집행(팀원 A).
①의 기록은 `docs/spec/s3.g1_review.md`에 누적한다.
테스트 함수명은 `test_<항목ID>_<설명>` 규약을 따를 것. 어기면 커버리지 대조에서 보이지 않는다(기준 문서 §4).

커버리지 대조 실행:

```
python3 sim/check_coverage.py --results sim/build/results.xml
# 계약 수정안 #1(BASE_SECTOR) 승인 후에는 --amendment1 을 붙여 F11·F12 를 포함시킨다
```

## TODO

- [x] [한영웅] 테스트 계획 문서 (팀원 A의 회귀 승인 기준) — `docs/spec/s3.g1_test_plan.md`
- [ ] [팀원 A] cocotb 환경 구축 (`tb/`)
- [x] [한영웅] `check_coverage.py` — 항목 ID 대조 스크립트 (2026-08-23)
- [ ] [팀원 A] Winbond 행동 모델 통합 (W25Q64 접미 확정 후 모델 파일 선택)
- [ ] [한영웅] golden model 연동 (`golden/`)
