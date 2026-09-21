# 명령 — 사람이 치는 것의 정본

이 문서에는 **명령만** 있다 — 언제 치나 · 무엇을 치나 · 치면 무엇이 남나 · 실패하면 어디를 보나.
**「왜 그렇게 되어 있나」는 여기 없다** — `docs/project_pipeline.md`(흐름·상태·이유)로 간다.
다른 문서는 명령을 복사하지 않고 이 문서의 절 번호로 링크한다. 명령이 바뀌면 **여기를 먼저 고친다.**
워크플로(`docs/workflow/`)는 그날의 순서이고, 날이 끝나면 통한 명령은 여기로, 흐름은 파이프라인으로 올라간다.

- 흐름·상태·이유: `docs/project_pipeline.md` (게이트 정의·판독표는 `docs/workflow/4.gate_map.md`)
- `reproduce.py` 가 대신 치는 원명령·기대 산출물·검증 수치: `docs/build_reproduction.md`
- 측정 사양(왜 그 조건인가): `docs/spec/`

---

## 0. 계층 — 무엇을 직접 치는가

```
[최상단]  사람이 친다
    reproduce.py                    빌드·검증 전체 (보드 없이)
    host/run/run_sweep_chip.py      실칩 측정 (prep → 스윕 → 분석)
    host/run/run_wear.py            P/E 마모 엔진 (accept · resume · tally-erase · 읽기)

[중하단]  위 스크립트가 부른다. 직접 칠 일은 드물다 — §4 에 그 드문 경우만
    host/capture/sweep_uart_capture.py   UART → CSV
    host/analysis/bathtub_analysis.py    욕조 판정·폭 (run_sweep_chip 이 부른다)
    host/capture/chip_registry.py        등록부 파서
    host/run/chip_pe.py                  P/E 이력
    ps/scripts/program_*.tcl             xsct 프로그래밍
    ps/scripts/build_*.py                Vitis ELF 빌드
    fpga/scripts/build_*.tcl             Vivado 비트·XSA

[보드 위]  ELF. 사람이 직접 실행하지 않는다 (xsct 가 올린다)
    flash_prep · flash_id · flash_jedec · g0_sweep/g3_sweep · core_smoke · flash_wear
```

**터미널은 하나면 된다.** 최상단 스크립트가 UART 를 쥔 채 xsct 를 부르므로, 캡처용 창을
따로 열 필요가 없다. (직접 `sweep_uart_capture.py` 를 쓸 때만 창이 둘 필요하다 — §4)

---

## 1. `reproduce.py` — 빌드·검증

보드가 필요 없다. 새 PC 에서 처음 하거나, 소스를 고친 뒤에 돌린다.

```bash
python reproduce.py                    # 전체 11단계 (약 10분)
python reproduce.py --only g3-25       # 한 단계만
python reproduce.py --only tb wear     # P/E 엔진만 — TB + flash_wear.elf (실칩 전 최소, 약 30초)
python reproduce.py --vitis-only       # ELF 만 다시 (Vivado 생략)
python reproduce.py --list             # 단계 목록과 실제 명령
```

| 옵션                             | 언제                                                                          |
| -------------------------------- | ----------------------------------------------------------------------------- |
| `--only <단계…>`              | 한두 단계만. 단계 이름은`--list` 에                                         |
| `--vitis-only`                 | C 코드만 고쳤을 때 (비트스트림 재사용)                                        |
| `--no-sim` / `--no-selftest` | `iverilog`·`uv`·`gcc` 가 없는 PC. `--no-selftest` 는 `tb` 도 뺀다 |
| `--keep-going`                 | 실패해도 끝까지 — 기본은 첫 실패에서 중단                                    |

기본 단계: `sim · selftest · tb · g0 · g2 · prep · id · wear · g3-25 · g3-45 · g3-75`
선택 단계(`--only` 로만): `jedec · smoke · g0e · g3e-25/45/75`

**읽는 법.** 각 단계는 6겹으로 채점된다 — 종료 코드 · 완료 문구 · 산출물 존재와 갱신 ·
타이밍 충족 · 수치 기준표 · 빌드 파라미터(g3 의 steps, wear 의 `git_rev`). `WARN` 은 실패가
아니라 기준표와 다른 것이고 **로그에 적을 거리**다. 요약은 `build/logs/reproduce_<UTC>/summary.txt`
에도 남는다. 덮는 것은 소스에서 다시 만들 수 있는 bit·XSA·ELF 뿐이라 언제 돌려도 되지만,
**보드 측정 직전에는 돌리지 않는다** — 단계가 중간에 실패하면 그 ELF 는 깨진 채 남는다.

Vivado/Vitis 가 PATH 에 있어야 한다 — `source ~/Xilinx/2025.2/Vitis/settings64.sh`
(Windows 는 `settings64.bat`). 영웅 PC 는 `.bashrc` 에 들어 있어 따로 칠 필요가 없다.

---

## 2. `run_sweep_chip.py` — 실칩 측정

한 프로세스가 UART 를 쥔 채 **세션1 → 세션2 → 분석**을 잇는다 (왜 한 명령인지는 파이프라인 §2.1).

```bash
uv run python host/run/run_sweep_chip.py --mode <newchip|sweep> --mhz <25|45|75> [옵션…]
```

### 모드 — 무엇을 하는가 (필수)

|               | `--mode newchip`                                                             | `--mode sweep`                     |
| ------------- | ------------------------------------------------------------------------------ | ------------------------------------ |
| 세션1         | `flash_prep` — JEDEC·UID·blank 조사 → **소거 + 정답지(PRBS) 쓰기** | `flash_id` — JEDEC·UID 만 읽는다 |
| **P/E** | **+1** (`chip_pe.md` 에 기록)                                          | **0**                          |
| 칩 식별       | 기계가 읽고, 신규면 라벨을 묻는다                                              | 기계가 읽어 등록부에서 라벨을 찾는다 |
| 세션2         | g3 비트 + 스윕 ×N                                                             | 같음                                 |
| 분석          | 자동                                                                           | 같음                                 |

모드가 정한 것은 옵션으로 뒤집을 수 없다 — `sweep` 에 prep 을 켜는 스위치가 없고 `newchip` 에
`--chip` 을 줄 수 없다 (이유는 파이프라인 §2.1).

### 옵션

| 옵션              | 기본             | 무엇 / 언제                                                                                                                 |
| ----------------- | ---------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `--mode`        | **필수**   | 위 표                                                                                                                       |
| `--mhz`         | **필수**   | SPI 클럭. 어느 g3 비트를 구울지 정한다. 기계가 알 수 없는 값이라 필수다                                                     |
| `--chip NN`     | 없음             | **재고 싶은 칩.** `2`·`02`·`chip02` 다 받는다. 주면 읽은 라벨과 대조해 어긋나면 중단. 생략하면 읽은 대로 간다 |
| `--repeat N`    | 1                | 스윕 반복. 세션1 은 1회, 스윕만 N회                                                                                         |
| `--reseat`      | 꺼짐             | 회차**사이**에 재장착 프롬프트 + UID 재확인. `--repeat 2` 이상에서만                                                |
| `--pl {4,6}`    | 없음             | PAY_LEAD 보험 비트스트림. 전 위상 BER 0.5 가 나올 때(75MHz 임계). 비트는 먼저 굽는다 (`-tclargs bit <mhz> <k>`)           |
| `--port`        | `/dev/ttyUSB1` | Windows 는`COM<N>`                                                                                                        |
| `--baud`        | 921600           | 2026-09-15 이전에 구운 ELF 는`115200`                                                                                     |
| `--base-sector` | 0                | 수정안#1 미승인 — 0 만 허용                                                                                                |
| `--blind`       | 꺼짐             | `chip_pe.md` 에 증분 대신 `(봉인)`. `newchip` 에서만                                                                  |

N(위상 스텝당 읽기 횟수)은 옵션이 아니다 — 실칩은 **112 고정**. `BEGIN` 의 `n=` 이 다르면 첫 줄에서 중단한다.

### 상황별

```bash
# 신품 첫 투입 (chip05~10) — P/E +1
uv run python host/run/run_sweep_chip.py --mode newchip --mhz 25

# 등록된 칩 재측정 — 어느 칩인지는 기계가 안다. P/E 불변
uv run python host/run/run_sweep_chip.py --mode sweep --mhz 25

# 앵커를 집어야 할 때 — 다른 칩을 꽂았으면 스윕 전에 걸린다
# (앵커는 prep 없이 잰다 — 재장착 성분만 보려는 것이고 P/E 도 안 쓴다. S-2 §8)
uv run python host/run/run_sweep_chip.py --mode sweep --mhz 25 --chip 2

# 재장착 σ — 3회, 회차 사이마다 빼고 다시 꽂는다 (매번 UID 재확인)
uv run python host/run/run_sweep_chip.py --mode sweep --mhz 25 --chip 2 --repeat 3 --reseat

# 조사·사전 쓰기만 하고 스윕은 나중에 → 전용 모드는 없앴다.
#   newchip 으로 돌리고 스윕 결과를 버리거나, 나중에 sweep 으로 다시 잰다
```

### 실패하면 무엇을 보는가

| 증상                                    | 뜻                                               | 볼 곳                              |
| --------------------------------------- | ------------------------------------------------ | ---------------------------------- |
| `session_idfail_*.log`                | **꽂힌 칩이 다르다** — 그것만 이 이름이다 | 로그의 읽은/기대 UID               |
| `session_prepfail_*.log`              | `flash_prep` 이 PASS 전에 죽었다               | `#PREP FAIL`·`#PREP ERROR` 줄 |
| `session_<batch_id>.log` (개명 안 됨) | ELF 누락·타임아웃 등 칩 신원과 무관한 실패      | 마지막 몇 줄                       |
| `*_invalid.csv`                       | 스윕이 완주하지 못했다 (행 결측·중단)           | `#G0 SWEEP END` 줄의 `valid=`  |
| `분석 실패 — 측정은 유효하다`        | CSV 는 정상. 분석만 다시 돌리면 된다             | §4 「분석만 다시」                |

세션 로그는 `build/data/session_*.log`, CSV 는 `build/data/sweep_*.csv` 에 생긴다.
**측정이 끝나면 원본을 `data/` 로 옮긴다** — `build/` 는 재빌드 때 지워진다.

---

## 3. `run_wear.py` — P/E 마모 엔진

g2 비트 + `flash_wear.elf`. 한 프로세스가 xsct 로 굽고 UART 를 쥔 채 명령·응답·`#WEAR` 행을 받는다.
인수 시험의 절차와 결과 **읽는 법은 런북 12**(`docs/workflow/12.*`)다 — 여기는 명령만.

```bash
uv run python host/run/run_wear.py <명령> [옵션…]
```

| 명령                                           | 무엇을 하는가                                                                                   | P/E                                      | 자물쇠                                                                                                     |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `accept` (계획 승인 → 마모)                                     | 프로그래밍 → UID 대조 → START → 완주 대기 → verdict 9줄 (A1~A7 · C · probe)               | `--base-sector` 영역에 `--to` 까지 | 계획 화면에서 사람이 enter 를 쳐야 START 를 보낸다 (`--i-approve-real-pe` 는 그 화면을 건너뛴다)                                                      |
| `resume`                                     | RESUME → 판정 → BLANK → (잔류 있으면 REERASE) → 채택값 출력.**START는 보내지 않는다** | 재소거 때만 섹터 ±1                     | —                                                                                                         |
| `tally-erase`                                | tally 두 벌(512·1,536) 소거 — 같은 칩으로 0 부터 다시                                         | 512·1,536 각 +1                         | `--i-approve-tally-erase` + **그 칩의 UID 를 직접 타이핑** + 지우기 전 값을 `chip_pe.md` 에 먼저 |
| `status` · `tally` · `dump` · `uid` | 읽기                                                                                            | 0                                        | —                                                                                                         |
| `halt`                                       | 다음 사이클 경계에서 정지. 이어 가려면 `accept` (표시값은 tally 에서 읽는다 — 눈금 밖이면 `--cycle <표시값>`)                               | 0                                        | —                                                                                                         |

| 옵션                                          | 기본                        | 무엇 / 언제                                                                                                                                                                                                                       |
| --------------------------------------------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `--chip NN`                                 | `chip01`                  | 등록부 라벨. 소켓의 UID 와 다르면 아무것도 하지 않는다                                                                                                                                                                            |
| `--to N`                                    | 마지막 체크포인트 (300,000) | **여기까지 누적으로 태운다.** 칩이 닳는 양은 이 값만이 정한다. 체크포인트가 없으면(TB) 기본 100                                                                                                                             |
| `--confirm-first K`                         | 1                           | 앞의**K 체크포인트**에서 사람이 확인한다 — enter 로 계속, `q` 로 정지. K 번 치고 나면 그 뒤는 무인                                                                                                                       |
| `--cycle N`                                 | **칩의 tally**        | 어디서부터인가. 안 주면 칩이 기억하는 누적(정본)을 읽어 쓴다. 복구 뒤에는`resume` 이 준 채택값을 명시한다                                                                                                                       |
| `--base-sector N`                           | **0**                 | **태울 자리**(7섹터의 시작). 0 = 마모 그룹 0~6 (S-1 §2) · 1000 = TB 전용 (S-4 §9, 인수 시험). 대조군·tally 는 엔진이 거부한다. `resume` 도 같은 값을 줘야 한다. 스윕의 `--base-sector`(읽는 창)와 **다른 것** |
| `--checkpoints 목록`                        | 마모 그룹이면 고정 12점     | 체크포인트 누적값(쉼표) 또는`none`. **구간 경계이자 측정 지점**이다                                                                                                                                                       |
| `--sweep-mhz N`                             | 25                          | 체크포인트 스윕의 SPI 클럭 (S-1 §3 은 25MHz 고정).**마모 속도와는 무관하다**                                                                                                                                               |
| `--no-measure`                              | 꺼짐                        | 체크포인트에서 재지 않고 태우기만 한다. 소거 시간 요약은 그래도`checkpoints.csv` 에 남는다                                                                                                                                      |
| `--i-approve-real-pe`                       | 꺼짐                        | **계획 확인 화면을 건너뛴다** — 비대화형(스크립트)에서 실칩에 P/E 를 낼 때 필요                                                                                                                                            |
| `--no-program`                              | 꺼짐                        | xsct 생략 — 이미 떠 있는 엔진에 붙는다                                                                                                                                                                                           |
| `--sim BIN`                                 | 없음                        | 실칩 대신 호스트 시뮬레이션. P/E 없음, 계획 확인·체크포인트 측정은 건너뛴다                                                                                                                                                      |
| `--host-log-max N` / `--from-session DIR` | —                          | `resume` 이 §8.3 판정에 쓰는 호스트 A 로그의 최대 cycle                                                                                                                                                                        |
| `--port` / `--baud`                       | `/dev/ttyUSB1` / 921600   | Windows 는`COM<N>`                                                                                                                                                                                                              |

**사람이 치는 것은 칩과 명령뿐이다.** 나머지는 기본값이고, START 전에 실행기가 계획을 화면에
띄우고 enter 를 기다린다 — 고칠 것이 있으면 그 자리에서 옵션을 쳐 넣으면 계획을 다시 띄운다.
구간을 몇 개로 나누는지는 옵션이 아니다: **체크포인트가 경계**이고, 그 사이가 30,000사이클보다
길면 실행기가 알아서 더 쪼개 파일로 흘린다(호스트가 33시간치를 들고 있지 않도록). `--to` 와
`--checkpoints` 는 **100 의 배수**여야 한다 — tally 가 100사이클마다 1바이트라 그 사이에서 끊으면
칩의 눈금과 호스트의 숫자가 어긋난다(§13 A5). `--cycle` 은 예외다.

**예상 시간**은 `남은 사이클 × 사이클 단가 + 남은 체크포인트 × 점당 비용`이다. 사이클 단가는
직전 체크포인트가 남긴 실측(`checkpoints.csv` 의 `cycle_s_p50`)을 쓰고, 없으면 typ 0.405초
(S-1 §1)로 떨어진다. 화면에 어느 쪽인지 같이 찍힌다.

### 상황별

```bash
# 보드 없이 연습 — 실칩과 같은 명령·같은 verdict.txt (조원 교육용)
#   임시 장부를 반드시 준다 — 안 주면 연습이 docs/chip_pe.md 에 증분 행을 남긴다
cp docs/chip_pe.md /tmp/practice_pe.md
uv run python host/run/run_wear.py accept --sim build/sim/flash_wear_sim --no-program \
    --to 300 --chip-pe /tmp/practice_pe.md --logdir /tmp/practice_logs

# 실칩, 읽기 전용 점검 (P/E 0) — 소켓의 칩·tally 상태
uv run python host/run/run_wear.py uid
uv run python host/run/run_wear.py tally
# 공짜 probe — START 없이 BLANK 만. 갓 소거된 7섹터면 program_fail 229376 이 나와야 한다
#   --base-sector 를 accept 와 같은 값으로 줘야 한다 (기본 0 = 마모 그룹)
uv run python host/run/run_wear.py resume --base-sector 1000 --host-log-max 0

# 마모 — 이것만 친다. 계획을 띄우고 enter 를 기다린다
uv run python host/run/run_wear.py accept --chip chip01
#   enter = 그대로 진행 · "--to 100000 --confirm-first 3" 처럼 쳐 넣으면 고쳐서 다시 띄운다 · q = 취소
#   체크포인트마다 0~6 소거+PRBS(P/E +1) → 스윕 → 분석·plot 을 실행기가 하고, 앞 K 점에서만 사람에게 묻는다

# 100사이클 인수 (A 시험) — 엔진을 고친 뒤에만. 본 마모의 첫 체크포인트(100)가 같은 판정을 돌린다 (런북 12)
uv run python host/run/run_wear.py accept --chip chip01 --base-sector 1000 --cycle 0 --to 100
# 이어 돌리기 (halt 뒤) — --cycle 을 빼면 칩의 tally 에서 이어 간다
uv run python host/run/run_wear.py accept --base-sector 1000 --to 200
# 전원 차단 뒤 — 채택값만 출력한다. START 는 사람이 위 명령으로
uv run python host/run/run_wear.py resume --from-session build/logs/wear/<세션>
# 같은 칩으로 처음부터 — UID 를 타이핑해야 지운다. 지운 값은 chip_pe.md 에 먼저 남는다
uv run python host/run/run_wear.py tally-erase --chip chip01 --i-approve-tally-erase
```

### 남는 것

`build/logs/wear/<session>/` — `plan.txt`(승인받은 계획 그대로) · `checkpoints.csv`(C 행 — 스윕 CSV 와
동작 시간 요약 `t_erase_p50/p99/max` · `t_program_p50/p99/max` · `cycle_s_p50` · 점당 소요) · `verdict.txt` ·
`A.txt` · `B.txt` · `R.txt`(사건 있을 때만) · `H.txt` · `raw.txt` · `commands.txt` · `session.log`.
구간마다 **덧붙는다** — 판정 9줄도 구간 머리글과 함께 `verdict.txt` 에 쌓이고, 행 파일은 구간 끝에
흘려 쓰므로 호스트가 죽어도 직전 구간까지는 남는다. `chip_pe.md` 에는 구간마다 증분 행 하나. `build/` 는 재빌드에 지워지지
않지만 커밋도 안 되므로 필요하면 `docs/results/` 로 승격한다. 종료 코드 0 = 전부 PASS ·
1 = FAIL 있음 · 2 = `resume` 이 사람을 부름 · 3 = 중단(거부·UID 불일치·타임아웃).

### 실패하면 무엇을 보는가

| 증상                          | 뜻                                            | 다음                                                       |
| ----------------------------- | --------------------------------------------- | ---------------------------------------------------------- |
| `REJECT E_DIRTY`            | tally 에 마크가 있는데`--cycle 0`           | 이어 돌리기(`--cycle <tally×100>`) 또는 `tally-erase` |
| `UID 불일치`                | 소켓의 칩이`--chip` 과 다르다               | 칩 확인. 아무것도 하지 않았다                              |
| `엔진이 error 로 부팅했다`  | SPI/JEDEC/UID 실패                            | 배선·JP5·칩 장착. START 는 안 갔다                       |
| `엔진이 running 이다`       | 이전 세션이 돌고 있다                         | `halt` 로 세우거나 끝나기를 기다린다                     |
| verdict`probe` FAIL         | 세는 경로가 죽었다                            | B 행의 0 을 믿지 않는다. 런북 12 §3.3                     |
| `clean=0` (`tally-erase`) | 소거 뒤에도`0xFF` 가 아니다 — 엔진은 error | 쓰기 보호(BP)·배선                                        |

---

## 4. 중하단을 직접 부를 때

평소에는 최상단이 부른다. 직접 칠 이유가 있는 경우만 적는다.

```bash
# 보드↔칩 통신만 확인 (배선 의심, 게재 2번 캡처) — 1초 주기 반복
xsct ps/scripts/program_g2.tcl build/vitis_jedec/flash_jedec/build/flash_jedec.elf
uv run python -m serial.tools.miniterm /dev/ttyUSB1 921600

# 이 칩이 몇 번인지만 확인 — 쓰기 없음, P/E 0
xsct ps/scripts/program_g2.tcl build/vitis_id/flash_id/build/flash_id.elf

# UID → 라벨 역조회 (보드 불필요)
uv run python host/capture/chip_registry.py --lookup D1642C74E7134527

# UART 원문만 보고 싶다 (진단) — CSV 를 만들지 않는다
uv run python host/capture/sweep_uart_capture.py --raw

# G0 루프백 캡처 (실칩 없이 계측기 점검) — 터미널 둘이 필요하다
uv run python host/capture/sweep_uart_capture.py --loopback     # 터미널 1 (먼저)
xsct ps/scripts/program_g0.tcl                                  # 터미널 2
```

**수신을 먼저, 송신을 나중에.** 보드는 ELF 가 뜨는 순간부터 뿜는다. 최상단 스크립트는
이 순서를 스스로 지키지만, 직접 부를 때는 사람이 지켜야 한다.

### 분석만 다시 — `bathtub_analysis.py`

```bash
uv run python host/analysis/bathtub_analysis.py data/sweep_chip04_<uid>_<stamp>.csv --json
```

`--json` 이면 수치가 `<입력>.analysis.json` 으로도 남는다. 화면에는 폭 3종(1e-2/1e-3/1e-4)과
체크리스트 5종이 뜨고, 그림은 `build/plots/bathtub_<stem>.png` 다.

측정 중에는 `run_sweep_chip.py` 가 자동으로 부르므로 직접 칠 일은 **파라미터를 바꿔 다시
볼 때**와 **자동 분석이 실패했을 때**다.

**체크리스트 5번(BER 연속성)이 FAIL 이면 곡선이 아니라 RTL 을 의심한다** — 한 스텝 만에
BER 이 0.001 → 0.25 로 뛰는 것은 물리적으로 불가능하고, 캡처 비트 정렬 슬립의 서명이다.

관련: 신품 조사 수치를 세션 로그에서 뽑는 파서 —
`uv run python host/analysis/prep_survey_parse.py data/session_chip04_*.log [--csv]`

---

## 5. 하지 않는 것

- **`sweep` 모드로 P/E 를 쓰지 않는다.** 그런 인자가 없다. 사전 쓰기가 필요하면 `newchip` 이다
- **`--chip` 으로 라벨을 "지정"하지 않는다.** 그것은 대조용 선언이고, 실제 라벨은 UID 가 정한다
- **신규 칩을 등록부에 손으로 적지 않는다.** `newchip` 이 기계가 읽은 UID 로만 등록한다
- **`build/` 안의 측정 원본을 그대로 두지 않는다.** 재빌드 때 사라진다 — `data/` 로 옮긴다
- **실칩에 승인 플래그 없이 P/E 를 내지 않는다.** `accept` 는 `--i-approve-real-pe`, `tally-erase` 는
  `--i-approve-tally-erase` + UID 타이핑. `--sim` 만 예외다
- **tally 를 자동으로 지우지 않는다.** `E_DIRTY` 를 받았다고 실행기가 알아서 `tally-erase` 를 부르는 길은 없다
