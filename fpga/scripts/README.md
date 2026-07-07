# fpga/scripts

**소유자: 팀원 A** — 타인 수정은 PR로만.

Vivado 프로젝트 재생성 스크립트. `.xpr`이 아니라 tcl이 소스다. 생성물은 `build/`로 (커밋 금지).

## TODO

- [x] build_g0_loopback.tcl — 프로젝트 생성 → BD → 합성 → 구현 → 비트스트림·XSA → ELF 체인 (G0, 로그 8)
