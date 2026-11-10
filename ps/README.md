# ps

**소유자: 팀원 B** — 타인 수정은 PR로만.

Zynq ARM 코어에서 도는 베어메탈 C + vitis tcl. "PS는 얇게" — PC 명령을 PL 레지스터로 중계하는 최소 로직만.

## TODO

- [ ] UART 에코 서버 (Zynq 단독 — PL 주소 맵 확정 전 착수 가능, 공백 방지)
- [x] UART 명령 서버 (`docs/interface/` 프로토콜 준수) — `ps/src/flash_wear.c`
- [ ] 온도 PID
- [x] JEDEC ID 식별 — `ps/src/flash_jedec.c`
- [x] vitis tcl (.xsa 소비 → 플랫폼/앱 재생성) — `ps/scripts/build_flash_wear.py` · `ps/scripts/build_g0_sweep.py` (Vitis Python CLI)
