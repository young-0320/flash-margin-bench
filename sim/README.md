# sim

시뮬레이터에서 도는 것 전부. RTL을 Python으로 검증하는 경계 영역이라 `fpga/`에도 `host/`에도 넣지 않고 독립.

소유 분할 — 타인 영역 수정은 PR로만:

- `tb/` — **팀원 A**: cocotb 환경, Winbond 행동 모델 통합, 회귀 실행
- `golden/` — **한영웅**: golden model(몬테카를로)
- `smoke/` — **한영웅**: 블록 단위 스모크 TB (iverilog 순수 Verilog, cocotb 회귀 확립 전 임시 최소 회귀)

회귀 승인 기준은 한영웅의 테스트 계획 문서. 승인은 팀원 A 몫.

## TODO

- [x] [한영웅] 테스트 계획 문서 (팀원 A의 회귀 승인 기준) — `sim/test_plan.md`
- [ ] [팀원 A] cocotb 환경 구축 (`tb/`)
- [ ] [팀원 A] Winbond 행동 모델 통합 (W25Q64 접미 확정 후 모델 파일 선택)
- [ ] [한영웅] golden model 연동 (`golden/`)
