# 프로젝트 파이프라인

- **작성일**: 2026-09-15 · **개정**: 2026-09-22 (축 중심으로 재구성 — 각 축이 무슨 일을 하고 무엇을 내는가) ·
  **2026-10-05** (마모 축을 실제 결과로 — 파일럿 300k · 종단 100k · 교정 곡선 · 수명 역산 v3.2 · 블라인드 · 온도 65°C, 닫힌 게이트 정리) ·
  **2026-11-11** (공모전 끝 뒤 상태로 — 축 3 교정 9칩 · 200k 7칩 · v4.3 · 블라인드 3칩, 축 4 온도 6칩, 축 1 욕조 v2 진행, §8 · §9)
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
  | 수명 역산 모델 버전별 사양 | `docs/spec/s5.lifetime_inverse_model.md` |

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
   data/sweep_*.csv · _reads.csv                    data/wear/<세션>/
   build/plots/bathtub_*.png                          plan.txt · verdict.txt · A/B/R/H.txt
          │                                            checkpoints.csv (C 행 + 소거 시간 요약)
          └──────────────────────┬────────────────────────────────┘
                                 │
        data/ (원본 보관)   docs/results/ (승격)   docs/chip_registry.md · chip_pe.md (기입)

   [마모가 끝난 뒤 — 보드 없이]
   host/analysis/pe_end.py      세션 원본 → 체크포인트 CSV · 1k 구간 곡선 · 그림 → docs/results/ 승격
   host/analysis/wear_curves.py   A 행 → 교정 표 (1k 구간 × 섹터 분위수)
   host/analysis/wear_inverse.py  교정 표 + 개봉 prep 로그 → 누적 P/E 추정 구간 · 판정 (수명 역산, 축 3 끝)
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

`python reproduce.py` 한 줄 (명령·옵션은 `commands.md` §1). 약 10분, 보드 불필요. 기본 12단계는
`sim · selftest · tb · g0 · g2 · prep · prep-wear · id · wear · g3-25 · g3-45 · g3-75`.

각 단계는 6겹으로 채점된다 — 종료 코드 · 완료 문구 · 산출물 존재와 갱신 · 타이밍 · 수치 기준표 ·
빌드 파라미터. `WARN` 은 실패가 아니라 기준표와 다른 것이고 **로그에 적을 거리**다.

**보드 측정 직전에는 돌리지 않는다** — 단계가 중간에 실패하면 그 ELF 는 깨진 채 남는다.

**`flash_prep.c` 를 고쳤으면 `prep-wear` 도 다시 굽는다.** 체크포인트가 올리는 것은 기본 prep 이 아니라 범위 전용 사본
(`build/vitis_prep_0_7`)이라, 이 단계를 빼먹으면 체크포인트만 옛 펌웨어로 돈다 — chip15 · chip18 종단의 체크포인트 로그에
프로그램 시간 줄이 없는 것이 그 탓이다(2026-10-05 재빌드, `build_reproduction.md` §3.3).

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
호스트 시험 178개(`host/tests/` — 블랙박스 TB(mock 엔진 + 호스트 시뮬 + 실행기)와 분석 스크립트 시험). RTL·호스트 코드를 만지면
여기를 먼저 통과시킨다.

### 지금 막힌 것

- **G1 cocotb 회귀는 진행 중** — `sim/tb/` 에 항목별 시험(C1-C6 · F1 …)이 들어와 있고 현황: 회귀 21항목 PASS(9/23, 작성자 실행) · ① 판정 3블록 미판정 · F11 · F12 제외 · 게이트 미개방 (지민 담당,
  워크플로 6). 블록 스모크 4종은 돈다
- **욕조 v2 — 설계 끝, 구현 전 (2026-11-11)** — 측정 경로에 두 번째 스윕 방식을 더한다: 펌웨어 2단계 스윕(훑기 1회 → 벽 집중, 25MHz ·
  K = 5 · 표준 N 8,064 · 초심부 N 2,064,384)과 `flash_rx.v` 의 에지 계수기(정렬 3 × 정답 0/1). 명세 `docs/spec/s6.bathtub_v2.md` ·
  계약 수정안 #4 가 초안이고 승인 전이다. 같은 두 RTL 파일을 고치는 수정안 #1(BASE_SECTOR)을 함께 구현해 비트스트림 회귀를 한 번에 끝낸다.
  구현 · 판정 한영웅, 검토 · 승인 박지민 · 장세은 (로그 55 [D55-4] · [D55-5] · [D55-11] · [D55-13] - [D55-15]). 마모 체크포인트 스윕은 v1 그대로다([D55-10])

---

## 2. 축 2 — 신품을 잰다 **[31칩 측정 종료 (2026-10-25)]**

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
| `data/sweep_<label>_<uid16>_<stamp>.csv` · `_reads.csv` | 위상별 오류 수 · 읽기별 상세 (계약 §6). 완주 못 하면 `_invalid` 접미 |
| `data/session_<label>_<uid16>_<batch>.log` | 그날의 원문 전부. 칩 신원이 어긋나면 `session_idfail_*` 로 개명 |
| `build/plots/bathtub_*.png` + 폭 3종 | θ=10⁻²/10⁻³/10⁻⁴ 에서의 윈도우 폭 |
| `docs/chip_registry.md` | UID ↔ 라벨. 기계가 쓴다 |
| `docs/chip_pe.md` | prep 1회 = 그 범위 P/E +1 |

### 지금 막힌 것

| 항목 | 현재 |
| --- | --- |
| 전수 측정 | **31칩 종료 (2026-10-25)** — FV 19(원 배치 8 · 추가 구매 5 · 3차 6, chip12 포함) · JV 12(원 배치 chip10 · 추가 구매 chip14 · 디바이스마트 chip30-39). 측정 불가 chip05 · 11 · 13 |
| G-a 드리프트 판정 | **불통과 확정이나 원인은 측정계가 아니었다** — 앵커 chip02 조립체의 고장(−300ps 이탈)을 대조 칩 3점으로 갈랐다 (`docs/results/newchip_survey.md`) |
| 재장착 σ | **13.86ps** (chip10 재장착 3회) — 판정 기준 3σ = 42ps |
| 신품 소거 시간 | **두 무리**로 갈린다 — 경계 40ms, 31칩 빠른 19 · 느린 12. FV 빠른 24.9-33.7 · 느린 47.0-51.1ms, JV 빠른 24.5-36.3 · 느린 52.7-53.4ms. 이 값이 수명 역산의 무리 분류자다(축 3) |
| 새로 산 칩 | **신품 전수 끝 (3차 FV 10/15 - 10/25 · JV 10/25).** 배정은 등록부 — chip30-39 는 미배정 |

UID 앞바이트가 `DF` 인 JV 7칩은 폭이 38,704-38,918ps 로 나머지 24칩(39,327-39,821ps)과 띠가 갈린다 (`docs/results/newchip_survey.md` 10/25 추기).
그중 chip10 · 14 를 상온 0 → 100k 마모로 돌렸고, 계단 없이 100k 2.55 · 2.65배로 늙어 교정 밖 「JV 둘」 로 따로 승격했다 (축 3).

---

## 3. 축 3 — 마모시킨다 **[동작 — 마모 19칩 · 교정 9칩(100k 너머 7장) · 수명 역산 v4.3 · 블라인드 3칩]**

### 무엇을 하는가

프로젝트의 본체다. 축 2 가 x=0 점 하나를 찍는 것이라면, 이 축은 **같은 칩의 7섹터를 태우며 x축을 만든다** —
파일럿(chip01)은 300k 사이클, 그 뒤의 종단 칩은 정격 내구인 100k 까지다. 역산의 답 범위 너머 곡선을 얻으려고 교정 칩 6개와 chip21 을
200k 까지 이었다(로그 52 [D52-10]). 체크포인트마다 그 자리를 다시 재서 곡선의 점을 찍는다.

```
  초기화 1회 (S-1 §4·§8.1)  UID 대조 → tally 두 벌 소거 → 마모군·대조군 PRBS 기록 → blank check

  반복 {
      마모 루프 (S-1 §6)   ① 0x00 프로그램 112페이지      → t_program_us
                           ② 7섹터 소거                   → 섹터별 t_erase_us
                           ③ 카운터 +1
                           ④ 100사이클마다 blank check · tally 1바이트 · UID 재확인
      체크포인트 도달       마모군 소거 → PRBS 기록(P/E +1) → 스윕 → 분석·plot
  }  종단 칩: 종점 100,000 (13점: 100 · 1,000 · 3,000 · 10,000 · 20,000 … 100,000 — 10k 부터 10k 간격)
     파일럿:  종점 300,000 (12점: 100 · 300 · 600 · 1,400 · 3,000 · 6,400 · 13,800 · 29,600 · 63,700 ·
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
**대조군은 마모 루프를 받지 않는다**(`[D17-13]`). 지금 체크포인트 prep 은 마모군 0\~6 만 다시 기록하고, 대조군이 정말
안 변했는지는 마모가 끝난 뒤 `newchip` 1회(섹터 0-127)의 소거 시간으로 본다.

### 사람이 하는 일

`run_wear.py accept --chip chipNN` 한 줄 (`commands.md` §3, 판정 읽는 법은 런북 12).

1. 실행기가 보드를 올리고 UID 를 대조한 뒤 **계획 한 장**을 띄운다 — 태울 자리, 보호 섹터,
   칩의 tally 와 장부 누적, 체크포인트 13점, 예상 시간(실측 단가 기준, 100k 에 약 22시간). 사람은 읽고 `enter`
2. 고칠 것이 있으면 그 자리에서 옵션을 쳐 넣는다(`--to 100000 --confirm-first 0`) — 계획을 다시 띄운다
3. **앞 K 체크포인트에서만** 판정 9줄·장부 행·plot 을 확인하고 `enter`. K 번 치고 나면 무인으로 종점까지
4. 전원이 나가면 `resume` 이 tally 두 벌과 호스트 A 로그로 채택값을 계산한다 — **START 는 사람이**
5. USB 가 잠깐 끊겨도 호스트는 30초 안에 다시 붙어 구간을 잇는다. 그 사이 놓친 체크포인트는 다음 `accept` 가 START 전에
   먼저 잰다(「휴지 뒤」 로 표시, 2026-09-29)
6. 종점까지 돌면 **`pe_end.py`** 로 결과를 정리해 승격한다 (아래 「마모가 끝나면」)

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
| `checkpoints.csv` (C 행) | 체크포인트마다 | `cycle · area · sweep_csv · chip_id · base_sector · n_reads · mhz · session` + 동작 시간 요약(`t_erase_p50/p99/max` · `t_program_p50/p99/max` · `cycle_s_p50`) · 점당 소요 · `measured`(직후/휴지 뒤) |
| `session.log` 의 `#PREP ERASE` · `#PREP PROGRAM` | 체크포인트마다 × 7섹터 | 체크포인트 prep 이 잰 섹터별 소거 · 프로그램 시간(**PRBS 패턴** — A 행의 0x00 과 눈금이 다르다). 블라인드 칩에서 얻는 값과 같은 눈금이라 역산 교정의 재료다. 프로그램 줄은 2026-10-05 재빌드 뒤의 런부터 |
| `docs/chip_pe.md` | 구간·체크포인트마다 | P/E 증분 행 (append-only) |
| 체크포인트의 스윕 CSV·png | 체크포인트마다 | 축 2 와 같은 경로·같은 형식 — **곡선 y1** |

**C 행의 `sweep_csv` 열이 마모 경로와 측정 경로를 잇는 유일한 못이다.** 공통 필수는
`chip_id`(UID) · `git_rev` · `base_sector` · `timestamp` 넷.

### 마모가 끝나면 — 승격 · 교정 곡선 · 수명 역산

```
  세션 폴더 (A 행 · 체크포인트)      host/analysis/pe_end.py --chip chipNN        build/pe_end/<chip>/ 에만 쓴다
        │                               훑어본 뒤 --promote                       docs/results/ 로 (워크플로 13)
        ▼
  교정 표  docs/results/data/wear_curves/wear_curves_<chip>_<YYYY-MM>.csv   A 행을 1k 구간 × 섹터 분위수로
        │   이름에 접미사가 없는 표만 교정이다 (_<온도>C · _ali · _nocal 은 밖)
        ▼
  수명 역산  host/analysis/wear_inverse.py <개봉 prep 로그>
        입력  기준 섹터 32-127 소거 중앙값(= 그 칩의 신품값 · 무리) + 마모 섹터 0-6 소거 시간
        출력  누적 P/E 추정 결과(사후 중앙값) · 68% · 95% 구간 · 판정(신품/저마모/중마모/고마모)
```

**이력을 모르는 칩에서 「신품값」 을 얻는 법이 이 축의 핵심이다.** 마모는 섹터 단위로 쌓이므로, 같은 칩의 지운 적 없는
섹터(32-127)가 그 칩의 신품 기준이 된다. 닳은 섹터가 그보다 몇 배 느려졌는지를 같은 무리 교정 곡선에 대어 사용량을 구간으로
답한다. 모델의 버전별 사양은 `docs/spec/s5.lifetime_inverse_model.md`(현행 v4.3), 쉬운 설명은 `docs/concepts/15.*`.

### 지금까지 나온 것 (2026-11-11)

| 무엇 | 결과 | 어디 |
| --- | --- | --- |
| 파일럿 chip01 0 → 300k | **폭은 움직이지 않았다**(신품 대비 +15.5ps, 3σ 42ps 안). 소거 시간은 5.2배 — 노화 지표는 소거 시간이다 | `docs/results/wear/wear_pilot_chip01.md` |
| 마모 19칩 | 상온 13칩(교정 9 · 교정 밖 chip10 · 12 · 14 · 21) · 온도 6칩(축 4). 이 밖에 chip08 — 마모 함 · 판정 전(모델 고정 판정, 로그 52 [D52-18]). 200k 까지 간 칩 7개(chip02 · 03 · 06 · 07 · 09 · 15 · 21). 폭은 전부 3σ 안 — 넘은 자리는 재장착 단차(chip06 −55 · chip02 +128ps)와 배선 사건(chip07 +590ps), 그리고 chip07 의 초기 −59ps(사후 처리로 표시) · chip14 의 90k −43ps | `docs/results/wear/` · 한눈 표 `data/wear/wear_checkpoint_table_2026-10.md` |
| 소거 노화 | **두 무리** — 100k 에 빠른 무리 2.60-3.97배 · 느린 무리 1.59-1.75배. 빠른 무리는 섹터별 약 18-23ms 계단(상온 FV 6칩 모두, 100k 안에 없던 칩도 11만-17.8만 회에 밟고 그 뒤 104-109ms 평탄), 느린 무리는 계단 없이 미끄럼(200k 1.91-2.25배). 프로그램 시간은 칩마다 갈려 모델에서 뺐다 | `docs/results/wear/wear_endurance_200k.md` |
| 느린 신품의 다른 형 | chip12 · 21(상온) · chip23(85°C) — 신품은 느린 무리인데 빠른 무리 속도로 늙는다. 마모한 느린 신품 7칩 중 3칩이고(chip23 의 원인은 이 형으로 본다), 신품 측정 한 번으로는 갈리지 않는다 → 교정에서 뺐다([D52-12]) | `wear/wear_endurance_200k.md` §8 · `docs/results/blind_temp_chip23_chip26.md` §2 |
| JV 두 칩 | chip10 · 14 — 계단 없이 100k 2.55 · 2.65배. JV 두 칩(각 100k 한 점)은 FV 모델이 54-55k(v3.2) · 59-60k(v4)로 읽었다 — 같은 100k 의 FV 칩도 0.60-0.86배라 이 숫자는 품번 차이의 증거가 아니다. JV 는 계단 없이 늙는 다른 곡선이고 모델은 FV 에서만 검증했다 → 교정 밖 | `wear/wear_endurance_chip10.md` · `wear/wear_endurance_chip14.md` |
| 교정 곡선 | **9칩** — 빠른 chip01 · 02 · 04 · 06 · 09 · 18 · 느린 chip03 · 07 · 15. 100k 너머 곡선 7장(chip01 300k · chip02 · 03 · 06 · 07 · 09 · 15 200k) | `docs/results/data/wear_curves/` |
| 수명 역산 모델 | v1(09-30) → v2(10-01) → v3.2(10-05) → v4(10-09) → **v4.3(10-23 등록, 현행)**. 9칩 LOCO 106점에서 95% 구간 94.5%(띠 91.5-99.1% 안) · 68% 81.7%(띠 59.4-76.4% 위, 과소신 그대로 — 7장 판 값이고 등록 때 6장 판은 81.6% · 94.1%). 정답 100k 근처는 약 0.7배(5장 판, 10/19 측정)로 낮게 읽고 50-100k 의 95% 포함은 99.3%(5장 판, 10/19 측정) — 고마모는 범위로 답한다. 빠른 무리는 교정 3칩에서 포화 | S-5 §2 · `data/inverse_v4_3_ceiling_2026-10.md` §7 · `data/inverse_v4_3_eval_2026-10.md` · `data/inverse_learning_curve_2026-10.md` |
| 기준선 비교 (v3.2 때 · 교정 8칩 · 94점) | 선행식 이진 판별 검출 64/94 → 칩 안 정규화 74/94 · 오경보 0/15. 오차 중앙값 단순 회귀 10,000 대 모델 7,500 | `docs/results/baseline_compare.md` |
| 블라인드 3칩 | chip06(상온 · 정답 12,000 · v2) 68% · 95% 안, 기준 ③ 불통과 · chip26(85°C · 70,000 · v4.3 모델 고정 판정) 68% 안 · 0.86배 합격 · chip23(85°C · 26,528 · 같음) 3.5배 과대 · 95% 밖 불합격 — 원인은 온도가 아니라 칩 종류 | `docs/results/blind_chip06.md` · `docs/results/blind_temp_chip23_chip26.md` |
| 대조군 전제 | 100k 뒤에도 **원격 섹터(32-127)는 신품 대비 0.98-1.00**, 같은 128KB 안의 근접 섹터(7-31)는 1.05-1.25 로 교란된다 — 그래서 역산의 기준을 32-127 로 좁혔다. 85°C chip24 만 기준 섹터도 1.11 이었다 | 각 칩 결과 문서 · `wear/wear_temperature_85C.md` §3 |

### 지금 막힌 것 · 남은 것

- **근접·원격 대조군의 「스윕」 은 여전히 불가** — 읽기 창이 RTL 에 페이지 0\~111 로 고정이다(수정안 #1 `BASE_SECTOR` 미구현,
  로그 44 `[U44-8]`). 2026-11-11 수정안 #4 와 함께 한영웅이 구현하기로 했다(축 1). 그때까지 대조군의 폭은 못 재고, 소거 시간만 `newchip` 으로 본다
- **남은 블라인드** — chip08(마모 함; 상온 · 느린 무리). 등록한 v4.3 7장 판으로 판정한다 — 정답이 이미 드러나 봉인 없는 「모델 고정 판정」(로그 52 [D52-18])
- **v4.4 — 느린 신품의 두 형** — 개봉 한 번으로 못 가르는 chip12 · 21 · 23 형을 어떻게 답할지(로그 52 [U52-7]). chip23 이 채점 칩이다
- **chip26 · chip23** — chip26 을 70k 에서 100k 까지 이을지(지민) · chip23 장부 정정 행(워크플로 14 M2)
- **미배정** — chip25(FV · 느린) · chip30-39(JV 10칩). 용도는 등록부에서 정한다
- **G5 마모 개시 게이트는 지난 일이다** — 엔진 실칩 인수(2026-09-22) 뒤 파일럿으로 개시했고, 블라인드 절차는 종단 3칩 뒤
  S-1 §15 에 등록했다(2026-09-30 · 10-01)

---

## 4. 축 4 — 환경을 바꾼다 (온도, 그리고 전압) **[온도 2점(65 · 85°C) 마모 이력 6칩 — 온도 계수 없음 · 전압 · 슈무 미착수]**

### 무엇을 하는가

온도는 루프의 4번째 단계가 아니라 **마모 런 전체를 다른 온도에서 한 번 더 도는 축**이 됐다. 처음 그린 그림은
「체크포인트마다 25 · 40 · 60°C 에서 스윕」 이었지만, 실제로는 칩 위 65°C · 85°C 를 유지한 채 마모를 태우고 상온 칩들과 견줬다.
블라인드 칩의 판정 측정은 식혀서 상온에서 했다.

### 사람이 하는 일

아두이노 온도 제어기(`hw/temperature_controller.ino` — TMP117 센서 + 필름 히터 구동)를 켜고, `hw/temp_logger.py` 로 1초마다
온도를 `data/temp_<label>_*.csv` 에 남기면서 평소처럼 `run_wear.py accept` 를 돌린다. 끝나면 `pe_end.py --temp` 가 체크포인트
표에 온도 열을 붙인다(워크플로 13).

### 나오는 것

| 칩 | 온도 (센서) | 무리 | 소거 (÷ 신품) | 계단 | 상온 모델 68% · 95% |
| --- | --- | --- | --- | --- | --- |
| chip17 | 65.2°C | 빠른 | 100k 2.44 | 없음 | 1/12 · 11/12 |
| chip16 | 65°C 설정 (칩 온도 미확인) | 빠른 | 100k 4.34 | 7/7 | 6/12 · 12/12 |
| chip24 | 83.5°C | 빠른 | 100k 3.47 | 3섹터 | 12/12 · 12/12 |
| chip22 | 85.0°C | 느린 | 100k 1.90 | 없음 | 3/12 · 12/12 |
| chip26 | 약 84°C | 빠른 | 70k 2.47 | 없음 | 블라인드 합격 |
| chip23 | 85.0°C | 느린 | 26k 1.77 | 없음 | 블라인드 불합격 (chip12 · 21 형) |

- **상온 칩의 개체 산포와 구별되지 않았다** — 같은 설정 65°C 의 chip16 · 17 이 반대로 갔고, 빠른 무리 85°C 둘(chip24 · 26)은 상온 띠 안,
  느린 무리 85°C 신호는 chip22 한 칩이다(chip23 은 다른 형). 100k 네 칩 48점에서 상온 모델 95% 47/48 · 68% 22/48 —
  고온 이력 칩에는 범위로 답한다 (`docs/results/wear/wear_temperature_85C.md` · `wear_temperature_chip16.md` · `wear_temperature_chip17.md`)
- 폭은 고온 칩도 마모 중 3σ 안이다
- 온도 런의 곡선은 교정에 넣지 않는다(`wear_curves_<chip>_*_<온도>C.csv`) — 상온 모델의 외부 검증 점으로만 쓴다

### 지금 막힌 것

- **온도 계수는 낼 수 없다** — 소거 노화는 온도에 따른 일관된 방향이 없고(위), 폭은 같은 칩을 온도를 바꿔 다시 잰 것이 chip17 을
  65°C → 25°C 로 식혀 한 번 잰 것(+40-58ps, 유의미한 변화 아님)뿐이라 ps/°C 와 온도별 윈도우 축소 곡선이 없다
- **모델에 온도 축은 넣지 않았다** — 로그 52 [U52-6] 은 열린 채이고, 해석 문서 · S-1 은 넣지 않는 쪽으로 적었다(`wear/wear_temperature_85C.md` §4)
- 온도는 센서 자리 값이다 — 칩 내부 온도는 모르고, chip16 은 칩 온도 미확인 · chip24 는 초반 30k 에 81-84°C 였다
- **전압 축 · 슈무 플롯은 미착수** — 레벨 시프터와 가변 전원이 든 전용 DUT 보드가 전제인데 제작 전이다(`hw/README.md` TODO).
  없이 전압을 내리면 과전압 스트레스가 교란 변수가 된다(`project_context.md` §5)
- 온도 제어는 PS 폐루프가 아니라 **아두이노 단독**이다. 리포에 XADC 사용 0건

---

## 5. 축을 잇는 것 — 산출물의 생애와 추적성

측정 원본은 커밋하지 않는다. 재현성은 원본 데이터가 아니라 **생성 스크립트 + 파라미터 + UID +
git rev** 로 확보한다.

| 단 | 위치 | 누가 쓰나 | 규칙 |
| -- | --- | --- | --- |
| 1 | `data/` | 기계 (캡처·래퍼·실행기)가 처음부터 쓴다 (2026-11-11 — 그 전에는 `build/` 에 쓰고 사람이 옮겼다) | 원본 보관. 생성은 `open(path, "x")` — 덮어쓰기 경로 자체를 두지 않는다. `.gitignore` (스키마·README만 커밋) |
| 2 | `docs/results/` | 사람이 승격한다 (마모 결과는 `pe_end.py --promote` 가 옮긴다) | `plots/` · `data/` · `captures/` (게이트별). **승격분은 동명 `.md` 로 유래·재현 방법을 짝지어 둔다.** `data/` 의 md 는 수치·표까지, 해석·판정은 `docs/results/` 바로 아래 문서로 — 칩마다 쌓이는 마모 결과만 `wear/` (2026-09-26 · `wear/` 는 2026-10-02) |

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
| `host/run/run_wear.py` | **마모의 정본.** 계획 승인 → 구간 → 체크포인트 측정 → 판정 | `data/wear/<세션>/` + `chip_pe.md` 행 |
| `host/run/wear_link.py` | UART 어댑터 — 경계 10개, 행 체크섬·재전송 | — |
| `host/capture/sweep_uart_capture.py` | UART 행 스트림 → 계약 §6 CSV 2개. 무효 런 판정 | `data/sweep_*.csv` |
| `host/capture/chip_registry.py` | 등록부 파서. UID→라벨 역조회, 제한된 쓰기 | `docs/chip_registry.md` |
| `host/run/chip_pe.py` | P/E 증분 append-only | `docs/chip_pe.md` |
| `host/analysis/bathtub_analysis.py` | 폭 3종 + 체크리스트 5종 + 그림 | `build/plots/` |
| `host/analysis/repeatability_aggregate.py` | 반복 런 집계 (평균±σ) | `build/plots/bathtub_<target>_repeat<n>.png` |
| `host/analysis/monte_carlo_sweep_params.py` | N·θ 사전 등록 golden model | `docs/results/plots/monte_carlo_*.png` |
| `host/analysis/prep_survey_parse.py` | 세션 로그의 `#PREP` 줄 → 신품 조사 수치 | 표 · CSV |
| `host/analysis/pe_end.py` | **마모 종료 뒤 정리의 정본.** 1단계 `build/pe_end/<chip>/` → `--promote` 로 승격 · 그림 · 한눈 표 재생성 | `docs/results/` (워크플로 13) |
| `host/analysis/wear_checkpoint_csv.py` · `temp_wear_summary.py` | 체크포인트 요약 CSV (상온 · 온도 런) | `docs/results/data/wear/` |
| `host/analysis/wear_curves.py` | A 행 → 1k 구간 × 섹터 분위수 (교정 표) | `docs/results/data/wear_curves/` |
| `host/analysis/plot_wear_curves.py` · `wear_checkpoint_table.py` | 칩별 곡선 · 배율 그림 · 칩 × 체크포인트 한눈 표 | `docs/results/plots/` · `data/wear/` |
| `host/analysis/wear_inverse.py` | **수명 역산의 정본** (v4.3). prep 로그 → 추정 구간 · 판정, `--loco` 모의 블라인드 | 화면 · `--out` 기록 |
| `hw/temperature_controller.ino` · `hw/temp_logger.py` | 온도 제어(아두이노) · 1초 온도 로그 | `data/temp_*.csv` |
| `ps/src/flash_wear.c` | 마모 엔진 (PS C, 무상태). tally 2벌·보호 범위는 엔진 상수 | `#WEAR` 행 |
| `ps/src/flash_prep.c` · `flash_io.*` · `flash_id.c` | 소거·PRBS 기록·verify · SPI 배관 · 신원 확인 | `#PREP` · `#G2` 행 |
| `host/tests/` | 호스트 시험 178 — 블랙박스 TB(mock 엔진 · 호스트 시뮬 · 실행기) + 분석 스크립트 시험 | PASS/FAIL |
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
| `run_wear.py uid` 가 「응답 없음」 | 보드에 마모 엔진이 안 떠 있다 — 읽기 명령은 프로그래밍하지 않는다 | `accept` 로 시작한다 (칩 · 케이블 문제가 아니다) |
| 체크포인트 로그에 `#PREP PROGRAM` 이 없다 | `prep-wear` ELF 가 옛 빌드다 | 마모 전에 `reproduce.py --only prep-wear` |
| 체크포인트 스윕 CSV 의 행이 빠진다 | 921600 을 못 따라가는 PC, 또는 USB 접촉 | `--sweep-baud 115200` · `dmesg` 로 disconnect 확인 |
| 마모가 한 사이클에서 선다 (`wip_timeout` 등) | 케이블 · 소켓 접촉 (chip07 · chip12 · chip15 에서 겪음) | `resume` 의 채택값으로 잇는다. 사건 사이클은 곡선에서 뺀다 |

---

## 8. 실선/점선 요약 (2026-11-11)

| 축 | 상태 |
| --- | --- |
| 축 1 빌드·검증 | **동작** — 2025.2 전 빌드 검증(2026-09-14) · 스모크 4 + 셀프테스트 3 + 호스트 시험 178 / G1 cocotb(회귀 21항목 PASS(9/23, 작성자 실행) · ① 판정 3블록 미판정 · F11 · F12 제외 · 게이트 미개방) · 욕조 v2(에지 계수기 + 수정안 #1) 명세 · 수정안 초안, 구현 전 |
| 축 2 신품 측정 | **31칩 측정 종료 (2026-10-25)** — FV 19 · JV 12 · 재장착 σ 13.86ps · 신품 소거 두 무리(빠른 19 · 느린 12) |
| 축 3 마모 | **동작** — 마모 19칩(상온 13 · 온도 6) · 교정 9칩(100k 너머 7장) · 수명 역산 v4.3 · 블라인드 3칩(chip06 68% 안 · 기준 ③ 불통과 · chip26 합격 · chip23 불합격) / 대조군 스윕(수정안 #1) · 블라인드 chip08 · v4.4 남음 |
| 축 4 온도·전압 | **온도 2점** — 65°C chip16 · 17 · 85°C chip22 · 23 · 24 · 26 마모 이력(아두이노 제어), 상온 개체 산포와 구별 안 됨 / 온도 계수는 낼 수 없음 · 전압 · 슈무는 DUT 보드 선행으로 미착수 |

일정: 최종보고서 2026-10-02 제출 · 최종 발표 2026-11-06 (끝) · 지금은 M2 졸업논문 (`docs/workflow/14.contest_thesis_paper_milestones.md`).

---

## 9. 미결 의사결정

| # | 항목 | 상태 |
| - | --- | --- |
| 1 | **느린 신품의 두 형을 어떻게 답하나 (v4.4)** — 사전 확률을 나눔 · 개봉 때 짧은 추가 마모로 기울기를 잼 · 「두 형 중 하나」 로만 답함 | chip23 이 재료로 생겼다(11/1). 결정 대기 (로그 52 [U52-7]) |
| 2 | **온도 PE 를 모델에 넣나** | 열린 채 — 해석 문서 · S-1 은 넣지 않는 쪽으로 적었다 (로그 52 [U52-6]) |
| 3 | **빈 구간(33.7-47ms) 칩** — v4 밖. chip14 · JV chip33 · 34 · 35 가 이 자리다 | 보고서에 「미검증」 한 줄 (로그 52 [U52-4]) |
| 4 | 수정안 #1 `BASE_SECTOR` (읽기 창) — 없으면 대조군의 폭을 못 잰다 | 발의 2026-08-23, 구현 0건. 2026-11-11 수정안 #4 와 함께 한영웅이 구현하기로 함 (로그 55 [D55-14] — 담당 문제 [U48-2] 는 이것으로 풀림) |
| 5 | **욕조 v2 승인** — 명세 S-6 · 수정안 #4 초안 | 박지민 · 장세은 검토 · 승인 대기 (로그 55 [D55-15]) · 기존 스윕의 평균 · 산포 분석은 진행 중 ([U55-2]) |
| 6 | chip26 을 70k 에서 100k 까지 잇나 | 지민 (워크플로 14 M2) |
| 7 | M2 기한 · 데이터 마감 | 학과 일정 확인 뒤 (워크플로 14) |
| 8 | 엔진 보호 범위(`CTRL_RANGES`)는 ELF 상수다 — 마모 자리를 옮기면 재빌드 | `[D44-2]` |
| 9 | 신품 조사 2단 CSV(호스트 파서) · 다칩 배치 `run_newchip.py` | 미구현 — 신품 31칩은 이것 없이 `run_sweep_chip.py --mode newchip` 으로 끝났다 (2026-10-25) |

닫힌 것: G5 ② ③(파일럿이 폭 불변을 답했고 블라인드 절차는 S-1 §15 에 등록) · 본 실험 배치(종단 100k · 13점 격자 · 마모 그룹 0\~6 하나) ·
v4 를 무엇으로 짜나(v4 2026-10-09 등록 [D52-8] → v4.3 10-23 등록 [D52-16], 프로그램 축 v4.2 는 폐기 [D52-9]) ·
새 칩의 교정과 블라인드 가르기(2026-10-16 배정 — 워크플로 14 M2 · 등록부) · chip10 교정 여부(JV 로 판독, 교정 밖 — `wear/wear_endurance_chip10.md` · 로그 53 [D53-5]).
