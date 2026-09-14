# 빌드 재현 절차 — 무엇을, 어떤 순서로, 어떤 명령으로 만드나

- **작성일**: 2026-09-14. Vivado/Vitis **2025.2** 기준. 표의 `검증` 열은 이 날 영웅 PC(Ubuntu 24)에서 실제로 통과한 기록.
- **재현의 정의**: 저장소의 소스(RTL·XDC·tcl·C)로부터 `build/` 아래 산출물(비트스트림·XSA·ELF)을 다시 만드는 것. `build/`는 커밋하지 않으므로 **측정하는 PC마다 이 절차로 만든다.** 남의 `build/`를 복사하면 어느 소스·어느 버전으로 만든 계측기인지 추적이 끊긴다.
- **측정·분석 절차는 이 문서 범위 밖**: 루프백은 런북 3 C절, 실칩 당일은 워크플로 7, 래퍼 옵션은 `host/run/run_sweep_chip.py --help`.

## 목차

1. [전제](#1-전제) — 셸에 2025.2, 리포 루트
2. [빌드 순서와 의존 관계](#2-빌드-순서와-의존-관계)
3. [단계별: 산출물 · 명령 · 검증](#3-단계별-산출물--명령--검증)
4. [산출물 트리](#4-산출물-트리)
5. [재현됐는지 확인](#5-재현됐는지-확인)
6. [산출물을 보드에 굽는 명령](#6-산출물을-보드에-굽는-명령)

---

## 1. 전제

```bash
source <설치루트>/2025.2/Vitis/settings64.sh   # Vivado·xsct·vitis 전부 PATH에 오른다
which vivado && vivado -version | head -1        # <설치루트>/2025.2/Vivado/bin/vivado, "v2025.2"
cd <리포 루트>                                   # 모든 명령은 여기서
```

- 버전 가드: 빌드 tcl 3개가 `2025.2*`가 아니면 즉시 에러. 2024.2·2025.1 불가.
- `.bashrc`에 settings64.sh는 **한 줄만**. 두 버전을 연달아 source하면 PATH가 섞인다.
- 파이썬(`uv sync`)은 빌드에 필요 없다. 측정·분석 때 필요.

## 2. 빌드 순서와 의존 관계

```
g0  ─────────────────────────────────────────────►  루프백 계측기 (독립)
g2  ──► prep (g2 XSA 소비)  ─────────────────────►  실칩 사전 쓰기·UID
g3-25 ┐
g3-45 ├──────────────────────────────────────────►  실칩 스윕 계측기 (클럭별, 서로 독립)
g3-75 ┘
```

- **g0**만 있으면 루프백 측정(G0)이 된다.
- **실칩**은 g2 → prep → g3-25 세 개가 최소. 45·75는 클럭 사다리 때.
- g3 세 벌은 서로 독립이라 어느 순서든 된다. 단 g2보다 뒤에 만들 이유는 없고 앞에 만들 이유도 없다.
- 각 tcl은 프로젝트를 **처음부터 재생성**한다. `.xpr`을 열어 이어 빌드하지 않는다.

## 3. 단계별: 산출물 · 명령 · 검증

### 3.1 g0 — 루프백 계측기

| | |
| - | - |
| **재현 대상** | `build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit` (PL 비트스트림) · `build/vivado/g0_loopback.xsa` (하드웨어 플랫폼, 비트 포함) · `build/vitis/g0_sweep/build/g0_sweep.elf` (PS 스윕 앱) · `build/vitis/g0_sweep/_ide/psinit/ps7_init.tcl` (PS 초기화, 프로그래밍 때 사용) |
| **입력** | `fpga/rtl/core/*.v` · `fpga/rtl/flash/flash_top.v` 계열 · `fpga/constraints/g0_*.xdc` · `fpga/boards/`(벤더링 보드파일) · `ps/src/g0_sweep.c` |
| **명령** | `vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl` |
| **내부 순서** | 프로젝트 생성 → BD 조립 → 합성 → 구현 → 비트스트림 → XSA → `vitis -s ps/scripts/build_g0_sweep.py`(ELF) |
| **소요** | 약 8분 |
| **검증** | 마지막 줄 `== all done: bit=… elf=…` · `== timing: WNS=양수 WHS=양수` |
| **검증 기록** | 2026-09-14 22:58 통과. WNS 29.811 / WHS 0.096, LUT 900 / FF 1,013 |

부분 실행: `-tclargs bd`(BD 검증만) · `-tclargs bit`(ELF 생략).

### 3.2 g2 — 실칩 JEDEC 브링업 비트

| | |
| - | - |
| **재현 대상** | `build/vivado_g2/g2_jedec.xsa` · `build/vivado_g2/g2_jedec.runs/impl_1/g2_wrapper.bit` |
| **입력** | `fpga/constraints/g2_jedec_pins.xdc` · 보드파일. PL 로직 없음 — PS SPI0을 EMIO로 JB 핀에 라우팅만 |
| **명령** | `vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl` |
| **소요** | 약 1분 |
| **검증** | 마지막 줄 `== done: …/g2_jedec.xsa (bit: …)` |
| **검증 기록** | 2026-09-14 23:00 통과 |

### 3.3 prep — 사전 쓰기·UID 앱 (g2 XSA 소비)

| | |
| - | - |
| **재현 대상** | `build/vitis_prep/flash_prep/build/flash_prep.elf` |
| **입력** | `build/vivado_g2/g2_jedec.xsa` (3.2) · `ps/src/flash_prep.c` |
| **명령** | `vitis -s ps/scripts/build_flash_prep.py` |
| **소요** | 약 20초 |
| **검증** | 마지막 줄 `== done: …/flash_prep.elf` |
| **검증 기록** | 2026-09-14 23:00 통과 |

같은 방식의 다른 앱: `vitis -s ps/scripts/build_flash_jedec.py` → `build/vitis_jedec/flash_jedec/build/flash_jedec.elf` (G2 JEDEC 확인용, 실칩 측정엔 불필요).

### 3.4 g3 — 실칩 스윕 계측기 (클럭별)

| | |
| - | - |
| **재현 대상** | `build/vivado_g3_<mhz>/g3_chip_<mhz>.runs/impl_1/g3_wrapper.bit` · `build/vivado_g3_<mhz>/g3_chip_<mhz>.xsa` · `build/vitis_g3_<mhz>/g3_sweep/build/g3_sweep.elf` |
| **입력** | `fpga/rtl/core/*.v` · `fpga/rtl/flash/flash_top_spi.v` 계열 · `fpga/constraints/g3_*.xdc` · 보드파일 · `ps/src/g0_sweep.c`(g3도 같은 스윕 앱, `G3_MHZ`로 분기) |
| **명령** | `vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 25` — `45`, `75`도 같은 식 |
| **내부 순서** | g0과 동일 골격. 차이는 SPI 프런트엔드, JB 핀 XDC, 클럭별 분주 파라미터, 클럭별 프로젝트 폴더 분리 |
| **소요** | 약 2분/클럭 |
| **검증** | `== timing: WNS=양수` · `== all done: bit=… elf=…` |
| **검증 기록** | 2026-09-14 세 벌 전부 통과 (25: 23:02 · 45: 23:04 · 75: 23:06). 수치는 §5 표 |

보험 비트(PAY_LEAD 어긋날 때): `-tclargs bit 25 <k>` → `build/vivado_g3_25_pl<k>/…`. 평소엔 만들지 않는다.

### 3.5 한 번에 전부

```bash
vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl
vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl
vitis  -s ps/scripts/build_flash_prep.py
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 25
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 45
vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all 75
```

약 15분. 하나가 실패하면 그 자리에서 멈추고 로그(`vivado.log`, 리포 루트에 생김)를 본다.

## 4. 산출물 트리

```
build/
├── vivado/                 g0: g0_loopback.xsa, g0_loopback.runs/impl_1/g0_wrapper.bit, 리포트(.rpt)
├── vitis/                  g0: g0_plat/(플랫폼), g0_sweep/build/g0_sweep.elf, g0_sweep/_ide/psinit/ps7_init.tcl
├── vivado_g2/              g2: g2_jedec.xsa, g2_jedec.runs/impl_1/g2_wrapper.bit
├── vitis_prep/             prep: flash_prep/build/flash_prep.elf
├── vitis_jedec/            (선택) flash_jedec/build/flash_jedec.elf
├── vivado_g3_25/ 45/ 75/   g3: g3_chip_<mhz>.xsa, g3_chip_<mhz>.runs/impl_1/g3_wrapper.bit
├── vitis_g3_25/ 45/ 75/    g3: g3_sweep/build/g3_sweep.elf
├── data/                   측정 CSV (빌드 산출물 아님 — 측정 때 생김)
└── plots/                  분석 그림 (빌드 산출물 아님)
```

전부 `.gitignore`. `rm -rf build`로 지우고 §3.5로 처음부터 다시 만들 수 있어야 한다 — 그것이 재현이다.

## 5. 재현됐는지 확인

**존재 + 타이밍**:

```bash
ls build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit build/vitis/g0_sweep/build/g0_sweep.elf \
   build/vivado_g2/g2_jedec.xsa build/vitis_prep/flash_prep/build/flash_prep.elf \
   build/vivado_g3_25/g3_chip_25.runs/impl_1/g3_wrapper.bit build/vitis_g3_25/g3_sweep/build/g3_sweep.elf
grep -L "All user specified timing constraints are met" build/vivado*/*.runs/impl_1/*_timing_summary_routed.rpt
# ↑ 아무 파일도 출력되지 않아야 한다. 출력된 파일 = 타이밍 위반 = 그 비트로 측정 금지
```

**수치 대조** — 같은 커밋·같은 2025.2면 조원 PC에서도 같은 값이 나와야 한다. `.bit` 자체는 헤더에 생성 시각이 들어가 해시 비교가 안 되므로 타이밍·자원 수치로 대조한다.

```bash
for R in build/vivado/g0_loopback.runs/impl_1/g0_wrapper build/vivado_g3_*/g3_chip_*.runs/impl_1/g3_wrapper; do
  echo "$R"
  grep -A8 'Design Timing Summary' ${R}_timing_summary_routed.rpt | grep -E '^\s+-?[0-9]+\.' | head -1 | awk '{print "  WNS="$1, "TNS="$2, "WHS="$5}'
  grep -E '^\| (Slice LUTs|Slice Registers)' ${R}_utilization_placed.rpt | head -2 | awk -F'|' '{gsub(/ /,"",$2); gsub(/ /,"",$3); print "  "$2"="$3}'
done
```

기준값 (영웅 PC, 2026-09-14 23:06, RTL·tcl은 `e229b04` 이후 변경 없음):

| 빌드 | WNS / WHS (ns) | Slice LUTs / Registers |
| ---- | -------------- | ---------------------- |
| g0 | 29.811 / 0.096 | 900 / 1,013 |
| g3-25 | 5.366 / 0.111 | 912 / 1,035 |
| g3-45 | 6.201 / 0.105 | 913 / 1,035 |
| g3-75 | 2.957 / 0.082 | 913 / 1,035 |

값이 다르면 실패는 아니지만 로그에 적는다. 소스가 같은데 배치가 다르다는 뜻이고, 그 차이가 폭 측정에 나타나는지는 측정으로만 안다.

## 6. 산출물을 보드에 굽는 명령

빌드 산출물을 쓰는 첫 행위. 보드 USB 연결, JP5=JTAG. 측정 절차 자체는 원전(런북 3 · 워크플로 7)을 따른다.

| 무엇을 | 명령 | 쓰는 산출물 |
| ------ | ---- | ----------- |
| 루프백 계측기 | `xsct ps/scripts/program_g0.tcl` | g0 bit + elf + ps7_init.tcl |
| 사전 쓰기·UID (실칩) | `xsct ps/scripts/program_g2.tcl build/vitis_prep/flash_prep/build/flash_prep.elf` | g2 bit(XSA에서 자동 추출) + prep elf |
| 실칩 스윕 | `xsct ps/scripts/program_g3.tcl 25` (`45`/`75`, 보험 `25 pl4`) | g3-<mhz> bit + elf |
| 실칩 전 과정 한 줄 | `uv run python host/run/run_sweep_chip.py --mhz 25` | 위 둘을 래퍼가 순서대로 호출 |

`BUILD_DIR=<폴더>` 환경변수를 앞에 붙이면 `build/` 대신 그 폴더의 산출물을 굽는다 (기본 `build`).
