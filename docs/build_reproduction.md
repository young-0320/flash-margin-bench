# 빌드 재현 절차 — 소스에서 보드 프로그래밍까지

이 문서는 저장소 소스(RTL·XDC·tcl·C)에서 `build/` 산출물(비트스트림·XSA·ELF)을 만들고
보드에 굽기까지의 전체 절차를 담는다. `build/`는 커밋하지 않으므로 **측정하는 PC마다 이
절차로 만든다** — 남의 `build/`를 복사하면 어느 소스·어느 버전으로 만든 계측기인지 추적이
끊긴다. 레포 소개와 결과 요약은 최상위 `README.md`, 게이트(G0~G5)와 설계 이름(`g0_*`)의
정의는 `docs/workflow/4.gate_map.md`, 측정 당일 절차는 런북 3(`docs/workflow/3.*`)·워크플로
7(`docs/workflow/7.*`), 파이썬 환경 규칙은 `docs/CONTRIBUTING.md` §1.5 참고.

표기 `[검증 2026-09-14]`는 그 날 영웅 PC(Ubuntu 24, Vivado/Vitis 2025.2)에서 실제로 통과한 명령.

---

## ⚡ 하나로 전부 — `reproduce.py`

**이 문서의 §3(빌드)과 §5(검증)는 손으로 치지 않아도 된다.** 리포 최상위의 `reproduce.py` 가
같은 명령을 같은 순서로 돌리고 **§3.6 기준으로 단계마다 채점**한다. **사용법·옵션은
`docs/commands.md` §1** — 여기에는 복사하지 않는다 (2026-09-21). 이 문서가 담는 것은 그 스크립트가
대신 치는 원명령과 기대 산출물·검증 수치, 즉 `reproduce.py` 의 사양이다.

**검증(sim·selftest·tb)이 맨 앞이다.** 합쳐 15초 남짓인 반면 빌드는 9분이라,
RTL·엔진이 깨져 있으면 Vivado 를 태우기 전에 알아야 한다 — 「전체 흐름」의 순서 그대로다.

**채점이 요점이다. 종료 코드 하나로 판정하지 않는다** — `vitis -s` 는 빌드가 깨져도 0 을 돌려준다.

| 검사                                               | 잡는 실패                                                                                                   |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| ① 종료 코드                                       | 명시적 실패                                                                                                 |
| ② 로그의 완료 문구 (횟수까지)                     | 조용한 실패 — 시뮬`PASS` ×4, 셀프테스트 `selftest PASS` ×2, TB `N passed`                              |
| ③ 산출물이**이번 실행 이후에** 생겼는지     | **옛 산출물이 남아 성공처럼 보이는 것** (2026-09-15 에 45·75MHz ELF 가 구형인 채 세대가 섞였던 유형) |
| ④ (Vivado) 타이밍 충족 문구                       | 타이밍 위반 비트로 측정하는 것                                                                              |
| ⑤ (Vivado) WNS/WHS·LUT/FF 를 §3.6 기준표와 대조 | 배치가 달라진 것 →**FAIL 이 아니라 WARN**                                                            |
| ⑥ (g3) 빌드 파라미터 — 로그의 `== done (<mhz>MHz, steps=…, n_reads=112)` 대조 | **무엇으로 구웠는지** — ③은 "다시 구웠다"만 말한다. 2026-09-15 에 45·75MHz ELF 가 N=100 인 채 남아 세대가 섞였던 유형 |
| ⑥ (wear) `== done (git_rev <HEAD>, spi prescale 64 (default))` 대조 | **어느 커밋의 엔진인지** — H 행 `git_rev` 가 시험 기록의 신원이다. 2026-09-21 에 커밋 직전에 구운 ELF 가 한 커밋 전 rev 를 품고 있던 유형 |

- 로그: `build/logs/reproduce_<UTC>/<단계>.log` + `summary.txt` (각 로그 첫 줄에 실제 명령과 `cwd`)
- 백업: 단계 시작 전 그 단계의 산출물만 `build/_prev/<단계>/` 에 **직전 1세대**. Vitis 빌드
  스크립트가 워크스페이스를 통째로 지우므로 컴파일이 깨지면 옛 ELF 까지 잃는다. **복원은 사람이 한다**
- **범위**: §3 · §5 · §6. **§4(보드 굽기)는 하지 않는다** — 보드·칩이 필요한 행위는 런북의 몫이다.
  §8 의 PAY_LEAD 보험 비트도 범위 밖이라 그것만은 §8 의 명령을 직접 친다
- 설계 경위와 미결은 `docs/log/young/32.reproduce_script.md`, Windows 대응은 로그 33, tb·wear 단계 추가는 2026-09-21

아래 §1\~§8 은 **각 단계를 손으로 칠 때의 원전**이자 이 스크립트가 무엇을 하는지의 근거다.
스크립트와 문서가 어긋나면 **문서가 옳고 스크립트를 고친다.**

---

## 전체 흐름

레포는 두 개의 루프로 굴러간다. 보드 없이 도는 검증 루프와, 보드에 올리는 빌드·측정 루프다.

```
[검증 루프 — 보드 불필요]
sim/smoke/  iverilog 스모크 TB 4개 (core · flash · spi · g0)   → 전부 PASS
host/       파이썬 셀프테스트 3개 (분석기 · 등록부 · P/E 이력) → 전부 PASS
host/tests/ 블랙박스 TB (S-4) — mock 채점 + C 엔진 호스트 시뮬(gcc) + 실행기 → 114 passed
sim/tb/     cocotb + Winbond 모델 회귀 = G1 (박지민, 구축 중)   → 기준 docs/spec/s3.g1_test_plan.md

[빌드·측정 루프 — 보드 필요]
fpga/scripts/*.tcl  →  build/vivado*/   bit · XSA        (Vivado)
ps/scripts/*.py     →  build/vitis*/    ELF              (vitis -s, XSA 소비)
ps/scripts/*.tcl    →  보드              JTAG 프로그래밍  (xsct)
host/capture/       →  build/data/      CSV              (UART 수신)
host/analysis/      →  build/plots/     욕조 곡선 · 폭    (판정)
host/run/run_wear.py→  build/logs/wear/ P/E 시험 verdict  (xsct + UART, 워크플로 12)
```

RTL을 바꾸면 검증 루프부터. 측정만 재현하려면 빌드·측정 루프만 돌면 된다. **g1 빌드는 없다** —
G1은 시뮬레이션 게이트라 비트스트림·ELF를 만들지 않는다.

## 목차

0. [한 줄로 전부 — `reproduce.py`](#-한-줄로-전부--reproducepy) — 빌드·검증 자동 실행과 채점
1. [파이썬 환경 준비](#1-파이썬-환경-준비) — uv 환경, 시리얼 포트
2. [전제: 도구와 버전](#2-전제-도구와-버전) — Vivado/Vitis 2025.2, iverilog 등 도구
3. [빌드 파이프라인](#3-빌드-파이프라인) — 빌드 루프 전체
   1. [g0 — 루프백 계측기](#31-g0--루프백-계측기) — bit·XSA·ELF
   2. [g2 — 실칩 JEDEC 브링업 비트](#32-g2--실칩-jedec-브링업-비트) — bit·XSA
   3. [prep — 사전 쓰기·UID 앱](#33-prep--사전-쓰기uid-앱) — ELF
   4. [g3 — 실칩 스윕 계측기 (클럭별)](#34-g3--실칩-스윕-계측기-클럭별) — ×3 클럭
   5. [wear — P/E 마모 엔진](#35-wear--pe-마모-엔진) — ELF, git_rev 신원
   6. [빌드 확인](#36-빌드-확인) — 존재·타이밍·기준값 대조
4. [산출물을 보드에 굽는 명령](#4-산출물을-보드에-굽는-명령)
5. [검증 파이프라인](#5-검증-파이프라인) — 검증 루프 전체
   1. [RTL 스모크 시뮬레이션](#51-rtl-스모크-시뮬레이션)
   2. [호스트 셀프테스트](#52-호스트-셀프테스트)
   3. [블랙박스 TB — P/E 엔진](#53-블랙박스-tb--pe-엔진)
6. [빠른 재빌드](#6-빠른-재빌드) — C 앱만 바뀐 경우의 지름길
7. [산출물 트리](#7-산출물-트리) — `build/` 트리
8. [디버그·과거 흐름](#8-디버그과거-흐름) — 스모크 앱·보험 비트·옛 명령

## 1. 파이썬 환경 준비

PC 측 캡처·분석은 bare `python` 대신 프로젝트 `uv` 환경을 사용한다. 의존성은
`pyproject.toml`에 선언되어 있다 (Python ≥ 3.13). 개인 venv·pip 수동 설치 금지.

```bash
uv sync
uv run python host/analysis/bathtub_analysis.py --selftest
```

PC 스크립트는 `uv run python ...`으로 실행한다. 빌드 자체에는 파이썬이 필요 없다.
시리얼 포트 이름은 머신마다 다르다:

**보 레이트는 921600이 프로젝트 표준이다** (2026-09-15부터). 호스트 스크립트의 `--baud`
기본값이며, 보드 쪽은 전 앱이 `main` 초입에서 UART 분주기를 925,925bps로 맞춘다
(100MHz/(9×12), 오차 +0.47% — 허용치 ±2~3% 안). 근거는 로그 30 §10.3: 스윕은 스텝당
1,467B를 흘리는데 115200이면 UART 이용률이 98%라 여유가 0이고, 921600이면 12%로 떨어지며
스윕 1회가 5.3분 → 약 1분이 된다. **`build/`의 ELF가 2026-09-15 이전 것이면 115200이므로
재빌드하거나 `--baud 115200`을 줘야 한다** — 안 맞으면 `BEGIN` 자체가 안 뜬다.
2026-09-22부터 보 레이트 옵션은 펌웨어에도 걸린다 — 호스트가 `UART_BAUD` 환경변수로 xsct 에 넘기고,
`program_g2/g3.tcl` 이 ELF 를 올린 뒤 `print -set g_uart_baud` 로 덮어쓴다. `run_sweep_chip.py --baud`
와 `run_wear.py --wear-baud`·`--sweep-baud` 가 그 손잡이다. 921600 스윕에서 CSV 행이 빠지는 PC
(지민)는 `run_wear.py --sweep-baud 115200` 으로 체크포인트 스윕만 낮춘다. 측정값에는 영향이 없다
(chip01 두 보 레이트 차이 +0.45ps, σ 안 — `docs/results/data/newchip_survey_2026-09.md`).

| 호스트 OS    | 흔한 UART 포트            | 비고                                                                                                                               |
| ------------ | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Linux/Ubuntu | `/dev/ttyUSB1` (기본값) | 사용자를`dialout` 그룹에 추가 후 재로그인                                                                                        |
| WSL2 Ubuntu  | `/dev/ttyUSB1` (기본값) | USB 는 기본으로 WSL 에 안 들어온다 — Windows 쪽에서 `usbipd` 로 붙인다 (아래). 붙은 뒤 `ls /dev/ttyUSB*` 로 확인. `dialout` 은 Linux 와 같다 |
| Windows      | `COM3`, `COM4`, etc.  | FT2232의 A(JTAG)·B(UART) 둘 다 COM으로 잡힌다 — 장치 관리자에서 부모가 "USB Serial Converter**B**"인 쪽. `--port COM<N>` |

**WSL2 에서 빌드·측정하는 경우** (Vivado/Vitis 를 WSL 안에 설치한 조원):

- 리포는 **WSL 파일시스템**(`~/dev/…`)에 clone 한다. `/mnt/c/…` 에 두면 Vivado 가 수 배 느리고
  실행 비트·mtime 이 Windows 쪽 규칙을 따라 `reproduce.py` 의 ③ 검사와 `build_sim.sh` 실행이 흔들린다
- 보드 USB 는 usbipd-win 으로 WSL 에 넘긴다. `bind` 는 처음 한 번(관리자 PowerShell), 그 뒤의
  `attach` 는 **WSL 터미널 안에서** `usbipd.exe` 로 쳐도 된다(usbipd-win 4 이상, Windows interop).
  `--auto-attach` 를 붙여 두면 그 터미널이 살아 있는 동안 보드를 뺐다 꽂아도 다시 붙는다 — 측정
  세션마다 한 번만 치면 된다. `reproduce.py` 에는 넣지 않는다 — 보드를 만지는 일은 §4 처럼
  스크립트 범위 밖이고, BUSID 가 PC 마다 달라 설정 파일이 하나 더 생긴다

```powershell
winget install usbipd                     # Windows, 처음 한 번
usbipd list                               # "USB Serial Converter A, USB Serial Converter B" 의 BUSID
usbipd bind --busid <BUSID>               # 관리자 PowerShell, 처음 한 번
```

```bash
usbipd.exe attach --wsl --busid <BUSID> --auto-attach &   # WSL 안, 측정 세션마다 한 번 (빼고 꽂아도 유지)
ls /dev/ttyUSB*                                            # ttyUSB0(JTAG)·ttyUSB1(UART) 둘 다 보여야 한다
```

- 안 보이면 커널에 `ftdi_sio` 가 없는 것 — `uname -r` 이 5.10.60 미만이면 `wsl --update`.
  JTAG(xsct) 도 같은 케이블이라 같이 넘어온다
- 이 절차는 **2026-09-21 기준 미검증**이다 — 조원 PC 에서 처음 통과하면 이 줄을 `[검증 날짜]` 로 바꾼다

## 2. 전제: 도구와 버전

AMD Vivado + Vitis **2025.2**가 하드웨어/bare-metal 빌드에 필요하다. 다른 버전은 빌드 tcl의
버전 가드가 거부한다. Lab Edition은 프로그래밍만 되고 빌드가 안 된다. 설치 요령과 함정은
`docs/workflow/8.vivado_2025_2_migration_and_rebaseline.md` W8-I.

빌드 터미널마다 2025.2 환경 스크립트를 source한다. 2025.2는 `<루트>/2025.2/<툴>` 배치다
(2024.2의 `<루트>/<툴>/2024.2`와 다름). Vitis 쪽 스크립트가 Vivado·xsct·vitis를 전부 올린다.

```bash
export VITIS_SETTINGS=$HOME/Xilinx/2025.2/Vitis/settings64.sh
source "$VITIS_SETTINGS"

which vivado xsct vitis          # 셋 다 <루트>/2025.2/ 아래
vivado -version | head -1        # vivado v2025.2
```

`.bashrc`에 넣는다면 **한 줄만**. 두 버전을 한 셸에서 연달아 source하면 PATH가 섞인다.

기타 도구:

| 도구                            | 용도                                          |
| ------------------------------- | --------------------------------------------- |
| `uv` + Python 3.13            | 캡처·분석·셀프테스트                        |
| `iverilog` 11+ / `vvp`      | RTL 스모크 시뮬레이션                         |
| `gcc` (apt `build-essential`) | 블랙박스 TB 의 C 엔진 호스트 시뮬레이션 (§5.3) |
| `xsct` (Vitis 동봉)           | JTAG 프로그래밍                               |
| Digilent Zybo Z7-20 board files | `fpga/boards/`에 벤더링 — 별도 설치 불필요 |

## 3. 빌드 파이프라인

소스에서 보드 프로그래밍 직전까지의 최단 경로다. 각 tcl은 프로젝트를 처음부터 재생성한다
(`.xpr`을 열어 이어 빌드하지 않는다). 순서와 의존:

```
g0  ─────────────────────────────►  루프백 계측기 (독립)
g2  ──► flash_prep (g2 XSA 소비) ─►  실칩 사전 쓰기·UID
    ├─► flash_id   (같은 XSA)    ─►  신원 확인만 (P/E 불변 — sweep 모드 세션1)
    └─► flash_wear (같은 XSA)    ─►  P/E 마모 엔진 (워크플로 12 실칩 인수가 요구)
g3-25 ┐
g3-45 ├──────────────────────────►  실칩 스윕 계측기 (클럭별, 서로 독립)
g3-75 ┘
```

루프백만 할 사람은 3.1만. 실칩 스윕을 할 사람은 3.1~3.4 (g3는 우선 25만, 45·75는 클럭 사다리 때).
P/E 인수(워크플로 12)만 할 사람은 3.2 + 3.5 면 된다.

**한 번에 돌리려면** `python3 reproduce.py` — 문서 최상단 「한 줄로 전부」 참조.

### 3.1 g0 — 루프백 계측기

레포 루트에서:

```bash
source "$VITIS_SETTINGS"
vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl
```

내부 순서: 프로젝트 생성 → BD 조립 → 합성 → 구현 → 비트스트림 → XSA → `vitis -s ps/scripts/build_g0_sweep.py`(ELF). 입력은 `fpga/rtl/core/*.v` · `fpga/rtl/flash/flash_top.v`
계열 · `fpga/constraints/g0_*.xdc` · `ps/src/g0_sweep.c`. 약 8분.

기대 산출물:

```text
build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit     PL 비트스트림
build/vivado/g0_loopback.xsa                            하드웨어 플랫폼 (비트 포함)
build/vitis/g0_sweep/build/g0_sweep.elf                 PS 스윕 앱
build/vitis/g0_sweep/_ide/psinit/ps7_init.tcl           PS 초기화 (프로그래밍 때 사용)
```

기대 출력: 로그 끝에 `== timing: WNS=양수 WHS=양수` 와 `== all done: bit=… elf=…`.
`[검증 2026-09-14]` 22:58 통과, WNS 29.811 / WHS 0.096, LUT 900 / FF 1,013.

부분 실행: `-tclargs bd`(BD 검증까지) · `-tclargs bit`(ELF 생략).

### 3.2 g2 — 실칩 JEDEC 브링업 비트

```bash
vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl
```

PL 로직 없음 — PS SPI0을 EMIO로 JB 핀에 라우팅만 한다. 입력은 `fpga/constraints/g2_jedec_pins.xdc`.
약 1분.

기대 산출물:

```text
build/vivado_g2/g2_jedec.xsa
build/vivado_g2/g2_jedec.runs/impl_1/g2_wrapper.bit
```

기대 출력: `== done: …/g2_jedec.xsa (bit: …)`. `[검증 2026-09-14]` 23:00 통과.

### 3.3 prep — 사전 쓰기·UID 앱

g2 XSA에서 Vitis 플랫폼과 앱을 만든다. 사전 쓰기(PRBS 2,048페이지) + UID(4Bh) 읽기 앱.

```bash
vitis -s ps/scripts/build_flash_prep.py
```

입력은 `build/vivado_g2/g2_jedec.xsa` · `ps/src/flash_prep.c` · `ps/src/flash_io.c`(배관 부품). 약 20초.

기대 산출물:

```text
build/vitis_prep/flash_prep/build/flash_prep.elf
```

기대 출력: `== done (default 0~127): …/flash_prep.elf` (체크포인트 모드면 `sectors <base>~<끝>`). `[검증 2026-09-21]` 02:22 통과.

같은 XSA로 형제 앱 **`flash_id`** 도 만든다 — JEDEC과 UID만 읽고 **쓰기 명령을 내보내지
않는다**(P/E 불변). `--mode sweep` 재측정의 세션 1이 이 ELF를 요구하므로 실칩 재측정을
하는 사람은 같이 빌드해 둔다 (로그 36).

```bash
vitis -s ps/scripts/build_flash_id.py        # 또는 uv run python reproduce.py --only id
```

```text
build/vitis_id/flash_id/build/flash_id.elf
```

### 3.4 g3 — 실칩 스윕 계측기 (클럭별)

클럭별로 프로젝트 폴더가 분리된다. g0과 같은 골격이며 차이는 SPI 프런트엔드
(`flash_top_spi.v`), JB 핀 XDC(`g3_*.xdc`), 클럭별 분주 파라미터. 스윕 앱은 g0과 같은
`ps/src/g0_sweep.c`를 `G3_MHZ`로 분기해 쓴다.

```bash
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 25
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 45
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 75
```

약 2분/클럭.

기대 산출물 (`<mhz>` = 25 · 45 · 75):

```text
build/vivado_g3_<mhz>/g3_chip_<mhz>.runs/impl_1/g3_wrapper.bit
build/vivado_g3_<mhz>/g3_chip_<mhz>.xsa
build/vitis_g3_<mhz>/g3_sweep/build/g3_sweep.elf
```

기대 출력: 클럭마다 `== timing: WNS=양수` · `== all done: bit=… elf=…`.
`[검증 2026-09-14]` 25: 23:02 · 45: 23:04 · 75: 23:06 전부 통과 (수치는 §3.6 표).

### 3.5 wear — P/E 마모 엔진

g2 XSA 에서 마모 엔진 앱을 만든다 (`docs/interface/pe_engine.md`, S-1 §6). 실칩 P/E 인수(워크플로 12)가
이 ELF 를 요구한다.

```bash
vitis -s ps/scripts/build_flash_wear.py                          # 또는 python3 reproduce.py --only wear
WEAR_SPI_PRESCALE=16 vitis -s ps/scripts/build_flash_wear.py     # 8·16·64 — 실측 뒤 사람이 고른다 (워크플로 12 §6)
```

입력은 `build/vivado_g2/g2_jedec.xsa` · `ps/src/flash_wear.c` · `wear_plat_zynq.c` · `flash_io.c`.
`git rev-parse --short HEAD` 가 `build/wear_gen/wear_build.h` 로 들어가 엔진의 `#WEAR H` 행에 박힌다. 약 20초.

기대 산출물:

```text
build/vitis_wear/flash_wear/build/flash_wear.elf
```

기대 출력: `== done (git_rev <HEAD>, spi prescale 64 (default)): …/flash_wear.elf`. **`git_rev` 가 지금
체크아웃과 같아야 한다** — 커밋 전에 구우면 한 커밋 전 rev 가 박힌 채 실칩 기록에 남는다. `reproduce.py`
는 이것을 ⑥ 으로 대조한다. `[검증 2026-09-21]` 02:18 통과 (git_rev ebc5be2).

### 3.6 빌드 확인

존재 + 타이밍:

```bash
ls build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit build/vitis/g0_sweep/build/g0_sweep.elf \
   build/vivado_g2/g2_jedec.xsa build/vitis_prep/flash_prep/build/flash_prep.elf \
   build/vitis_wear/flash_wear/build/flash_wear.elf \
   build/vivado_g3_25/g3_chip_25.runs/impl_1/g3_wrapper.bit build/vitis_g3_25/g3_sweep/build/g3_sweep.elf
grep -L "All user specified timing constraints are met" build/vivado*/*.runs/impl_1/*_timing_summary_routed.rpt
```

기대 결과: `ls`는 전부 존재, `grep -L`은 **아무 파일도 출력하지 않는다** (출력된 파일 =
타이밍 위반 = 그 비트로 측정 금지).

수치 대조 — 같은 커밋·같은 2025.2면 다른 PC에서도 같은 값이 나와야 한다. `.bit` 자체는
헤더에 생성 시각이 들어가 해시 비교가 안 되므로 타이밍·자원 수치로 대조한다:

```bash
for R in build/vivado/g0_loopback.runs/impl_1/g0_wrapper build/vivado_g3_*/g3_chip_*.runs/impl_1/g3_wrapper; do
  echo "$R"
  grep -A8 'Design Timing Summary' ${R}_timing_summary_routed.rpt | grep -E '^\s+-?[0-9]+\.' | head -1 | awk '{print "  WNS="$1, "TNS="$2, "WHS="$5}'
  grep -E '^\| (Slice LUTs|Slice Registers)' ${R}_utilization_placed.rpt | head -2 | awk -F'|' '{gsub(/ /,"",$2); gsub(/ /,"",$3); print "  "$2"="$3}'
done
```

기준값 (영웅 PC, 2026-09-14 23:06, RTL·tcl은 `e229b04` 이후 변경 없음):

| 빌드  | WNS / WHS (ns) | Slice LUTs / Registers |
| ----- | -------------- | ---------------------- |
| g0    | 29.811 / 0.096 | 900 / 1,013            |
| g3-25 | 5.366 / 0.111  | 912 / 1,035            |
| g3-45 | 6.201 / 0.105  | 913 / 1,035            |
| g3-75 | 2.957 / 0.082  | 913 / 1,035            |

**2026-09-16 재검증**: 같은 PC에서 `build/`를 비켜 두고 맨바닥 재빌드 2회 — 네 수치 전부 위
표와 일치(FAIL 0, WARN 0). 로그 33의 이식성 수정이 산출물을 바꾸지 않았다는 근거다 (로그 33 §3).

값이 다르면 실패는 아니지만 로그에 적는다. 소스가 같은데 배치가 다르다는 뜻이고, 그
차이가 폭 측정에 나타나는지는 측정으로만 안다.

## 4. 산출물을 보드에 굽는 명령

빌드 산출물을 쓰는 첫 행위. 보드 USB 연결(JTAG+UART 겸용 1개), JP5 = **JTAG** 부팅 모드.
측정 절차 자체(캡처 순서·배선·판정)는 런북 3 · 워크플로 7을 따른다.

| 무엇을                | 명령                                                                                | 쓰는 산출물                          |
| --------------------- | ----------------------------------------------------------------------------------- | ------------------------------------ |
| 루프백 계측기         | `xsct ps/scripts/program_g0.tcl`                                                  | g0 bit + elf + ps7_init.tcl          |
| 사전 쓰기·UID (실칩) | `xsct ps/scripts/program_g2.tcl build/vitis_prep/flash_prep/build/flash_prep.elf` | g2 bit(XSA에서 자동 추출) + prep elf |
| 신원 확인만 (P/E 불변) | `xsct ps/scripts/program_g2.tcl build/vitis_id/flash_id/build/flash_id.elf`     | 같은 g2 bit + id elf                 |
| 실칩 스윕             | `xsct ps/scripts/program_g3.tcl 25` (`45`/`75`, 보험 `25 pl4`)              | g3-<mhz></mhz> bit + elf             |
| 실칩 전 과정 한 줄    | `uv run python host/run/run_sweep_chip.py --mhz 25`                               | 위 둘을 래퍼가 순서대로 호출         |
| P/E 마모 엔진 (실칩)  | `uv run python host/run/run_wear.py accept --chip chip01 --base-sector 1000 --cycle 0 --to 100` | g2 bit + wear elf — 실행기가 xsct 를 부른다. 절차·판독은 워크플로 12 |

루프백 최소 확인 (점퍼 JE1↔JE2). 캡처를 **먼저** 켠다 — 첫 줄(BEGIN)부터 받아야 한다:

```bash
uv run python host/capture/sweep_uart_capture.py --loopback --port /dev/ttyUSB1   # 터미널 1
xsct ps/scripts/program_g0.tcl                                                     # 터미널 2
```

기대 결과: 터미널 1에 수 초 내 `#G0 SWEEP BEGIN …`, 약 10분 뒤
`#G0 SWEEP END valid=1 reason=complete`, `build/data/sweep_loopback_<stamp>.csv` 생성.
`TIMEOUT`이면 점퍼 미접촉, BEGIN 자체가 안 뜨면 포트(§1).

`BUILD_DIR=<폴더>` 환경변수를 앞에 붙이면 `build/` 대신 그 폴더의 산출물을 굽는다 (기본 `build`).

## 5. 검증 파이프라인

RTL을 바꾸거나 결과를 기록하기 전에 사용한다. 보드가 필요 없다.

### 5.1 RTL 스모크 시뮬레이션

cocotb 회귀(G1)가 확립되기 전까지의 최소 회귀. 순수 Verilog TB + `unisim_stub.v`(MMCM·ODDR 스텁).
`sim/smoke/` 디렉터리에서:

```bash
cd sim/smoke
iverilog -g2005 -o /tmp/tb_core.vvp  tb_core_smoke.v      unisim_stub.v ../../fpga/rtl/core/*.v                          && vvp /tmp/tb_core.vvp
iverilog -g2005 -o /tmp/tb_flash.vvp tb_flash_smoke.v     unisim_stub.v ../../fpga/rtl/flash/*.v                         && vvp /tmp/tb_flash.vvp
iverilog -g2005 -o /tmp/tb_spi.vvp   tb_flash_spi_smoke.v unisim_stub.v ../../fpga/rtl/flash/*.v                         && vvp /tmp/tb_spi.vvp
iverilog -g2005 -o /tmp/tb_g0.vvp    tb_g0_smoke.v        unisim_stub.v ../../fpga/rtl/core/*.v ../../fpga/rtl/flash/*.v && vvp /tmp/tb_g0.vvp
cd ../..
```

기대 결과: 네 TB 모두 `PASS` 줄을 찍고 FAIL/ERROR 없이 `$finish`. `[검증 2026-09-14]` 4/4 PASS.

G1 cocotb 회귀(`sim/tb/`, 박지민)는 구축 중이다. 기준은 `docs/spec/s3.g1_test_plan.md`,
커버리지 대조는 `python3 sim/check_coverage.py --results sim/build/results.xml`.

### 5.2 호스트 셀프테스트

```bash
uv run python host/analysis/bathtub_analysis.py --selftest
uv run python host/capture/chip_registry.py --selftest
uv run python host/run/chip_pe.py --selftest
```

기대 결과: 등록부·P/E 이력은 `selftest PASS`, 분석기는 셀프테스트 그림(`build/plots/bathtub_selftest_*.png`)과 체크리스트 PASS. `[검증 2026-09-14]` 3/3 통과.

### 5.3 블랙박스 TB — P/E 엔진

`docs/spec/s4.blackbox_tb.md` 의 채점표를 세 층으로 돌린다 — ① 가짜 엔진(mock) 채점과 「버그 심은 엔진을
떨어뜨리는지」(T6), ② 같은 `flash_wear.c` 를 가짜 NOR 위에 gcc 로 올린 호스트 시뮬레이션을 UART 어댑터로
채점, ③ 실행기 `run_wear.py` 의 accept·resume·status 를 시뮬레이션에 붙여 종단 확인. 보드 불필요.

```bash
uv run pytest host/tests/ -q            # 또는 python3 reproduce.py --only tb
```

기대 결과: `114 passed`. `[검증 2026-09-21]` 통과 (11초). **gcc 가 없으면** ② 가 skip 되고
`test_gcc_absent_is_reported_not_hidden` 1개가 FAIL 한다 — 조용히 넘어가지 않게 둔 의도된 실패이니
`build-essential` 을 깔고 다시 돌린다. Windows 네이티브는 ② 가 POSIX(`poll.h`) 라 지원하지 않는다 — WSL 로.

시뮬레이션을 손으로 굴려 출력 모양을 익히려면 (P/E 없음, 결과는 `build/logs/wear/<session>/`):

```bash
uv run python host/run/run_wear.py accept --sim build/sim/flash_wear_sim --no-program
```

## 6. 빠른 재빌드

RTL·XDC는 그대로이고 `ps/src/*.c`만 바뀐 경우, Vivado를 다시 돌리지 않고 기존 XSA에서 ELF만
재생성한다 (워크스페이스는 지우고 다시 만들지만 20초 안팎):

```bash
vitis -s ps/scripts/build_g0_sweep.py                  # g0 스윕 앱   ← build/vivado/g0_loopback.xsa
vitis -s ps/scripts/build_flash_prep.py                # prep 앱      ← build/vivado_g2/g2_jedec.xsa
vitis -s ps/scripts/build_flash_wear.py                # 마모 엔진    ← 같은 g2 XSA (커밋 뒤에 굽는다 — §3.5)
G3_MHZ=25 vitis -s ps/scripts/build_g3_sweep.py        # g3 스윕 앱   ← build/vivado_g3_25/g3_chip_25.xsa
```

기대 산출물: 해당 `build/vitis*/…/*.elf` 갱신. 이후 프로그래밍은 반드시 **전체 경로**
(`program_*.tcl`)로 — ELF만 재로드하면 MMCM 위상이 남아 `phase_pos_mismatch`로 거부된다
(의도된 방어).

RTL이 바뀌었으면 지름길이 없다 — 해당 tcl을 처음부터 (§3).

래퍼로는 `python3 reproduce.py --vitis-only` (g0·prep·prep-wear·id·wear·g3 ×3 ELF + §5 검증).

## 7. 산출물 트리

```text
build/
├── vivado/                 g0: g0_loopback.xsa, g0_loopback.runs/impl_1/g0_wrapper.bit, 리포트(.rpt)
├── vitis/                  g0: g0_plat/(플랫폼), g0_sweep/build/g0_sweep.elf, g0_sweep/_ide/psinit/ps7_init.tcl
├── vivado_g2/              g2: g2_jedec.xsa, g2_jedec.runs/impl_1/g2_wrapper.bit
├── vitis_prep/             flash_prep/build/flash_prep.elf
├── vitis_id/               flash_id/build/flash_id.elf   (sweep 모드 세션1이 요구)
├── vitis_wear/             flash_wear/build/flash_wear.elf   (P/E 인수 — 워크플로 12)
├── wear_gen/               wear_build.h (git_rev — build_flash_wear.py 가 생성)
├── vitis_prep_0_7/         prep 체크포인트 모드(마모 그룹 0~6) — reproduce.py `prep-wear` 단계. run_wear.py 체크포인트가 이 ELF 를 올린다 (2026-09-22 필수로 승격)
├── vitis_prep_<base>_<n>/  (선택) 다른 범위 — PREP_BASE=<base> PREP_N=<n> vitis -s …build_flash_prep.py (대조군 스윕이 열리면 reproduce 에 넣는다, [U44-8])
├── sim/                    flash_wear_sim — TB 의 C 엔진 호스트 시뮬레이션 (gcc, §5.3이 매번 다시 만든다)
├── vitis_jedec/            (선택) flash_jedec/build/flash_jedec.elf
├── vitis_smoke/            (선택) core_smoke/build/core_smoke.elf
├── vivado_g3_25/ 45/ 75/   g3: g3_chip_<mhz>.xsa, g3_chip_<mhz>.runs/impl_1/g3_wrapper.bit
├── vitis_g3_25/ 45/ 75/    g3: g3_sweep/build/g3_sweep.elf
├── data/                   측정 CSV·세션 로그 (빌드 산출물 아님 — 측정 때 생김)
├── logs/                   reproduce_<UTC>/ (채점 로그) · wear/<session>/ (P/E 시험 verdict — 승격은 docs/results/)
└── plots/                  분석 그림 (빌드 산출물 아님)
```

전부 `.gitignore`. `rm -rf build`로 지우고 §3으로 처음부터 다시 만들 수 있어야
한다 — 그것이 재현이다. 측정 원본 CSV는 `build/data/`에서 `data/`로 옮겨 보관한다(CONTRIBUTING).

## 8. 디버그·과거 흐름

메인 재현 경로가 아니라 브링업·근본원인 도구로 남아 있는 것들:

- **core_smoke** — PS↔PL AXI-Lite 스모크 앱 (세은). `vitis -s ps/scripts/build_core_smoke.py`
  → `xsct ps/scripts/program_core_smoke.tcl` → miniterm에서 6개 테스트 PASS/FAIL.
  TEST4·5는 JE1↔JE2 점퍼가 있어야 완주.
- **flash_jedec** — G2 JEDEC ID(`EF 40 17`) 확인 앱. `vitis -s ps/scripts/build_flash_jedec.py`
  → `xsct ps/scripts/program_g2.tcl build/vitis_jedec/flash_jedec/build/flash_jedec.elf`.
  실칩 측정엔 불필요 (flash_prep이 JEDEC 검사를 포함).
- **PAY_LEAD 보험 비트** — 실칩에서 전 위상 BER≈0.5(정렬 창 이탈)일 때만.
  `vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs bit 25 <k>` (k=4|6) →
  `build/vivado_g3_25_pl<k>/` → `xsct ps/scripts/program_g3.tcl 25 pl<k>` 또는 래퍼 `--pl <k>`.
- **UART 직접 보기** — `uv run python -m serial.tools.miniterm /dev/ttyUSB1 921600`.
  (2026-09-15부터 전 앱이 925,925bps. 구형 ELF 를 굽는다면 115200)
  캡처와 같은 포트라 동시에 못 연다.
- **옛 명령** — 런북 3·로그 13의 `sweep_uart_capture.py --target …`은 로그 24에서
  `--loopback` / `--uid <16hex>`로 바뀌었다. 실칩은 래퍼(`host/run/run_sweep_chip.py`)가 정식 경로.
- 브링업 고장 판독(TIMEOUT·line_dead·no_window·FF FF FF …)은 런북 3 표 E.
