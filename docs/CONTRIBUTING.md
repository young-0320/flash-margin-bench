# 협업 규칙

## 1. 폴더 구조

```
repo/flash-margin-bench/
├── README.md           # 사람용 입구 — 프로젝트 정의·원리·3막 구조·폴더 지도
├── CLAUDE.md           # 에이전트 행동 계약 — 규칙만, 설명은 README 참조
├── .gitignore
├── fpga/               # 비트스트림 생산에 들어가는 입력의 집합
│   ├── rtl/
│   │   ├── core/       # [한영웅] MMCM 위상 제어, 스윕 FSM, AXI-Lite 레지스터
│   │   └── flash/      # [팀원 A] SPI 마스터(더미 사이클), P/E 사이클러, 패턴/타이머/로거
│   ├── constraints/    # [팀원 A] 핀 배치·타이밍 제약 (.xdc)
│   └── scripts/        # [팀원 A] Vivado 프로젝트 재생성 tcl (build.tcl이 소스)
├── ps/                 # [팀원 B] Zynq 베어메탈 C — UART 명령 서버, 온도 PID + vitis tcl
├── host/               # 호스트 PC Python — 무거운 로직 전부, 코드량 최대 영역
│   ├── analysis/       # [한영웅] sweep_runner, 몬테카를로, 교정 곡선, 오차 정량화
│   └── viz/            # [팀원 B] plot_bathtub/shmoo, chipdb
├── sim/                # cocotb 검증 — tb/ [팀원 A], golden/ [한영웅]
├── hw/                 # [팀원 B] DUT 보드 KiCad, BOM, 결선도, 열 이력 시료
├── docs/               # roles, milestone, decisions 등 프로젝트 문서
│   └── interface/      # [한영웅] 레지스터 맵, UART 프로토콜, CSV 스키마 (동결 후 3인 합의로만 수정)
├── build/          (.gitignore)   # 재현 가능한 생성물 전부 (Vivado 산출물, 분석 그림·표) — 커밋 금지
└── data/           (.gitignore, 스키마·샘플만 커밋)   # 측정 데이터
```

### 배치 기준

구조를 관통하는 원칙 4가지. 새 파일·폴더의 위치가 애매하면 이 순서로 판단한다.

1. **명명 기준 통일** — 폴더 이름은 "어디서 도는가"(`ps/`, `host/`, `sim/`) 또는 "무엇을 생산하는가"(`fpga/`, `hw/`) 기준.
2. **폴더 = 소유자 1명** — 하위 경계까지 포함해서 소유자가 한 명이다. 타인 폴더는 PR로만 수정한다.
3. **소스와 생성물 분리** — 사람이 쓴 텍스트만 커밋한다. 생성물(`.xpr`, 비트스트림, 측정 CSV)은 스크립트로 재생성한다.

문서 배치: `docs/spec/`는 설계가 바뀔 때 같이 업데이트한다.

**생성물 흐름 (build/ → docs/reports/)**: 스크립트로 재생성할 수 있는 산출물(그림, 표, 시뮬레이션 CSV)은 전부 `build/` 하위에 생성한다 — 세부 폴더(`build/plots/`, `build/data/` 등)는 생산 스크립트가 정한다. `build/`는 통째로 `.gitignore`. 이 중 중간보고서·최종보고서·최종발표에 실제 게재되는 것만 **사람이 직접** `docs/reports/`로 복사해 승격하고, 승격본만 커밋한다. 즉 `docs/reports/`에 있다는 것 자체가 "보고서·발표 게재물"이라는 선언이다. 단, 실칩 측정 원본은 재현 불가능하므로 `build/`가 아니라 `data/`에 둔다(아래 표).

### 폴더별 역할 상세

소유자·분담 상세는 `docs/roles.md` 참조. 3인 병렬 개발의 실질적 충돌 방지 장치는 폴더가 아니라 `docs/interface/`의 계약이다.

| 폴더                  | 소유자 | 역할                                                                                                                                                                                                                                                                           |
| --------------------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `README.md`         | —     | 사람용 입구. GitHub 정면에 렌더링되는 유일한 지면. 한 문장 정의, 원리 요약, 3막 구조, 폴더 지도, docs/ 링크. 짧게 유지하고 깊은 내용은 docs/로 위임 — 단일 출처 원칙.                                                                                                         |
| `CLAUDE.md`         | —     | 에이전트 행동 계약. 설명이 아니라 규칙만 담는다(OPEN 결정 임의 판단 금지, 빌드 산출물 커밋 금지, 계약 우선, 회귀 규칙). 프로젝트 설명은`@README.md` 임포트로 참조 — 복제하면 드리프트.                                                                                      |
| `fpga/`             | —     | 비트스트림 생산에 들어가는 입력의 집합. 이 정의가 하위 배치의 판별 규칙이다.                                                                                                                                                                                                   |
| `fpga/rtl/core/`    | 한영웅 | 측정의 심장. MMCM 동적 위상 제어(PSEN/PSINCDEC), 위상 스윕 FSM, AXI-Lite 레지스터 파일.**판별: "언제 샘플링하고 측정을 어떻게 제어하나"를 다루면 여기.**                                                                                                                 |
| `fpga/rtl/flash/`   | 팀원 A | 플래시와의 트랜잭션 계층 전부. SPI 마스터(물리 계층/커맨드 시퀀서 분리, 더미 사이클 지원), P/E 사이클러, 패턴 생성기, op_timer, error logger.**판별: "칩과 무엇을 주고받나"를 다루면 여기.** NOR/NAND 하위 분화는 W25N 착수 시 구현 구조에 따라 — 지금은 평탄 유지.     |
| `fpga/constraints/` | 팀원 A | xdc — 핀 배치·타이밍 제약. 합성은 되는데 보드에서 안 돌 때 제일 먼저 보는 곳이라 rtl과 분리.                                                                                                                                                                                 |
| `fpga/scripts/`     | 팀원 A | vivado`build.tcl`. `.xpr`을 커밋하는 대신 프로젝트를 재생성하는 스크립트가 소스다.                                                                                                                                                                                         |
| `ps/`               | 팀원 B | Zynq ARM 코어에서 도는 베어메탈 C + vitis tcl. UART 명령 서버, 온도 PID, JEDEC ID 식별. "PS는 얇게" 원칙에 따라 최소 로직만. vitis tcl이 여기 있는 이유: vivado의 출력(.xsa)을 소비하는 별도 공정이고 소유자가 다르므로`fpga/`가 아니다.                                     |
| `host/`             | —     | 호스트 PC에서 도는 Python. 무거운 로직 전부, 코드량 최대 영역.                                                                                                                                                                                                                 |
| `host/analysis/`    | 한영웅 | sweep_runner(시나리오 자동화), 몬테카를로, 교정 곡선 구축, 오차 정량화.                                                                                                                                                                                                        |
| `host/viz/`         | 팀원 B | plot_bathtub/shmoo, chipdb(칩 이력 DB).                                                                                                                                                                                                                                        |
| `sim/`              | 분할   | 시뮬레이터에서 도는 것 전부. `tb/`(팀원 A): cocotb 환경, Winbond 행동 모델 통합, 회귀 실행. `golden/`(한영웅): golden model(몬테카를로). 회귀 승인 기준은 한영웅의 테스트 계획 문서. RTL(fpga 소유물)을 Python(host 담당 언어)으로 검증하는 경계 영역이라 `fpga/`에도 `host/`에도 넣지 않고 독립. |
| `hw/`               | 팀원 B | 실행 코드가 아닌 물리 설계물. DUT 보드 KiCad, BOM, 결선도, 열 이력 시료 기록. 레벨 시프터·히터·보호 회로가 여기서 결정된다.                                                                                                                                                  |
| `docs/`             | —     | roles.md(역할·소유권), milestone-bathtub.md(G0~G4 스코프), decisions-hyw.md(개인 결정 레지스터), decisions.md(팀 공용 설계 결정 A~D).                                                                                                                                        |
| `docs/interface/`   | 한영웅 | 레지스터 맵, UART 프로토콜, CSV 스키마. 동결 후 수정은 3인 합의.                                                                                                                                                                                                               |
| `build/`            | —     | 재현 가능한 생성물 전부 — Vivado 산출물(`.xpr/.runs/.cache`)과 분석 스크립트 출력(그림·표·시뮬레이션 CSV — `build/plots/`, `build/data/`). `.gitignore` 대상 — 커밋되는 순간 리포가 무거워지고 충돌원이 된다. 보고서 게재분만 사람이 `docs/reports/`로 승격.        |
| `docs/reports/`     | —     | 보고서·발표 게재물의 승격처. `build/`에서 사람이 선별 복사한 것 + 보고서 초안만 — 생산 스크립트가 여기에 직접 쓰지 않는다.                                                                                                                                                |
| `data/`             | —     | 측정 CSV.`.gitignore`하되 스키마 정의와 샘플 몇 줄만 커밋. 재현성은 원본 데이터가 아니라 생성 스크립트+파라미터+chip_id로 확보.                                                                                                                                              |

## 1.5 파이썬 환경 (uv)

호스트 Python(`host/`, `sim/golden/`)의 의존성은 리포 루트 `pyproject.toml` + `uv.lock`으로 관리한다. 개인 venv·pip 수동 설치 금지 — 세 명이 같은 환경이어야 "내 컴에선 되는데"가 없다.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv 설치 (최초 1회)
uv sync                                            # .venv 생성 + 의존성 설치 (락파일 기준)
uv run python host/analysis/bathtub_analysis.py --selftest   # 실행은 uv run 으로 (activate 불필요)
```

의존성 추가는 `uv add <패키지>` — pyproject.toml과 uv.lock이 같이 갱신되므로 둘 다 커밋한다. 예외: `sim/tb/`의 cocotb는 시뮬레이터(iverilog)와 함께 설치되는 별도 환경(팀원 A 관리).

## 2. 파일 네이밍 규칙

1. 모든 파일명은 소문자 + 언더스코어 방식으로 작성한다.
2. 파일 이름과 모듈 이름은 일치시킨다 (예: `full_adder.v` → `module full_adder`).
3. 하나의 파일에는 하나의 모듈만 작성한다.
4. 테스트 벤치의 파일 이름은 tb_로 시작한다 (예: `tb_full_adder.v`).

## 3. Git 사용법

### **기본 원칙**

**중요 : 작업 전에 항상 최신 코드를 받는다.**

먼저 현재 작업 중인 변경사항이 있는지 확인한다.

```
git status
```

작업 중인 변경사항이 없다면 최신 코드를 받는다.

`git pull origin main`

작업 완료 후에는 바로 `git add .`를 하기 전에 변경 파일과 변경량을 확인한다.

```
git status
git diff --stat
```

커밋에 넣을 파일만 골라서 stage 한다.

```
git add <파일 경로>
```

예시:

```
git add rtl/simple_cpu/alu.v
git add sim/tb/tb_alu.v
git add docs/spec/simple_cpu.md
```

모든 변경사항을 의도적으로 커밋할 때만 `git add .`를 사용한다.

변경사항을 확인한 뒤 commit과 push를 한다.

```
git commit -m "커밋 메시지"
git push origin main
```

### **커밋 메시지**

선택 사항입니다.

```
feat:     새 기능 추가
fix:      버그 수정
test:     Testbench 추가 또는 수정
docs:     문서 수정
refactor: 기능 변경 없이 코드 정리
```

예시

```
feat: ALU 비교 연산(EQ, GT) 추가
fix: FSM DECODE 상태에서 제어 신호 오류 수정
test: tb_alu 단위 시뮬레이션 추가
docs: spec 업데이트
```

## 4. 주의사항

1. 작업 전에 꼭 `git pull`로 최신 코드 반영
2. `git push`하기 전 한번만 더 확인
