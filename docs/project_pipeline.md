# 프로젝트 파이프라인

- **작성일**: 2026-09-15 · **개정**: 2026-09-22 (축 중심으로 재구성 — 각 축이 무슨 일을 하고 무엇을 내는가)
- **이 문서는** 축마다 **무슨 일이 일어나고 무엇이 남으며 어디까지 됐나**를 적는다. 축마다
  「무엇을 하는가 · 사람이 하는 일 · 나오는 것 · 지금 막힌 것」 네 칸을 같은 순서로 쓴다.
  **명령은 여기 없다** → `docs/commands.md` · 왜 이 실험인가는 → `docs/project_context.md`
- 실험 서사(왜 재는가)는 `docs/project_context.md`, 게이트 정의는
  `docs/workflow/4.gate_map.md`가 원전이고 **본 문서는 그 사이의 흐름을 그린다.**
- 소스

  | 층 | 원전 |
  | --- | --- |
  | **사람이 치는 명령** (전부) | `docs/commands.md` — 본 문서는 명령을 싣지 않고 그 절 번호를 가리킨다 |
  | 빌드 원명령·기대 출력·검증 수치 | `docs/build_reproduction.md` |
  | 측정 당일 절차·고장 판독표 | `docs/workflow/3.realchip_day_runbook.md` · `7.realchip_uid_verification_day.md` |
  | 마모 당일 절차·판정 읽는 법 | `docs/workflow/12.pe_engine_acceptance_runbook.md` |
  | 게이트 정의·이름 규칙 | `docs/workflow/4.gate_map.md` |
  | CSV 스키마·무효 런 정의 | `docs/interface/contract.md` §6 |
  | 신품 전수 측정 절차 | `docs/spec/s2.newchip_protocol.md` |
  | 마모 벤치 절차·인수 기준 | `docs/spec/s1.wear_bench_spec.md` |

  본 문서는 이들을 **연결만** 한다. 합격 기준·문턱값·시료 배분표를 여기에 복제하지 않는다
  (복제하면 원전과 어긋나는 문서가 하나 더 생긴다).
- **표기**: 축 머리에 **[동작]** / **[부분]** / **[미착수]** 를 붙인다. 읽는 사람이 무엇을
  지금 돌릴 수 있고 무엇이 아직 없는지를 절 제목만 보고 알게 하기 위한 장치다.
- **용어** (로그 29 §7): 읽기 마진 측정 = **스윕**, 그 그림 = **욕조 곡선**, P/E 마모 = **마모 벤치**.
  문장에서는 **측정 경로(스윕, PL) / 마모 경로(P/E, PS SPI)** 로 가른다.

---

## 0. 한 장 지도

```
  [소스]                       [빌드]                    [보드에서]                 [남는 것]

  fpga/rtl/ · constraints/ ┐
  fpga/scripts/*.tcl       ┼ vivado ► build/vivado*/ *.bit + *.xsa
  ps/src/*.c               ┴ vitis  ► build/vitis*/  *.elf
                                          │  xsct program_{g0,g2,g3}.tcl 가 올린다
          ┌───────────────────────────────┴───────────────────────────────┐
          │                                                               │
   [측정 경로]  PL · g3_chip_<mhz> 비트                    [마모 경로]  PS SPI · g2_jedec 비트
   g3_sweep.elf   위상 ×2,520 × 읽기 112                    flash_prep.elf  소거 + PRBS 기록
      UART  #G0 SWEEP BEGIN … END                           flash_wear.elf  0x00 프로그램 + 소거 반복
          │                                                     UART  #WEAR H/A/B/R/D 행
          │                                                               │
   host/run/run_sweep_chip.py                              host/run/run_wear.py
     └ sweep_uart_capture.py (CSV 2개)                       └ wear_link.py (행 수신·체크섬)
     └ chip_registry.py      (UID → 라벨)                    └ chip_pe.py   (P/E 증분 기입)
     └ chip_pe.py            (prep = P/E +1)                 └ run_sweep_chip.py 를 체크포인트마다 부른다
          │                                                               │
   build/data/sweep_*.csv · _reads.csv              build/logs/wear/<세션>/
   build/plots/bathtub_*.png                          plan.txt · verdict.txt · A/B/R/H.txt
          │                                            checkpoints.csv (C 행 + 소거 시간 요약)
          └──────────────────────┬────────────────────────────────┘
                                 │
        data/ (원본 보관)   docs/results/ (승격)   docs/chip_registry.md · chip_pe.md (기입)
```

**두 경로는 비트스트림이 다르다.** 측정은 PL 로직(g3)이 하고 마모는 PS 의 SPI(g2)가 한다. 한 보드에
동시에 올릴 수 없으므로, 체크포인트마다 ELF·비트를 갈아 끼운다 — 그 교체를 사람 대신 `run_wear.py`
가 한다(축 3).

---

## 1. 축 1 — 계측기를 만든다 (빌드·검증) **[동작]**

### 무엇을 하는가

측정도 마모도 **소스에서 만든 비트와 ELF** 로만 돈다. 이 축은 보드를 건드리지 않고 그 전부를
다시 만들고, 만든 것이 맞는지 보드 없이 채점한다. 새 PC 에서 처음 시작할 때와 소스를 고쳤을 때
거치는 자리다.

### 사람이 하는 일

`python reproduce.py` 한 줄 (명령·옵션은 `commands.md` §1). 약 10분, 보드 불필요. 기본 11단계는
`sim · selftest · tb · g0 · g2 · prep · id · wear · g3-25 · g3-45 · g3-75`.

각 단계는 6겹으로 채점된다 — 종료 코드 · 완료 문구 · 산출물 존재와 갱신 · 타이밍 · 수치 기준표 ·
빌드 파라미터. `WARN` 은 실패가 아니라 기준표와 다른 것이고 **로그에 적을 거리**다.

**보드 측정 직전에는 돌리지 않는다** — 단계가 중간에 실패하면 그 ELF 는 깨진 채 남는다.

### 나오는 것

| 산출물 | 무엇 | 누가 쓰나 |
| --- | --- | --- |
| `build/vivado/` · `vivado_g2/` · `vivado_g3_<mhz>/` | g0 루프백 · g2(PS SPI 를 EMIO 로) · g3 스윕 계측기 비트 + XSA | xsct 가 보드에 올린다 |
| `build/vitis*/…/*.elf` | `g0_sweep` · `g3_sweep` · `flash_prep` · `flash_id` · `flash_wear` | 같음 |
| `build/vitis_prep_<base>_<n>/` | 범위 전용 prep (0\_7 · 7\_7 · 2041\_7) — 체크포인트가 쓴다 | 축 3 |
| `build/sim/flash_wear_sim` | 마모 엔진의 호스트 시뮬레이션 (보드 없이 같은 명령) | 블랙박스 TB · 조원 연습 |
| `build/logs/reproduce_<UTC>/summary.txt` | 단계별 채점 결과 | 사람 |

**한 소스가 두 앱이 되는 자리** — `ps/src/g0_sweep.c` 하나에서 g0(루프백)과 g3(실칩)이 나온다.
`build_g3_sweep.py` 가 상수 셋(`SWEEP_STEPS` · `F_SCLK_HZ` · `N_READS_CFG=112`)만 치환한 사본을
빌드한다. **N 은 옵션이 아니라 ELF 에 박힌다** — 신품과 파일럿의 비교가 같은 N 위에서만 성립하기
때문이다(수정안 #2). 래퍼는 `BEGIN` 의 `n=` 이 112 가 아니면 첫 줄에서 중단한다.

**보드 없이 도는 검증 루프** — iverilog 블록 스모크 4종 · 호스트 셀프테스트 3종 ·
블랙박스 TB 127개(`host/tests/`, mock 엔진 + 호스트 시뮬 + 실행기). RTL·호스트 코드를 만지면
여기를 먼저 통과시킨다.

### 지금 막힌 것

- **G1 cocotb 회귀 미착수** — `sim/tb/` 가 비어 있다. 블록 스모크 4종은 돈다 (지민 담당)

---

## 2. 축 2 — 신품을 잰다 **[측정 종료 · 게이트 판정 보류]**

### 무엇을 하는가

**마모를 한 번이라도 시작하면 영원히 못 얻는 값**을 전부 걷는다 — UID 등록, 출고 blank 상태,
신품 윈도우 폭, 재장착 σ. 파이프라인에서 유일하게 "지금 안 하면 끝"인 자리다(S-2 머리말).
곡선의 x=0 점이 여기서 나온다.

### 사람이 하는 일

`run_sweep_chip.py --mode newchip --mhz 25` (신품 첫 투입, P/E +1) 또는 `--mode sweep` (재측정,
P/E 불변). 명령·옵션은 `commands.md` §2, 당일 절차는 런북 3·7.

```
  등록부 파싱 (깨져 있으면 보드를 건드리기 전에 죽는다)
  포트 개방 ──────────────────── 캡처가 먼저다. 첫 줄을 놓치면 런이 무효
  세션1  xsct program_g2.tcl + flash_prep.elf   (sweep 모드는 flash_id.elf — 쓰기 없음)
           #PREP JEDEC EF 40 17 → #PREP UID <16hex> → (BLANK/ERASE) → #PREP PASS
           UID 로 docs/chip_registry.md 역조회 → 라벨 확정 → docs/chip_pe.md 에 +1 행
  세션2  xsct program_g3.tcl <mhz>   ×N회 (--repeat, --reseat)
           #G0 SWEEP BEGIN … END valid=1 reason=complete
  분석   bathtub_analysis.py 자동 호출 → 폭 3종(θ) + 그림
```

**사람이 라벨을 입력하지 않는다.** UID 를 읽는 것은 세션 1(PS SPI)이고 CSV 를 만드는 것은
세션 2(PL)라, 사람이 중간에 끼면 UID 가 파일에 닿지 못한다. 래퍼의 존재 이유가 이것이다.

**모드가 정한 것은 옵션으로 뒤집을 수 없다.** `sweep` 에 prep 을 켜는 스위치가 없고 `newchip` 에
`--chip` 을 줄 수 없다. 앵커 재측정에서 옵션을 빠뜨려 칩을 한 번 더 마모시키던 사고를
**표현 불가능**하게 만든 것이다.

### 나오는 것

| 산출물 | 무엇 |
| --- | --- |
| `build/data/sweep_<label>_<uid16>_<stamp>.csv` · `_reads.csv` | 위상별 오류 수 · 읽기별 상세 (계약 §6). 완주 못 하면 `_invalid` 접미 |
| `build/data/session_<label>_<uid16>_<batch>.log` | 그날의 원문 전부. 칩 신원이 어긋나면 `session_idfail_*` 로 개명 |
| `build/plots/bathtub_*.png` + 폭 3종 | θ=10⁻²/10⁻³/10⁻⁴ 에서의 윈도우 폭 |
| `docs/chip_registry.md` | UID ↔ 라벨. 기계가 쓴다 |
| `docs/chip_pe.md` | prep 1회 = 그 범위 P/E +1 |

### 지금 막힌 것

| 게이트 | 조건 | 현재 |
| --- | --- | --- |
| W10-M 전수 측정 | chip04\~10 + 앵커 | **2026-09-20 종료** |
| G-a | 드리프트 판정 (chip01 재측정) | **보류** — 재장착 σ 확보 후 판정 (워크플로 7) |
| G5 ② | 예상 노화 이동량 Δ (분자) | **없음** — 분모 σ_repeat 13.86ps 는 확보, 비교 대상이 문서에 없다 |
| G5 ③ | 블라인드 절차 | **미설계** (로그 23 부록 D) |

**G5 ②③ 이 축 3 의 착수 조건이다.** 마모 전에 문서에 수치가 있어야 한다 — 데이터를 본 뒤 정하면
S-2 §6 이 금지한 사후 해석이 된다.

---

## 3. 축 3 — 마모시킨다 **[동작 — 대조군 스윕만 막혀 있다]**

### 무엇을 하는가

프로젝트의 본체다. 축 2 가 x=0 점 하나를 찍는 것이라면, 이 축은 **같은 칩의 7섹터를 300k 사이클까지
태우며 x축을 만든다.** 체크포인트마다 그 자리를 다시 재서 곡선의 점을 찍는다.

```
  초기화 1회 (S-1 §4·§8.1)  UID 대조 → tally 두 벌 소거 → 마모군·대조군 PRBS 기록 → blank check

  반복 {
      마모 루프 (S-1 §6)   ① 0x00 프로그램 112페이지      → t_program_us
                           ② 7섹터 소거                   → 섹터별 t_erase_us
                           ③ 카운터 +1
                           ④ 100사이클마다 blank check · tally 1바이트 · UID 재확인
      체크포인트 도달       마모군 소거 → PRBS 기록(P/E +1) → 스윕 → 분석·plot
  }  종점 300,000 (12점: 100 · 300 · 600 · 1,400 · 3,000 · 6,400 · 13,800 · 29,600 · 63,700 ·
                          137,000 · 294,500 · 300,000)
```

**얻는 것이 둘이다** — 체크포인트의 스윕이 주는 **윈도우 폭**(y1)과, 매 사이클 A 행이 주는
**동작 시간**(y2: 소거 `t_erase_us` · 쓰기 `t_program_us`). 칩이 낡을수록 지우고 쓰는 데 오래
걸리는 성질을 재서 **동작 시간 자체를 칩의 나이를 읽는 센서로 쓴다**(`project_context.md`).
둘 다 칩 내부 WIP 해제까지의 실측이라 SPI 클럭과 무관하다. 사전 등록된 **1차 지표는 소거 시간**
이고(G5 이중 지표 · A6 판정선 400ms), 쓰기 시간은 같은 행·같은 해상도로 남는 **보조 지표**다 —
변화 폭이 작고 단조롭지 않을 수 있어 1차로 걸지 않았다. 쓰기 쪽의 더 강한 신호는 시간이 아니라
B 행의 `program_fail_bits`(전하가 안 들어간 비트)다.

영역 배치는 S-1 §2.1 — 마모군 0\~6 · 근접 대조군 7\~13 · 원격 대조군 2,041\~2,047 · tally 512·1,536.
**대조군은 마모 루프를 받지 않고** 체크포인트마다 한 번씩만 다시 기록된다(읽기 교란을 마모군과
대칭으로 맞추려는 것, `[D17-13]`). 300k 끝에서 마모군 300,012 : 대조군 12 다.

### 사람이 하는 일

`run_wear.py accept --chip chip01` 한 줄 (`commands.md` §3, 판정 읽는 법은 런북 12).

1. 실행기가 보드를 올리고 UID 를 대조한 뒤 **계획 한 장**을 띄운다 — 태울 자리, 보호 섹터,
   칩의 tally 와 장부 누적, 체크포인트 12점, 예상 시간(실측 단가 기준). 사람은 읽고 `enter`
2. 고칠 것이 있으면 그 자리에서 옵션을 쳐 넣는다(`--to 100000 --confirm-first 3`) — 계획을 다시 띄운다
3. **앞 K 체크포인트에서만** 판정 9줄·장부 행·plot 을 확인하고 `enter`. K 번 치고 나면 무인으로 종점까지
4. 전원이 나가면 `resume` 이 tally 두 벌과 호스트 A 로그로 채택값을 계산한다 — **START 는 사람이**

**사람이 치는 것은 칩과 명령뿐이다.** 체크포인트 배치·구간 나누기·측정 편성은 전부 기본값이고,
비가역 행위 앞에는 계획 승인 화면이 선다.

### 나오는 것

| 산출물 | 주기 | 무엇 |
| --- | --- | --- |
| `A.txt` (A 행) | 매 사이클 × 7섹터 | `cycle · sector · t_erase_us · t_program_us · ts` — **곡선 y2 의 원자료**, 300k 면 210만 행 |
| `B.txt` (B 행) | 검사 주기(100, 결함 뒤 10) | 두 읽기의 결함 비트와 주소 · `uid_ok` |
| `R.txt` (R 행) | 사건마다 | `wip_timeout` · `program_fail` · `erase_fail` · `uid_mismatch` · `halt` · `reerase` |
| `H.txt` (H 행) | START 마다 | `chip_id` · **`git_rev`** · `session` · `cycle` · `delta` |
| `plan.txt` | 실행마다 | 사람이 승인한 계획 그대로 |
| `verdict.txt` | 구간마다 | A1\~A7 · C · probe 9줄 |
| `checkpoints.csv` (C 행) | 체크포인트마다 | `cycle · area · sweep_csv · chip_id · base_sector · n_reads · mhz · session` + 동작 시간 요약(`t_erase_p50/p99/max` · `t_program_p50/p99/max` · `cycle_s_p50`) · 점당 소요 |
| `docs/chip_pe.md` | 구간·체크포인트마다 | P/E 증분 행 (append-only) |
| 체크포인트의 스윕 CSV·png | 체크포인트마다 | 축 2 와 같은 경로·같은 형식 — **곡선 y1** |

**C 행의 `sweep_csv` 열이 마모 경로와 측정 경로를 잇는 유일한 못이다.** 공통 필수는
`chip_id`(UID) · `git_rev` · `base_sector` · `timestamp` 넷.

### 지금 막힌 것

- **근접·원격 대조군 스윕 불가** — 읽기 창이 RTL 에 페이지 0\~111 로 고정이라 섹터 7\~13 도
  2,041 도 못 읽는다(수정안 #1 `BASE_SECTOR` 미구현, 로그 44 `[U44-8]`, 지민 담당).
  **파일럿은 마모군 곡선만 나오고 S-1 §15 ③(인접 간섭)은 답이 안 나온다**
- **체크포인트 측정 경로는 실칩 미검증** — prep ELF → 스윕 → 엔진 복귀를 sim 으로는 못 잰다.
  기본 `--confirm-first 1` 이 첫 체크포인트(100)에서 사람을 세우는 이유가 이것이다
- **G5 3조건** — ① 전수 신품 측정(종료) ② 분자 Δ(없음) ③ 블라인드 절차(미설계).
  **셋이 차기 전에는 어떤 칩도 마모하지 않는다.** 이 절에서 이 문장을 빼면 점선이 실선처럼 읽힌다

---

## 4. 축 4 — 환경을 바꾼다 (온도, 그리고 전압) **[센서 브링업 착수]**

### 무엇을 하는가

온도는 루프의 4번째 단계가 아니라 **체크포인트를 곱하는 축**이다 — 같은 측정을 온도마다 반복한다.

```
   현재:   체크포인트 → 스윕 (상온)
   온도축: 체크포인트 → { 25°C · 40°C · 60°C } 각각에서 스윕
```

### 사람이 하는 일

아직 파이프라인에 명령이 없다. 지금은 **하드웨어 브링업** 단계다 — TMP117 온도 센서를
아두이노로 읽는 시험이 `hw/arduino/tmp117_test/` 에 들어왔다(2026-09-22).

### 나오는 것

기대 산출물은 온도별 윈도우 축소 곡선과, 전압-클럭 평면의 슈무 플롯(온도별 여러 장)이다.
파이프라인에는 자리만 잡혀 있다 — `die_temp_c` 열(S-1 §9 B·C)과 XADC 판독.

### 지금 막힌 것

- 선행 조건이 소프트웨어가 아니라 **하드웨어**다: 히터 + 온도 센서 + PID 제어(PS), 짧은 배선의
  DUT 보드. 전압 축은 추가로 레벨 시프터가 전제다 — 없이 전압을 내리면 과전압 스트레스가
  실험 교란 변수가 된다(`project_context.md` §5)
- 소유는 장세은(`hw/`, 온도 축 우선). **리포에 XADC 사용 0건**
- 이 축은 G5 를 막지 않는 **병렬 트랙**이다. 마모 루프가 온도를 기다리지 않는다

---

## 5. 축을 잇는 것 — 산출물의 생애와 추적성

측정 원본은 커밋하지 않는다. 재현성은 원본 데이터가 아니라 **생성 스크립트 + 파라미터 + UID +
git rev** 로 확보한다.

| 단 | 위치 | 누가 쓰나 | 규칙 |
| -- | --- | --- | --- |
| 1 | `build/data/` · `build/logs/` | 기계 (캡처·래퍼·실행기) | 생성은 `open(path, "x")` — 덮어쓰기 경로 자체를 두지 않는다 |
| 2 | `data/` | 사람이 옮긴다 | 원본 보관. `.gitignore` (스키마·README만 커밋) |
| 3 | `docs/results/` | 사람이 승격한다 | `plots/` · `data/` · `captures/` (게이트별). **승격분은 동명 `.md` 로 유래·재현 방법을 짝지어 둔다** |

추적성의 못은 넷이다. ① 파일명에 박힌 `<uid16>` ② CSV·로그 행의 `uid`·`git_rev` 열
③ 등록부(`chip_registry.md`)와 P/E 이력(`chip_pe.md`) ④ C 행의 `sweep_csv`.
**라벨과 데이터가 어긋나면 UID 가 진실이다.**

**누적 P/E 의 정본은 칩 자신의 tally 섹터다**(S-1 §8). `chip_pe.md` 는 호스트 측 이력이고 둘이
어긋나면 칩이 진실이다 — 다만 tally 는 100사이클 눈금이라 그 아래는 호스트 A 로그가 메운다.
실행기는 START 전에 셋(tally 두 벌 · 장부 합계 · 영역)을 맞대보고 어긋나면 멈춘다.

---

## 6. 스크립트 색인

| 스크립트 | 무엇을 | 산출물 |
| --- | --- | --- |
| `reproduce.py` | 빌드·검증 전체 (보드 없이) | `build/*` + `build/logs/reproduce_<UTC>/` |
| `fpga/scripts/build_g0_loopback.tcl` | g0 프로젝트 재생성 → 비트·XSA → ELF 체인 | `build/vivado/`, `build/vitis/` |
| `fpga/scripts/build_g2_jedec.tcl` | PS SPI0 을 EMIO 로 JB 에 라우팅 (PL 로직 없음) | `build/vivado_g2/` |
| `fpga/scripts/build_g3_chip.tcl` | 실칩 스윕 계측기 (클럭별). `-tclargs bit <mhz> <k>` 는 PAY_LEAD 보험 비트 | `build/vivado_g3_<mhz>/` |
| `ps/scripts/build_g3_sweep.py` · `build_g0_sweep.py` | 스윕 앱 ELF. g3 는 상수 3개 치환 사본 (N=112) | `build/vitis*/…/g*_sweep.elf` |
| `ps/scripts/build_flash_prep.py` | prep 앱. 인자로 범위 지정 사본 (`vitis_prep_<base>_<n>`) | `build/vitis_prep*/` |
| `ps/scripts/build_flash_wear.py` · `build_flash_id.py` | 마모 엔진 · 신원 확인 앱 | `build/vitis_wear/`, `build/vitis_id/` |
| `ps/scripts/program_g0.tcl` · `program_g2.tcl` · `program_g3.tcl` | xsct JTAG 프로그래밍 (bit + ELF + ps7_init) | 보드 |
| `host/run/run_sweep_chip.py` | **측정의 정본.** 세션1(prep·UID) → 세션2(스윕 ×N) → 분석 | CSV 2개 ×N + 세션 로그 + png |
| `host/run/run_wear.py` | **마모의 정본.** 계획 승인 → 구간 → 체크포인트 측정 → 판정 | `build/logs/wear/<세션>/` + `chip_pe.md` 행 |
| `host/run/wear_link.py` | UART 어댑터 — 경계 10개, 행 체크섬·재전송 | — |
| `host/capture/sweep_uart_capture.py` | UART 행 스트림 → 계약 §6 CSV 2개. 무효 런 판정 | `build/data/sweep_*.csv` |
| `host/capture/chip_registry.py` | 등록부 파서. UID→라벨 역조회, 제한된 쓰기 | `docs/chip_registry.md` |
| `host/run/chip_pe.py` | P/E 증분 append-only | `docs/chip_pe.md` |
| `host/analysis/bathtub_analysis.py` | 폭 3종 + 체크리스트 5종 + 그림 | `build/plots/` |
| `host/analysis/repeatability_aggregate.py` | 반복 런 집계 (평균±σ) | `build/plots/bathtub_<target>_repeat<n>.png` |
| `host/analysis/monte_carlo_sweep_params.py` | N·θ 사전 등록 golden model | `docs/results/plots/monte_carlo_*.png` |
| `ps/src/flash_wear.c` | 마모 엔진 (PS C, 무상태). tally 2벌·보호 범위는 엔진 상수 | `#WEAR` 행 |
| `ps/src/flash_prep.c` · `flash_io.*` · `flash_id.c` | 소거·PRBS 기록·verify · SPI 배관 · 신원 확인 | `#PREP` · `#G2` 행 |
| `host/tests/` | 블랙박스 TB 127 — mock 엔진 · 호스트 시뮬 · 실행기 | PASS/FAIL |
| `sim/smoke/*.v` + `iverilog` | 블록 스모크 4종 | PASS/FAIL |
| `sim/check_coverage.py` | G1 회귀 커버리지 대조 (항목 누락만) | 비영 종료 = FAIL |
| `host/run/run_newchip.py` | **미구현** — 다칩 배치 | — |

---

## 7. 파이프라인이 자주 새는 자리

런북 3 표 E 가 원전이고, 그중 **파이프라인 층에서 나는 것**만 옮긴다.

| 증상 | 원인 | 처치 |
| --- | --- | --- |
| BEGIN 줄이 없다 | 송신(xsct)을 수신(캡처)보다 먼저 켰다 | **수신 먼저.** 래퍼는 포트를 프로그래밍 전에 연다 |
| 포트가 안 열린다 | miniterm 과 캡처가 같은 `/dev/ttyUSB1` | 동시 사용 불가 |
| `phase_pos_mismatch` 거부 | ELF 만 재로드했다 (MMCM 위상이 남는다) | `program_*.tcl` 전체 경로로 재실행 — 의도된 방어 |
| 전 위상 BER≈0.51, e_i 가 PRBS 0비트 수와 일치 | 사전 쓰기 없이 스윕 | `flash_prep` PASS 먼저 |
| 전 위상 BER≈0.5 + `valid=1` | PAY_LEAD 어긋남 (칩 문제가 아니다) | 보험 비트 빌드 후 `--pl 4` |
| `BEGIN` 의 `n=` 이 112 가 아니다 | ELF 세대가 다르다 (N 은 빌드 시 고정) | `reproduce.py --only g3e-<mhz>` 로 다시 굽는다 |
| `E_CYCLE` · `E_DIRTY` 거부 | 호스트가 준 `cycle` 이 칩의 tally 와 안 맞는다 | `resume` 으로 채택값을 받거나, 새 실험이면 `tally-erase` |
| 「칩과 장부가 다른 이야기를 한다」 | `chip_pe.md` 와 tally 가 창을 벗어났다 | 실행기가 찍는 세 갈래 안내를 따른다 (장부 정정 · `--cycle` · `tally-erase`) |

---

## 8. 실선/점선 요약 (2026-09-22)

| 축 | 상태 |
| --- | --- |
| 축 1 빌드·검증 | **동작** — 2025.2 전 빌드 검증(2026-09-14) · 스모크 4 + 셀프테스트 3 + TB 127 / G1 cocotb 미착수 |
| 축 2 신품 측정 | **측정 종료**(2026-09-20 전수 10개) / G-a 판정 보류 · G5 ②③ 미충족 |
| 축 3 마모 | **동작** — 엔진·실행기 구현, 실칩 인수 통과(2026-09-22). 체크포인트 편성·자동 측정 구현 / 대조군 스윕 막힘(`[U44-8]`) · 실칩 체크포인트 미검증 |
| 축 4 온도·전압 | **센서 브링업** — TMP117 시험 코드. DUT 보드·히터·레벨 시프터 선행 |

---

## 9. 미결 의사결정

| # | 항목 | 상태 |
| - | --- | --- |
| 1 | **G5 ② 예상 노화 이동량 Δ** — 마모 착수 전에 수치가 문서에 있어야 한다 | 워크플로 10 §N — 후보 3안 제시, 미정 |
| 2 | **G5 ③ 블라인드 절차** | 미설계 (로그 23 부록 D) |
| 3 | 수정안 #1 `BASE_SECTOR` (읽기 창) — 없으면 대조군을 못 잰다 | 발의 2026-08-23, 구현 0건 (지민) |
| 4 | 본 실험 3칩의 그룹 수·마모량 배분·패턴 — 파일럿이 답한다 | S-1 §15 ①\~⑥ |
| 5 | 엔진 보호 범위(`CTRL_RANGES`)는 ELF 상수다 — 본 실험 배치로 가면 재빌드 | `[D44-2]` |
| 6 | 신품 조사 2단 CSV(호스트 파서)를 언제 만드나 | 로그 30 미결 1 — `run_newchip.py` 와 겹친다 |
