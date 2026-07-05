# fpga/rtl/core

**소유자: 한영웅** — 타인 수정은 PR로만.

측정의 심장. MMCM 동적 위상 제어(PSEN/PSINCDEC), 위상 스윕 FSM, AXI-Lite 레지스터 파일.
판별: "언제 샘플링하고 측정을 어떻게 제어하나"를 다루면 여기.

## TODO

- [ ] MMCM 동적 위상 제어 모듈
- [ ] 위상 스윕 FSM
- [ ] AXI-Lite 레지스터 파일 (`docs/interface/` 레지스터 맵 준수)
- [ ] G0: 루프백 욕조 곡선 실증
