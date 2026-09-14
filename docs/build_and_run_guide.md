# 빌드·측정 가이드 — 어느 PC에서든 같은 계측기를 만들고 같은 절차로 잰다

- **작성일**: 2026-09-14 (Vivado/Vitis **2025.2** 팀 통일 후 첫 판)
- **대상**: 조원 전원. 이 문서 하나로 "클론 → 빌드 → 보드 프로그래밍 → 루프백/실칩 측정 → 분석"까지 간다.
- **원칙**: 빌드 산출물(`build/`)은 커밋하지 않는다. **각자 PC에서 같은 소스·같은 tcl·같은 Vivado 버전으로 빌드**하는 것이 재현성이다. 남의 `build/`를 복사받지 않는다.
- **검증 표기**: 각 명령 옆 `[검증 2026-09-14]`는 그 날 영웅 PC(Ubuntu 24, 2025.2)에서 실제로 통과한 것. 표기 없는 것은 아직 2025.2에서 안 돌려 본 것이다.
- **원전**: 실칩 당일 순서·판정은 `docs/workflow/7.realchip_uid_verification_day.md`, 배선·고장 판독표는 `docs/workflow/3.realchip_day_runbook.md`(D0·표 E). 충돌 시 원전 우선.

## 목차

| # | 단계 | 무엇을 하나 | 소요 |
| - | ---- | ----------- | ---- |
| 1 | [준비물](#1-준비물) | 툴 설치 · 파이썬 환경 · 클론 · 보드 | 설치 1시간+ (1회) |
| 2 | [환경 확인](#2-환경-확인) | 셸에 2025.2가 올라왔는지 | 1분 |
| 3 | [빌드](#3-빌드) | 비트스트림·ELF를 `build/`에 만든다 (g0 → g2 → prep → g3) | 30~60분 |
| 4 | [루프백 측정](#4-루프백-측정-칩-없이) | 점퍼 1개로 계측기 자체 검증 (G0) | 15분 |
| 5 | [실칩 측정](#5-실칩-측정-래퍼) | 래퍼 한 줄로 prep → UID → 스윕 | 7분/회 |
| 6 | [분석](#6-분석) | CSV → 욕조 곡선 · 폭 · 체크리스트 | 1분 |
| 7 | [자주 막히는 곳](#7-자주-막히는-곳) | 증상 → 원인 → 조치 | — |

---

## 1. 준비물

### 1.1 Vivado + Vitis 2025.2 (필수, 다른 버전 불가)

빌드 tcl에 버전 가드가 있어 **2025.2가 아니면 빌드가 거부된다.** Lab Edition은 프로그래밍만 되고 빌드가 안 되므로 안 된다.

- 설치기: AMD 웹 설치기 `FPGAs_AdaptiveSoCs_Unified_SDI_2025.2_*_Lin64.bin` (AMD 계정 필요)
- 실행은 **터미널에서 직접** (`./FPGAs_…bin`). `nohup`·백그라운드로 띄우면 터미널을 찾다 죽는다
- 선택: 제품 **Vitis** (Vivado를 포함한다) → 디바이스 **Zynq-7000 All Programmable SoC만** 체크, 나머지 디바이스 전부 해제 → 설치 경로 `<루트>` (예 `/home/<me>/Xilinx`)
- HLS·Model Composer는 해제가 안 되는 강제 항목이다. 그대로 둔다. 설치 끝에 "Model Composer … script failed" 경고가 떠도 무시 (MATLAB 없어서 나는 것)
- 라이선스 관리자 창이 뜨면 그냥 닫는다 — xc7z020은 무료 범위
- 2025.2는 `<루트>/2025.2/Vivado`, `<루트>/2025.2/Vitis` 배치다 (2024.2의 `<루트>/Vivado/2024.2`와 다름)
- 디스크: 다운로드 28GB + 최종 79GB. 설치 중 다른 무거운 프로그램은 닫는다 (메모리 부족으로 멈춘 사례 있음)

### 1.2 파이썬 환경 (uv) `[검증 2026-09-14]`

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh     # 최초 1회
cd <리포>
uv sync                                              # .venv 생성 + 락파일대로 설치
uv run python host/analysis/bathtub_analysis.py --selftest
```

개인 venv·pip 수동 설치 금지 (CONTRIBUTING §1.5). 실행은 항상 `uv run python …`.

### 1.3 저장소

```bash
git clone https://github.com/young-0320/flash-margin-bench
cd flash-margin-bench
git log --oneline -1        # 2026-09-14 이후 커밋(가드 2025.2)이어야 한다
```

### 1.4 보드·케이블·포트

- Zybo Z7-20, USB 케이블 1개 (JTAG + UART 겸용), **JP5 = JTAG** 부팅 모드
- 루프백: 점퍼선 1개 (JE1 ↔ JE2)
- 실칩: W25Q64 모듈 + 배선은 런북 3 D0 표
- **UART 포트**
  - 리눅스: 사용자를 `dialout` 그룹에 넣는다 (`sudo usermod -aG dialout $USER` 후 재로그인). 포트는 보통 `/dev/ttyUSB1` (기본값)
  - Windows: FT2232의 A(JTAG)·B(UART) 채널이 둘 다 COM으로 잡힌다. 장치 관리자에서 부모가 "USB Serial Converter **B**"인 COM을 골라 `--port COM<N>`. 판정은 "캡처 켜고 프로그래밍하면 수 초 안에 BEGIN이 뜨는가" (로그 13)

## 2. 환경 확인

새 터미널을 열 때마다 (또는 `.bashrc`에 한 줄):

```bash
source <루트>/2025.2/Vitis/settings64.sh     # Vitis 것이 Vivado·xsct·vitis를 전부 올린다
which vivado xsct vitis                        # 셋 다 <루트>/2025.2/ 아래여야 한다
vivado -version | head -1                      # "vivado v2025.2"
```

`[검증 2026-09-14]` 두 버전을 한 셸에서 연달아 source하지 않는다 — PATH가 섞인다. `.bashrc`에는 한 줄만.

## 3. 빌드

전부 리포 루트에서. 산출물은 `build/` (gitignore). 순서가 있다 — 각 단계가 다음 단계의 XSA를 만든다.

| 단계 | 무엇을 | 명령 | 산출물 | 소요 |
| ---- | ------ | ---- | ------ | ---- |
| 3.1 g0 `[검증 2026-09-14]` | 루프백 계측기 (RTL → BD → 비트 → XSA → ELF 원샷) | `vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl` | `build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit` · `build/vitis/g0_sweep/build/g0_sweep.elf` | 10~20분 |
| 3.2 g2 | 실칩 JEDEC 브링업 비트 (PS SPI → JB) | `vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl` | `build/vivado_g2/g2_jedec.xsa` | 5분 |
| 3.3 prep | 사전 쓰기 + UID 앱 (g2 XSA 소비) | `vitis -s ps/scripts/build_flash_prep.py` | `build/vitis_prep/flash_prep/build/flash_prep.elf` | 2분 |
| 3.4 g3 | 실칩 스윕 계측기, 클럭별 3벌 | `vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 25` (45·75도 같은 식) | `build/vivado_g3_<mhz>/…/g3_wrapper.bit` · `build/vitis_g3_<mhz>/g3_sweep/build/g3_sweep.elf` | 10분/클럭 |

루프백만 할 사람은 3.1만. 실칩을 할 사람은 3.1~3.4 전부 (g3는 우선 25만, 45·75는 사다리 때).

**끝나면 확인** — 산출물 존재 + 타이밍 위반 없음:

```bash
ls build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit build/vitis/g0_sweep/build/g0_sweep.elf
grep -L "All user specified timing constraints are met" build/vivado*/*.runs/impl_1/*_timing_summary_routed.rpt
# ↑ 아무것도 출력되지 않아야 한다 (출력된 파일 = 타이밍 위반 → 측정 금지)
```

**빌드 재현성 확인 (선택)**: `.bit`는 헤더에 생성 시각이 들어가 md5로는 비교할 수 없다. 대신 타이밍 요약의 WNS와 자원 사용량을 조원끼리 비교한다 — 같은 소스·같은 버전이면 같아야 한다.

```bash
R=build/vivado/g0_loopback.runs/impl_1/g0_wrapper
grep -A8 'Design Timing Summary' ${R}_timing_summary_routed.rpt | grep -E '^\s+-?[0-9]+\.' | head -1 | awk '{print "WNS="$1, "TNS="$2, "WHS="$5}'
grep -E '^\| (Slice LUTs|Slice Registers)' ${R}_utilization_placed.rpt | head -2
```

영웅 PC 2026-09-14 값은 `docs/log/young/27.vivado_2025_2_migration_plan.md` §빌드 결과 표에 있다.

## 4. 루프백 측정 (칩 없이)

**무엇을**: 칩 없이 FPGA 출력을 점퍼로 되받아 욕조 곡선을 만든다. 계측기 자체가 동작한다는 물리 검증(G0). 새 PC·새 빌드는 반드시 이걸 먼저 통과한다.

```
4.1 점퍼: JE1(V12) ↔ JE2(W16) 직결. 보드 전원, USB, JP5=JTAG
4.2 [터미널 1] 캡처를 먼저 켠다 — 첫 줄(BEGIN)부터 받아야 하므로 순서가 중요하다
    uv run python host/capture/sweep_uart_capture.py --loopback [--port /dev/ttyUSB1|COM<N>]
4.3 [터미널 2] 프로그래밍 + 실행 (JTAG)
    xsct ps/scripts/program_g0.tcl
4.4 완주 대기 (~10분, UART 전송이 지배). 터미널 1에서
    "#G0 SWEEP END valid=1 reason=complete"
    → build/data/sweep_loopback_<stamp>.csv 생성
4.5 분석 → §6
```

기대: `valid=1`, 체크리스트 통과, width@θ=1e-2 가 수만 ps 자릿수(7월 값 34,693ps — 점퍼·접촉에 따라 수백 ps 흔들린다, 정밀 비교 대상 아님).

## 5. 실칩 측정 (래퍼)

**무엇을**: 칩을 꽂고 래퍼 한 줄을 돌리면 ① 사전 쓰기(flash_prep) → ② 칩 UID 읽기 → ③ 등록부에서 라벨 역조회 → ④ 스윕 N회 → CSV. 사람이 캡처를 따로 띄우지 않고, 라벨을 손으로 입력하지 않는다.

선행: §3의 g2·prep·g3(25) 빌드, 배선(런북 3 D0), 칩 UID가 `docs/chip_registry.md`에 있어야 한다 (새 칩은 먼저 등록).

```
5.1 첫 실행 (prep 포함, ~7분):
    uv run python host/run/run_sweep_chip.py --mhz 25
5.2 같은 칩 반복 (사전 쓰기는 비휘발 — 지우기 전까지 재사용):
    uv run python host/run/run_sweep_chip.py --mhz 25 --no-prep --uid <16hex> --repeat 3
    --reseat 를 붙이면 회차 사이에 재장착 프롬프트 (재장착 σ 측정용)
5.3 산출물:
    build/data/sweep_<label>_<uid16>_<stamp>.csv (+ _reads.csv)
    build/data/session_<label>_<uid>_<batch>.log
    docs/chip_pe.md 에 P/E 증분 행 자동 추가 (append-only)
```

당일 순서표(배선 → 1차 실행 → 세 곳 대조 → 분석 → 재장착 3회 → 판정 → 보관)는 워크플로 7이 원전이다.

## 6. 분석

```bash
uv run python host/analysis/bathtub_analysis.py build/data/sweep_<…>.csv
```

출력: width@θ(1e-2·1e-3·1e-4), 벽 σⱼ 좌/우, 체크리스트 5항 PASS/FAIL, `build/plots/*.png`. 게재할 것만 `docs/results/`로 승격하고 동명 md에 유래(빌드 Vivado 버전 포함)를 적는다.

## 7. 자주 막히는 곳

| 증상 | 원인 | 조치 |
| ---- | ---- | ---- |
| 빌드 첫 줄 `Vivado 2025.2 필요 (현재: …)` | 다른 버전 셸 | §2 |
| `xsct 가 PATH 에 없다` (래퍼) | settings64.sh 미source | §2 |
| 캡처에 BEGIN이 안 뜸 (Windows) | JTAG 채널 COM을 열었음 | 다른 COM (§1.4) |
| 캡처에 BEGIN이 안 뜸 (리눅스) | 포트 권한 / 포트 번호 | `dialout` 그룹, `ls /dev/ttyUSB*` |
| `TIMEOUT` (루프백) | 점퍼 미접촉 | 점퍼 |
| `phase_pos_mismatch` | ELF만 재로드 | program 전체 경로 재실행 (xsct …) |
| 전 위상 BER ≈ 0.5 (실칩) | PAY_LEAD 정렬 이탈 | `--pl 4` 또는 `--pl 6` 보험 비트 (먼저 `build_g3_chip.tcl -tclargs bit 25 <k>`로 구워야 함) |
| `#PREP FAIL` | 쓰기/검증 실패 | 스윕 금지. 배선·/WP·/HOLD·전원 |
| JEDEC `FF FF FF` / `00 00 00` | 무칩/오배선 | 런북 3 D0 표 |

더 자세한 판독표는 런북 3 표 E.
