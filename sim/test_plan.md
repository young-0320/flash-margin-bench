# 테스트 계획 — cocotb 회귀 승인 기준 (한영웅, 2026-07-08)

이 문서가 `sim/README.md`의 "회귀 승인 기준". cocotb 회귀(팀원 A 소유 `tb/`)가
아래 항목을 커버하고 전부 PASS면 해당 블록은 승인이다. 각 항목은 이미
`smoke/`의 iverilog TB로 1회 이상 통과했다 — cocotb는 이를 Winbond 행동 모델
상대로 재현·상시화하는 층이고, 항목 자체가 곧 체크리스트다.

## 대상과 우선순위

1. **flash 블록 + SPI 마스터** (`flash_top_spi` — 게재 4번 임계 경로, 최우선)
2. core 블록 (`core_top` — MMCM은 스텁/모델 대체)
3. 통합 (core+flash, AXI 트랜잭션 레벨)

스왑 지점: `smoke/tb_flash_spi_smoke.v`의 내장 슬레이브(0x0B만 아는 최소 모델)를
**Winbond W25Q64 행동 모델로 교체**하는 것이 cocotb ③의 본질 — 내장 모델이
못 보는 것(명령 오인식에 대한 칩의 실제 반응, tSHSL 위반, mode 경계)이 추가로
검증된다.

## flash_top_spi 승인 항목 (계약 §2·§4·§5 근거)

| #   | 항목                    | PASS 기준                                                                   |
| --- | ----------------------- | --------------------------------------------------------------------------- |
| F1  | 프레임 규격             | cmd=0x0B, addr=페이지 i×256(하위 8비트 0), dummy 8, 프레임당 SCLK 정확히 40+B |
| F2  | mode 0 타이밍           | CS↓ 후 첫 상승 에지까지 ≥tSLCH, CS↑ 간격 ≥tSHSL, SCLK 유휴 low            |
| F3  | 주소→시드 정합         | 읽기 i의 기대 PRBS 시드 {1, i[13:0]} — 모델이 페이지 데이터로 응답 시 에러 0 |
| F4  | 위상 스윕               | clk_sample 위상 0~1UI 전 구간에서 에러 0 (프레이밍 재정렬 절벽 금지)         |
| F5  | 출력 지연 스윕          | 칩 tCLQV 0~1UI 미만 전 구간에서 에러 0. **1UI 초과 시 전 위상 BER 0.5로 실패하는 것도 확인** (PAY_LEAD 재보정 경계의 문서화) |
| F6  | 정확 계수               | 단일 비트 오염 → 해당 e_i=1, err_bits=1, err_reads=1. R8 3항 일치            |
| F7  | R10 워치독              | done 경로 차단 시 T_max=2N(B+64)에 done+timeout 동시 펄스, CS 해제, 이후 정상 복구 |
| F8  | R11 거부                | N=0 / B<8 / B%8≠0 → cfg_err만, busy·done 없음, 이후 정상 복구             |
| F9  | 무칩 서명               | MISO 무응답 → **TIMEOUT 없이 완주 + 에러 = 기대 PRBS의 1 개수** (루프백과 반대 서명 — 브링업 판독표) |
| F10 | 경계                    | N=2,048(풀 버퍼)·B=8(최소)·B=2,048(계약 기본) 각 클린 런                  |

## core_top 승인 항목 (smoke 27체크의 재현 — `tb_core_smoke.v` 헤더 참조)

- C1 레지스터 리셋값·ID / C2 PHASE_INC·DEC signed 누적 / C3 R2·R4 busy 게이팅
- C4 CTRL 단일 명령 규칙 + CMD_ERR sticky / C5 R5 sticky DONE·자동 클리어
- C6 R10·R11 sticky 플래그와 유효 START 클리어

## 통합 항목

- I1 호스트 스텝 시퀀스(§3) 1스텝 왕복: PHASE_INC → PS_BUSY 폴 → START → DONE 폴 → ERR·e_i 회수
- I2 R8 무결성(호스트 검사 리허설) — 스텝 2회 이상
- I3 무효 런 시나리오 1개 이상 (TIMEOUT 또는 CFG_ERR)가 CSV 경로에서 `_invalid`로 이어지는 것 (호스트 스크립트까지 물리면 G1 범위)

## 승인 규칙

- 위 표의 PASS 기준이 어서션으로 존재하고 회귀 1회 전부 PASS → 블록 승인 (승인 행위는 팀원 A, `sim/README.md`)
- 회귀는 시드·위상 값을 고정하지 말 것 — 최소한 F4·F5는 스윕 루프
- golden model(경계 판정 독립 구현) 교차 검증은 G1 게이트 항목 — 이 문서 범위 밖 (워크플로 1 §G0-5)
