# 역할 분담 (초안)

Updated: 2026-07-06

폴더 = 소유자. 타인 폴더는 PR로만 수정한다. 폴더 배치 원칙은 `CONTRIBUTING.md` 참조.

| 사람   | 한 줄 정의                                 | 소유 폴더                                                            |
| ------ | ------------------------------------------ | -------------------------------------------------------------------- |
| 한영웅 | 실험 설계·데이터 오너 / 계측 엔진 아키텍트 | `fpga/rtl/core/`, `sim/golden/`, `host/analysis/`, `docs/interface/` |
| 팀원 A | SPI/트랜잭션 서브시스템 오너               | `fpga/rtl/flash/`, `fpga/constraints/`, `fpga/scripts/`, `sim/tb/`   |
| 팀원 B | 실험 인프라·신뢰성 실험 오너               | `hw/`, `ps/`, `host/viz/`, `data/`(스키마 관리)                      |

---

## 한영웅 — 실험 설계·데이터 오너 / 계측 엔진 아키텍트

### 코어 RTL

- MMCM 동적 위상 제어(PSEN/PSINCDEC)
- 위상 스윕 FSM
- AXI-Lite 레지스터 파일
- 루프백 실증(G0)

### 검증 인프라

- golden model(몬테카를로) — `sim/golden/`
- 테스트 계획 문서 — **팀원 A의 승인 기준이 되는 문서. 먼저 작성해야 회귀 승인이 가능**

### 실험 설계

- 칩 10개 배분: W25Q64는 브링업·반복성·신품 산포·예비(+선택적 NOR 마모 파일럿). 종단 마모 4개 배분은 W25N 도착 후
- 반복성 프로토콜, 블라인드 절차
- 설계 결정 A~D 주도 (NAND 3종 지표 체계, 0x03/0x0B 커맨드, ECC 비활성화, 레벨 시프터)

### 분석

- sweep_runner
- 교정 곡선(band) 구축
- 개체 산포 σ vs 노화 이동량 Δ 분리
- 블라인드 추정 오차 정량화

### 계약 오너

- 레지스터 맵, UART 프로토콜, 측정 레코드 스키마

**소유 폴더:** `fpga/rtl/core/`, `sim/golden/`, `host/analysis/`, `docs/interface/`

**하지 않는 것:** flash 서브시스템 내부 설계, 검증 환경 구축·회귀 실행, 열 이력 실험 세부, 회귀 PASS 자가 승인

---

## 팀원 A — SPI/트랜잭션 서브시스템 오너

### RTL

- `fpga/rtl/flash/`: SPI 마스터(가변 클럭, 더미 사이클, NOR/NAND 커맨드 셋, 상태 폴링), P/E 사이클링 엔진, 패턴 생성기, op_timer(10ns), error logger
- **내부 아키텍처 결정권 보유** — 외부 스펙(레지스터 맵, 더미 사이클 요구사항)만 준수하면 됨
- SPI 물리 계층/커맨드 시퀀서 계층 분리 요구됨 — NAND 확장 시 nor/nand 폴더 분화 여부도 이 사람 판단

### 빌드 플로우

- `fpga/constraints/` (xdc), `fpga/scripts/` (vivado build.tcl)

### 검증 운영

- cocotb 환경 구축 (`sim/tb/`)
- Winbond 행동 모델 통합
- cocotb 회귀 실행
- 결과 리뷰 및 마일스톤 PASS 승인 (기준: 한영웅의 테스트 계획 문서)

**소유 폴더:** `fpga/rtl/flash/`, `fpga/constraints/`, `fpga/scripts/`, `sim/tb/`

---

## 팀원 B — 실험 인프라·신뢰성 실험 오너

### DUT 보드

- SOP8 소켓, 가변 전원+레벨 시프터, 히터+온도 센서, 보호 회로 — 설계·제작·브링업

### 열 이력 실험 (독립 챕터로 완결)

- 리플로우 0/1/3/5회 그룹 실험 전체 — 프로파일 결정, 시료 제작, 그룹 비교 분석, 보고서 집필

### PS 펌웨어

- 베어메탈 C: UART 명령 서버, 온도 PID, JEDEC ID 식별
- **7월 착수 순서 주의:** PL 주소 맵 확정 전엔 UART 에코 서버(Zynq 단독)부터 세워 공백 방지

### 실험 수행

- 마모·스윕 실험 실행(9월~, 시기별 부하 최대)
- 측정 데이터 정리, Fail Map 생성·해석

### 시각화·DB

- plot_bathtub / plot_shmoo, chipdb

**소유 폴더:** `hw/`, `ps/`, `host/viz/`, `data/`(스키마 관리)
