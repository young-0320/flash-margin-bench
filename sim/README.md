# sim

**소유자: 한영웅** (프레임워크·golden model) — 타인 수정은 PR로만. 회귀 실행·승인은 팀원 A.

시뮬레이터에서 도는 것 전부: cocotb 프레임워크, Winbond 행동 모델, golden model, 테스트 계획.
RTL을 Python으로 검증하는 경계 영역이라 `fpga/`에도 `host/`에도 넣지 않고 독립.

## TODO

- [ ] cocotb 환경 구축
- [ ] 테스트 계획 문서 (팀원 A의 회귀 승인 기준 — 우선 작성)
- [ ] Winbond 행동 모델 통합 (W25Q64 접미 확정 후 모델 파일 선택)
- [ ] golden model 연동
