# 프로젝트 파이프라인

- **작성일**: 2026-09-15
- **용도**: "어떤 스크립트를 치면 무슨 파일이 생기고, 그 파일이 다음 단계에서 무엇으로 쓰이는가"를
  한 문서에서 따라가기 위한 지도.
- 실험 서사(왜 재는가)는 `docs/project_context.md`, 게이트 정의는
  `docs/workflow/4.gate_map.md`가 원전이고 **본 문서는 그 사이의 흐름을 그린다.**
- 소스

  | 층                              | 원전                                                                                  |
  | ------------------------------- | ------------------------------------------------------------------------------------- |
  | 빌드 명령·기대 출력·검증 수치 | `docs/build_reproduction.md`                                                        |
  | 측정 당일 절차·고장 판독표     | `docs/workflow/3.realchip_day_runbook.md` · `7.realchip_uid_verification_day.md` |
  | 게이트 정의·이름 규칙          | `docs/workflow/4.gate_map.md`                                                       |
  | CSV 스키마·무효 런 정의        | `docs/interface/contract.md` §6                                                    |
  | 신품 전수 측정 절차             | `docs/spec/s2.newchip_protocol.md`                                                  |
  | 마모 벤치 절차·인수 기준       | `docs/spec/s1.wear_bench_spec.md`                                                   |

  본 문서는 이들을 **연결만** 한다. 합격 기준·문턱값·시료 배분표를 여기에 복제하지 않는다
  (복제하면 원전과 어긋나는 문서가 하나 더 생긴다).
- **표기**: 각 절 머리에 **[동작]** / **[부분]** / **[미구현]** 을 붙인다. 이 문서를 읽고
  "그럼 지금 P/E를 돌릴 수 있겠네"로 오독하는 것을 막기 위한 장치다.
- **용어** (로그 29 §7): 읽기 마진 측정 = **스윕**, 그 그림 = **욕조 곡선**, P/E 마모 = **마모 벤치**.
  문장에서는 **측정 경로(스윕, PL) / 마모 경로(P/E, PS SPI)** 로 가른다.

---

## 0. 한 장 지도

```
  [소스]                          [빌드 산출물]                 [측정 산출물]              [게재물]

  fpga/rtl/core/ · flash/  ┐
  fpga/constraints/*.xdc   ┼─ vivado ─► build/vivado*/ *.bit + *.xsa
  fpga/scripts/*.tcl       ┘                    │
                                                ├─ vitis ─► build/vitis*/ *.elf
  ps/src/g0_sweep.c        ────────────────────┘                │
  ps/src/flash_prep.c      ──────────────────────────────────────┤
                                                                 │  xsct program_*.tcl
                          ┌──────────────────────────────────────┴──────────────────┐
                          │                                                          │
             [마모 경로]  PS SPI · g2_jedec 비트                  [측정 경로]  PL · g3_chip_<mhz> 비트
             flash_prep.elf                                       g3_sweep.elf
                          │  UART: #PREP UID / BLANK / ERASE / PASS  │  UART: #G0 SWEEP BEGIN…END
                          └──────────────────────────────────────┬──┘
                                                                 │
                       host/run/run_sweep_chip.py  (두 세션을 한 프로세스가 잇는다)
                                  └─ host/capture/sweep_uart_capture.py
                                  └─ host/capture/chip_registry.py   (UID → 라벨 역조회)
                                  └─ host/run/chip_pe.py             (P/E 이력 +1)
                                                                 │
                    build/data/  sweep_<label>_<uid16>_<stamp>.csv · _reads.csv · session_*.log
                                                                 │
                       host/analysis/bathtub_analysis.py      → build/plots/*.png + 폭 3종(θ)
                       host/analysis/repeatability_aggregate.py → 평균 ± σ + 대표 곡선
                                                                 │
                    data/ (원본 보관)   docs/results/ (승격)   docs/chip_registry.md · chip_pe.md (기입)
```

읽는 요령 두 가지.

1. **가로는 층위 4단**이다 — 빌드 → 측정 → 분석 → 기록. 층을 건너뛰는 지름길은 없다.
2. **세로는 경로 2개**다 — 같은 칩에 마모 경로(PS가 SPI로 직접 때린다)와 측정 경로(PL이 위상을
   밀며 읽는다)가 번갈아 닿는다. **둘은 비트스트림이 다르고 서로를 볼 수 없다**(로그 29 F5).
   그래서 "칩 1개 = 1세션"이 절차 규칙으로 강제된다(S-2 §3.2) — 하드웨어가 보증해 주지 않는다.

---

## 1. 0단계 — 계측기를 만든다 (빌드) **[동작]**

측정 산출물을 논하기 전에 계측기부터 만든다. `build/`는 커밋하지 않으므로 **측정하는 PC마다**
아래를 돌린다. 명령·기대 출력·기준 수치(WNS·LUT)는 `docs/build_reproduction.md` §3이 원전이고,
여기서는 "무엇이 무엇을 낳는가"만 적는다.

| 대상             | 명령                                                                                  | 산출물                                                                                 | 소요      |
| ---------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------- |
| g0 루프백 계측기 | `vivado -mode batch -source fpga/scripts/build_g0_loopback.tcl`                     | `build/vivado/g0_loopback.{bit,xsa}` + `build/vitis/g0_sweep/build/g0_sweep.elf`   | ~8분      |
| g2 브링업 비트   | `vivado -mode batch -source fpga/scripts/build_g2_jedec.tcl`                        | `build/vivado_g2/g2_jedec.{bit,xsa}`                                                 | ~1분      |
| prep 앱          | `vitis -s ps/scripts/build_flash_prep.py`                                           | `build/vitis_prep/flash_prep/build/flash_prep.elf`                                   | ~20초     |
| g3 스윕 계측기   | `vivado -mode batch -source fpga/scripts/build_g3_chip.tcl -tclargs all <25\|45\|75>` | `build/vivado_g3_<mhz>/…bit` + `build/vitis_g3_<mhz>/g3_sweep/build/g3_sweep.elf` | ~2분/클럭 |

의존 사슬: **g2 XSA → prep ELF**, **g3 XSA → g3_sweep ELF**. g0은 독립이다.

### 1.1 굽기 — 산출물이 보드로 가는 자리

JTAG 프로그래밍은 `xsct`가 한다. bit·ELF·`ps7_init.tcl`을 한 묶음으로 올리므로 **ELF만 재로드하는
경로를 두지 않는다**(MMCM 위상이 남아 `phase_pos_mismatch`로 거부된다 — 의도된 방어).

| 무엇을                | 명령                                                                                |
| --------------------- | ----------------------------------------------------------------------------------- |
| 루프백 계측기 (G0)    | `xsct ps/scripts/program_g0.tcl`                                                  |
| 사전 쓰기·UID (실칩) | `xsct ps/scripts/program_g2.tcl build/vitis_prep/flash_prep/build/flash_prep.elf` |
| 실칩 스윕             | `xsct ps/scripts/program_g3.tcl 25` (`45`/`75`, 보험 `25 pl4`)              |

실칩은 **뒤 둘을 사람이 직접 치지 않는다** — 래퍼가 순서대로 호출한다(§2.1). 직접 치는 것은
루프백뿐이고, 그때도 캡처를 **먼저** 켠다:

```bash
uv run python host/capture/sweep_uart_capture.py --loopback --port /dev/ttyUSB1   # 터미널 1
xsct ps/scripts/program_g0.tcl                                                    # 터미널 2
```

### 1.2 한 소스가 두 앱이 되는 자리 — `g0_sweep.c`

`ps/src/g0_sweep.c` 하나가 루프백(g0)과 실칩(g3) 스윕 앱의 공통 원본이다. `build_g3_sweep.py`가
**사본을 떠서 상수 3개를 텍스트 치환**한다 (원본 무수정 원칙, 로그 8 R7):

| 상수            | 원본          | g3 치환값                                               |
| --------------- | ------------- | ------------------------------------------------------- |
| `SWEEP_STEPS` | 2,520         | 56 × O — 25MHz 2,520 / 45MHz 1,400 / 75MHz 840        |
| `F_SCLK_HZ`   | 25,000,000    | 클럭별                                                  |
| `N_READS_CFG` | **100** | **112** (수정안 #2, 2026-09-15 승인 — 실칩 전용) |

**루프백은 100을 유지한다.** 계측기 자기 이력과 비교하는 경로라 칩 데이터와 섞이지 않는다
(로그 29 §8.1). 즉 같은 파일에서 나온 두 ELF의 N이 서로 다르다 — 이것이 의도다.

### 1.3 보드 없이 도는 검증 루프

빌드 파이프라인과 별개로, RTL·호스트 코드를 만지면 먼저 여기를 통과시킨다.

| 무엇                       | 명령                                                                                               | 기대                       |
| -------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------- |
| RTL 스모크 4종             | `sim/smoke/`에서 `iverilog` + `vvp` (build_reproduction §5.1)                               | 4/4 PASS                   |
| 호스트 셀프테스트 3종      | `uv run python host/{analysis/bathtub_analysis,capture/chip_registry,run/chip_pe}.py --selftest` | 3/3 PASS                   |
| G1 cocotb 회귀**[미구현]** | `sim/tb/` (지민) + `python3 sim/check_coverage.py --results sim/build/results.xml`             | 23/23 항목 · 전 항목 PASS |

`check_coverage.py`는 **항목 누락만** 본다. 어서션이 그 항목을 실제로 재는지는 보지 않는다.

---

## 2. 1단계 — 신품 측정 **[부분: 게이트 2개 미구현]**

신품에서만 얻을 수 있는 값을 전부 걷는 단계다. **마모를 한 번이라도 시작하면 영원히 확보
불가능**하므로(S-2 머리말) 파이프라인에서 유일하게 "지금 안 하면 끝"인 자리다.

### 2.1 칩 하나 = 한 명령

```bash
uv run python host/run/run_sweep_chip.py --mode newchip --mhz 25 --n-reads 112
```

이 한 줄이 아래를 순서대로 한다 (`host/run/run_sweep_chip.py`, 로그 23·24).

```
  등록부 파싱 (깨져 있으면 보드를 건드리기 전에 죽는다)
  포트 개방 ──────────────────────────────── 캡처가 먼저다. 첫 줄을 놓치면 런이 무효
  세션1  xsct program_g2.tcl + flash_prep.elf
           #PREP JEDEC EF 40 17 → #PREP UID <16hex> → (BLANK/ERASE) → #PREP PASS
           UID로 docs/chip_registry.md 역조회 → 라벨 확정 → docs/chip_pe.md 에 +1 행
  세션2  xsct program_g3.tcl <mhz>   ×N회 (--repeat, --reseat)
           #G0 SWEEP BEGIN … END valid=1 reason=complete
           → build/data/sweep_<label>_<uid16>_<stamp>.csv (+ _reads.csv)
  종료   "k/N 완료" + build/data/session_<label>_<uid16>_<batch_id>.log
```

핵심은 **사람이 라벨을 입력하지 않는다**는 것이다. UID를 읽는 것은 세션 1(PS SPI)이고 CSV를
만드는 것은 세션 2(PL)라, 사람이 중간에 끼면 UID가 파일에 닿지 못한다. 래퍼의 존재 이유가 이것이다.

> S-2 §4의 `sweep_uart_capture.py --target chipNN` 표기는 **옛 명령**이다. 로그 24에서
> `--loopback` / `--uid <16hex>`로 바뀌었고, 실칩의 정식 경로는 래퍼다 (build_reproduction §8).

### 2.2 `flash_prep`이 내는 것

| 출력                                     | 무엇                                           | 상태                                                   |
| ---------------------------------------- | ---------------------------------------------- | ------------------------------------------------------ |
| `#PREP JEDEC EF 40 17`                 | 칩 동일성. 불일치면 스스로 중단                | 동작                                                   |
| `#PREP UID <16hex>`                    | 개체 정본 식별자 (4Bh ×3회 일치)              | 동작 (G-c)                                             |
| `#PREP PASS all 2048 pages verified`   | PRBS15 사전 쓰기 + 전수 read-back              | 동작                                                   |
| `#PREP BLANK pre/post` + `BLANKADDR` | 출고 시점 결함 비트 / 소거 잔여 비트 + 주소    | 구현됨 (G-d, 로그 30) —**미커밋·실칩 확인 전** |
| `#PREP ERASE <sector> <us>` + SUMMARY  | 섹터별 소거 시간 128건 = 노화 이중 지표의 후자 | 구현됨 (G-b, 로그 30) —**미커밋·실칩 확인 전** |

`blank_pre`는 **첫 소거와 함께 질문 자체가 소멸**한다. 그래서 이 둘이 S-2 §2의 게이트이고,
지금 chip02를 꽂으면 신품 데이터를 잃기만 하고 얻지 못한다. 확장 후 prep 소요는 16초 → 약 47초.

### 2.3 스윕이 산출하는 것

스윕 1회 = 위상 2,520스텝 × 112읽기 × 2,048비트(25MHz 기준), **59초**(UART 921600 실측). 산출물 3개:

| 파일                                       | 내용                                                                                                | 스키마 원전         |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------- | ------------------- |
| `sweep_<label>_<uid16>_<stamp>.csv`      | 위상 스텝 1행. 메타 열(target·generated_at·git_rev·uid·reseat·repeat_idx·batch_id) 전 행 반복 | 계약 §6 + 수정안#3 |
| `..._reads.csv`                          | 읽기별 에러 수 e_i 원본 (~27만 행).**선택이 아니라 필수** — 버스트성 검사(체크 4)의 입력     | 계약 결정 3-4       |
| `session_<label>_<uid16>_<batch_id>.log` | `#PREP` 전문 + 배치 진행. 시작부터 디스크에 쓴다 (Ctrl-C에도 UID가 남는다)                        | 로그 25             |

무효 런(계약 §6 ①~⑥)이면 두 CSV 모두 `_invalid` 접미가 붙는다. **필터 코드를 안 짜도 기본
동작이 안전한 쪽**이 되도록 파일명 층에서 처리한다.

### 2.4 분석 — 곡선에서 숫자로

```bash
uv run python host/analysis/bathtub_analysis.py build/data/sweep_<…>.csv
uv run python host/analysis/repeatability_aggregate.py <csv> <csv> ...      # 2개 이상
```

| 스크립트                        | 산출                                                                                                                                                   |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `bathtub_analysis.py`         | 유효 윈도우 폭 3종(θ=10⁻²/10⁻³/10⁻⁴) + 체크리스트 5종 판정 +`build/plots/*.png`. 동반 `_reads.csv`가 옆에 있으면 R8 무결성 검사를 자동 수행 |
| `repeatability_aggregate.py`  | 여러 런의 폭을 같은 알고리즘으로 구해**평균 ± 표준편차** + 대표 곡선 1장 (G4 에러바, 게재 4번)                                                  |
| `monte_carlo_sweep_params.py` | 측정**전에** N·θ를 정한 사전 등록 근거. 실측 σ_j가 나오면 재실행해 N을 재확인한다                                                             |

체크리스트 5는 곡선이 아니라 **RTL을 의심하라**는 신호다(프레이밍 슬립). 판정이 FAIL이면
데이터를 해석하지 않고 위로 되돌아간다.

### 2.5 기입 — 파이프라인이 문서로 끝나는 자리

| 목적지                    | 무엇                                                                  | 쓰는 주체                                      |
| ------------------------- | --------------------------------------------------------------------- | ---------------------------------------------- |
| `docs/chip_registry.md` | UID ↔ 라벨 대응표 (정본은 md 표 자체. 별도 CSV/JSON을 두지 않는다)   | `chip_registry.py` — 공란 채우기·행 추가만 |
| `docs/chip_pe.md`       | P/E 증분 이력 (append-only,`--blind`면 `(봉인)`)                  | `chip_pe.py`                                 |
| `docs/results/data/`    | 집계 md + 요약 CSV (개체 산포 σ, 소거 시간 기준선, blank, 재장착 σ) | 사람                                           |

### 2.6 지금 막혀 있는 곳

| 게이트 | 조건                          | 현재                                                                                |
| ------ | ----------------------------- | ----------------------------------------------------------------------------------- |
| G-a    | 드리프트 판정 (chip01 재측정) | **보류** — 재장착 σ 확보 후 판정 (워크플로 7)                               |
| G-b    | 섹터별 소거 시간 계측         | 코드 완료 (미커밋) ·**ELF 빌드 통과 2026-09-15 23:53** — 실칩 1회 확인 남음 |
| G-c    | UID 출력                      | 완료                                                                                |
| G-d    | blank check 판독              | G-b와 같음 (같은 파일·같은 구현)                                                   |

G-b·G-d는 `flash_prep.c` 단일 파일 변경이었고(명세 로그 30), 2026-09-15 구현이 working tree에
들어와 ELF 빌드까지 통과했다 — 커밋과 실칩 1회 확인이 남아 있다. **측정 데이터를 뜨기 전에
커밋한다**: CSV의 `git_rev` 열이 dirty tree를 가리키면 그 데이터의 출처가 재구성되지 않는다. **그것이 끝나면 남는 게이트는 G-a 하나**이며,
N=112는 게이트가 아니라 조건 통일 항목이다(로그 29 §8.3·로그 30 §9).

---

## 3. 주 루프 — 마모 체크포인트 루프 **[미구현]**

여기서부터가 프로젝트의 본체다. 위 1단계가 x=0 점 하나를 찍는 것이라면, 주 루프는 **같은 칩을
300k 사이클까지 태우며 x축을 만드는 것**이다.

### 3.1 루프의 모양

```
  초기화 1회 (S-1 §4)  UID 대조 → tally 섹터 소거 → 대조군·마모군 PRBS 기록 → blank check → 체크포인트 0

  반복 {
      마모 루프 (S-1 §6)          ① 0x00 프로그램 112페이지  → t_program_us
                                   ② 7섹터 소거              → 섹터별 t_erase_us
                                   ③ wear_loop_cycles +1
                                   ④ 검사 주기(100사이클)마다 blank check · tally 기록 · UID 재확인
      체크포인트 도달 (S-1 §5)     마모군·근접 대조군·원격 대조군 각각
                                     소거 → PRBS 기록 → verify → 스윕 ×반복
      다음 체크포인트 산정 (§11)   ×2.15 (조용할 때) / ×1.47 (직전 폭 변화 > 1.83ps)
  }  종점 300,000
```

**여기서 "읽기 스윕"은 루프와 병렬인 항목이 아니라 루프 안의 계측 프리미티브**다. 1단계에서 쓴
측정 경로를 그대로 다시 부른다 — 그래서 신품 측정을 N=112로 떠야 파일럿과 비교가 성립한다.

### 3.2 무엇을 만들어야 하는가

| 구성                 | 이름 (로그 29 §7)      | 상태                                                             |
| -------------------- | ----------------------- | ---------------------------------------------------------------- |
| 마모 엔진            | `flash_wear`          | **미구현.** 구현 층위(PS C vs PL RTL) 미확정 — 로그 29 D1 |
| 호스트 실행기        | `run_wear.py`         | **미구현**                                                 |
| 소거 시간 계측       | (prep 확장과 같은 코드) | **미구현** — G-b                                          |
| 사이클 카운터 영속화 | tally 섹터 2벌          | **미구현**                                                 |

확정된 경계는 **D2 — 반복은 PL, 판단은 PS**다. PL이 erase/program 발행·WIP 폴링·카운터·시간
측정을 맡고, PS가 체크포인트 판정·tally 기록·resume 복원·로그 포맷·UID 확인을 맡는다.
이 경계 덕분에 D1이 늦어도 **"판단" 쪽 + mock 엔진으로 90%를 먼저 짤 수 있다**(로그 29 §9).

### 3.3 마모 경로의 산출물

스윕 CSV와 **다른 계열**의 로그 3종이 새로 생긴다 (S-1 §9).

| 로그         | 주기                  | 핵심 열                                                                                                              |
| ------------ | --------------------- | -------------------------------------------------------------------------------------------------------------------- |
| A 사이클     | 매 사이클, 섹터별 1행 | `cycle, sector, t_erase_us, t_program_us, timestamp`                                                               |
| B 무결성     | 검사 주기마다         | `erase_residual_bits, program_fail_bits, defect_addrs, die_temp_c, uid_ok`                                         |
| C 체크포인트 | 스윕 1개당 1행        | `cycle, area, sweep_csv, chip_id(UID), base_sector, n_reads, pattern, repeat_idx, area_cumulative_cycles, git_rev` |

C의 `sweep_csv` 열이 **마모 경로와 측정 경로를 잇는 유일한 못**이다. 공통 필수는
`chip_id(UID)` · `git_rev` · `base_sector` · `timestamp` 넷.

### 3.4 시간

1사이클 405ms(typ) · 300k 사이클 = **33.7시간** · 체크포인트 1점 = 파일럿 약 3분 / 본 실험 약 15분 (S-1 §12, 2026-09-16 개정).
tSE는 칩 내부 고전압 펄스 시간이라 SPI 클럭으로 줄일 수 없고, 소켓이 1개라 전 과정 직렬이다.

### 3.5 이 루프에 들어가기 전의 잠금

**마모는 이 프로젝트에서 유일한 비가역 행위다.** G5 게이트 3조건(전수 신품 측정 · 노이즈 플로어
수치 확인 · 체크포인트 계획과 블라인드 정답 사전 커밋)이 모두 충족되기 전에는 어떤 칩도
마모하지 않는다. 파이프라인 문서에서 이 절을 빼면 **점선이 실선처럼 읽힌다.**

---

## 4. 축 추가 — 온도, 그리고 전압 **[미착수]**

온도는 루프의 4번째 단계가 아니다. **체크포인트를 곱하는 축**이다 — 같은 측정을 온도마다 반복한다.

```
   현재:   체크포인트 → 스윕 (상온)
   온도축: 체크포인트 → { 25°C · 40°C · 60°C } 각각에서 스윕
```

- 선행 조건은 소프트웨어가 아니라 **하드웨어**다: 히터 + 온도 센서 + PID 제어(PS), 그리고 짧은
  배선의 DUT 보드. 전압 축은 추가로 레벨 시프터가 전제다 — 없이 전압을 내리면 과전압 스트레스가
  실험 교란 변수가 된다(`project_context.md` §5).
- 소유는 장세은(DUT 보드, 온도 축 우선), 파이프라인에는 `die_temp_c` 열(S-1 §9 B·C)과
  XADC 판독이 자리만 잡혀 있다 — **리포에 XADC 사용 0건**.
- 이 축은 G5를 막지 않는 **병렬 트랙**이다. 마모 루프가 온도를 기다리지 않는다.

기대 산출물은 온도별 윈도우 축소 곡선과, 전압-클럭 평면의 슈무 플롯(온도별 여러 장)이다.

---

## 5. 산출물의 생애 — 3단 착지

측정 원본은 커밋하지 않는다. 재현성은 원본 데이터가 아니라 **생성 스크립트 + 파라미터 +
UID + git rev**로 확보한다.

| 단 | 위치              | 누가 쓰나         | 규칙                                                                                                                 |
| -- | ----------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------- |
| 1  | `build/data/`   | 기계 (캡처·래퍼) | 생성은`open(path, "x")` — 덮어쓰기 경로 자체를 두지 않는다                                                        |
| 2  | `data/`         | 사람이 옮긴다     | 원본 보관.`.gitignore` (스키마·README만 커밋)                                                                     |
| 3  | `docs/results/` | 사람이 승격한다   | `plots/` · `data/` · `captures/` (게이트별). **승격분은 동명 `.md`로 유래·재현 방법을 짝지어 둔다** |

추적성의 못은 셋이다. ① 파일명에 박힌 `<uid16>` ② CSV의 `uid`·`git_rev` 열 ③ 등록부와 P/E 이력.
**라벨과 데이터가 어긋나면 UID가 진실이다.**

---

## 6. 스크립트 색인

| 스크립트                                                                                  | 무엇을                                                                    | 산출물                                         |
| ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | ---------------------------------------------- |
| `fpga/scripts/build_g0_loopback.tcl`                                                    | g0 프로젝트 재생성 → 합성·구현·비트·XSA → ELF 체인 호출              | `build/vivado/`, `build/vitis/`            |
| `fpga/scripts/build_g2_jedec.tcl`                                                       | PS SPI0을 EMIO로 JB에 라우팅 (PL 로직 없음)                               | `build/vivado_g2/`                           |
| `fpga/scripts/build_g3_chip.tcl`                                                        | 실칩 스윕 계측기 (클럭별).`-tclargs bit <mhz> <k>`는 PAY_LEAD 보험 비트 | `build/vivado_g3_<mhz>/`                     |
| `ps/scripts/build_g0_sweep.py` · `build_g3_sweep.py`                                 | 스윕 앱 ELF. g3는 상수 3개 치환 사본                                      | `build/vitis*/…/g*_sweep.elf`               |
| `ps/scripts/build_flash_prep.py` · `build_flash_jedec.py` · `build_core_smoke.py` | prep · JEDEC 확인 · AXI 스모크 앱                                       | `build/vitis_prep/` 등                       |
| `ps/scripts/program_g0.tcl` · `program_g2.tcl` · `program_g3.tcl`                 | xsct JTAG 프로그래밍 (bit + ELF + ps7_init)                               | 보드                                           |
| `host/run/run_sweep_chip.py`                                                            | **실칩 정식 경로.** 세션1(prep·UID) → 세션2(스윕 ×N)             | CSV 2개 ×N + 세션 로그                        |
| `host/capture/sweep_uart_capture.py`                                                    | UART 행 스트림 → 계약 §6 CSV 2개. 무효 런 판정·`_invalid` 접미       | `build/data/sweep_*.csv`                     |
| `host/capture/chip_registry.py`                                                         | 등록부 파서. UID→라벨 역조회, 제한된 쓰기                                | `docs/chip_registry.md`                      |
| `host/run/chip_pe.py`                                                                   | P/E 증분 append-only                                                      | `docs/chip_pe.md`                            |
| `host/analysis/bathtub_analysis.py`                                                     | 폭 3종 + 체크리스트 5종 + 그림                                            | `build/plots/`                               |
| `host/analysis/repeatability_aggregate.py`                                              | 반복 런 집계 (평균±σ)                                                   | `build/plots/bathtub_<target>_repeat<n>.png` |
| `host/analysis/monte_carlo_sweep_params.py`                                             | N·θ 사전 등록 golden model                                              | `docs/results/plots/monte_carlo_*.png`       |
| `sim/smoke/*.v` + `iverilog`                                                          | 블록 스모크 4종                                                           | PASS/FAIL                                      |
| `sim/check_coverage.py`                                                                 | G1 회귀 커버리지 대조 (항목 누락만)                                       | 비영 종료 = FAIL                               |
| `ps/src/flash_wear` · `host/run/run_wear.py`                                         | **미구현** — 마모 벤치                                             | S-1 §9 로그 A/B/C                             |
| `ps/src/flash_io.*` · `ps/src/flash_id.c`                                            | 신원 확인 (JEDEC+UID, 쓰기 없음) — `--mode sweep` 세션1              | `#G2 UID <16hex>` → 등록부 대조               |
| `host/run/run_newchip.py`                                                              | **미구현** — 다칩 배치(재장착마다 UID 재확인, `flash_id` 재사용)   | —                                             |

---

## 7. 파이프라인이 자주 새는 자리

런북 3 표 E가 원전이고, 그중 **파이프라인 층에서 나는 것**만 옮긴다.

| 증상                                          | 원인                                   | 처치                                                    |
| --------------------------------------------- | -------------------------------------- | ------------------------------------------------------- |
| BEGIN 줄이 없다                               | 송신(xsct)을 수신(캡처)보다 먼저 켰다  | **수신 먼저.** 래퍼는 포트를 프로그래밍 전에 연다 |
| 포트가 안 열린다                              | miniterm과 캡처가 같은`/dev/ttyUSB1` | 동시 사용 불가                                          |
| `phase_pos_mismatch` 거부                   | ELF만 재로드했다 (MMCM 위상이 남는다)  | `program_*.tcl` 전체 경로로 재실행 — 의도된 방어     |
| 전 위상 BER≈0.51, e_i가 PRBS 0비트 수와 일치 | 사전 쓰기 없이 스윕                    | `flash_prep` PASS 먼저                                |
| 전 위상 BER≈0.5 +`valid=1`                 | PAY_LEAD 어긋남 (칩 문제가 아니다)     | `--pl 4` 보험 비트                                    |
| `요청 N=112 인데 ELF 는 n=100`              | `--n-reads`와 빌드가 따로 논다       | 빌드와 인자가 함께 가야 한다 (아래)                     |

**현재 알려진 세대 불일치**: g3 25·45MHz ELF는 N=112 반영 완료, **75MHz는 아직 100**이다.
그리고 `run_sweep_chip.py --n-reads` 기본값도 아직 100이라, 실칩 25MHz를 돌릴 때 인자를 빠뜨리면
1회차 캡처 후 중단된다 (로그 30 미결 3·4).

---

## 8. 실선/점선 요약 (2026-09-15)

| 단계                                   | 상태                                                        |
| -------------------------------------- | ----------------------------------------------------------- |
| 빌드 파이프라인 (g0·g2·prep·g3 ×3) | **동작** — 2025.2에서 전 빌드 검증 (2026-09-14)      |
| 검증 루프 (스모크 4 + 셀프테스트 3)    | **동작** / G1 cocotb는 미착수                         |
| 측정 경로 (스윕 → CSV → 폭)          | **동작** — G0·G2·G3·G4 통과                       |
| 신품 측정 (M 트랙)                     | **부분** — G-b·G-d 코드 완료(미커밋), G-a 판정 보류 |
| 마모 루프 (P/E)                        | **미구현** — 엔진 층위 미확정(D1), G5 잠금           |
| 온도·전압 축                          | **미착수** — 하드웨어 선행                           |

---

## 9. 미결 의사결정

| # | 항목                                                                   | 상태                                                            |
| - | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| 1 | 마모 엔진 층위 (PS C vs PL RTL)                                        | 로그 29 D1 잠정, 근거 재검토 중                                 |
| 2 | `flash_prep` G-b·G-d 구현 주체                                      | 세은 B 트랙 배정이나 온도 트랙 이동 중 — 워크플로 9 §2-3 미결 |
| 3 | 신품 조사 2단 CSV(호스트 파서)를 언제 만드나                           | 로그 30 미결 1 —`run_newchip.py`와 겹친다                    |
| 4 | `--n-reads` 기본값과 75MHz ELF 세대 정리                             | 로그 30 미결 3·4                                               |
| 5 | 수정안#1(BASE_SECTOR) 승인 — 승인 전까지 `--base-sector`는 0만 허용 | 워크플로 9 §5                                                  |
