#!/usr/bin/env python3
"""마모 엔진 호스트 실행기 — 실칩 인수 시험(S-4 §9)과 복구(S-1 §8.3)를 명령 한 줄로.

    run_wear.py accept  --chip chipNN --i-approve-real-pe [--cycle 0] [--delta 100]   ELF 프로그래밍 → START → 캡처 → A1~A7·C 판정
    run_wear.py accept  --chip chipNN --to 100000 --delta 30000 --first-delta 1000 --confirm-first 3
                                                                        구간을 이어 목표까지 — 앞 3구간만 사람이 보고 그 뒤 무인
    run_wear.py status | halt | tally | dump | uid                      읽기·정지 (halt 는 다음 사이클 경계)
    run_wear.py resume  --chip chipNN --host-log-max N | --from-session <dir>          RESUME → decide_resume → BLANK → (REERASE) → 채택값 출력
    run_wear.py tally-erase --chip chipNN --i-approve-tally-erase                 tally 두 벌 소거 — UID 를 직접 타이핑해야 하고, 장부에 먼저 적는다

    공통: --port /dev/ttyUSB1 | --sim build/sim/flash_wear_sim (호스트 시뮬레이션, P/E 없음)
          --wear-baud 921600 (마모 링크 · 체크포인트 prep) · --sweep-baud 921600 (체크포인트 스윕만) — 호스트 포트와
          펌웨어 양쪽에 걸린다. 921600 스윕에서 CSV 행이 빠지는 PC(지민)는 --sweep-baud 115200
          --no-program (accept 에서 xsct 단계 생략 — 이미 떠 있는 엔진에 붙는다)

**P/E 는 비가역이다.** `accept` 는 `--i-approve-real-pe` 없이는 실칩에 START 를 보내지 않는다 (`--sim` 은 예외).
`resume` 은 START 를 자동으로 보내지 않는다 — 채택값을 출력하고 사람이
`accept --cycle <채택값> --delta <n>` 으로 잇는다. 태울 자리는 `--base-sector` 이고 기본값은 인수 시험의
TB 전용 1,000~1,006 이다 (S-4 §9) — 파일럿 마모 그룹은 `--base-sector 0` (S-1 §2.1). 대조군(7~13 ·
2,041~2,047)과 tally(512 · 1,536)는 엔진이 거부한다 (E_CTRL_OVERLAP · E_TALLY_OVERLAP).
체크포인트 편성(prep → 스윕 → ELF 교체 → START)은 근접·원격 스윕이 막혀 있어 (로그 44 [U44-8])
아직 이 실행기에 없다 — 체크포인트마다 사람이 잇는다.

세션 로그: build/logs/wear/<session>/ — raw.txt(원문 전부) · H/A/B/R/D.txt(행 분리) · commands.txt ·
verdict.txt · resume.txt. 문자열 생성·해석은 host/tests/host_side.py, 전송은 host/run/wear_link.py.
의존: run_sweep_chip.py 의 Session·run_xsct·Drained·require_tty, chip_pe.py, chip_registry.py, pyserial, xsct.
"""

import argparse
import os
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "tests"))
sys.path.insert(0, str(REPO / "host" / "capture"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import chip_pe                                              # noqa: E402
import chip_registry                                        # noqa: E402
import host_side as hs                                      # noqa: E402
import wear_link as wl                                      # noqa: E402
from run_sweep_chip import Abort, Drained, Session, require_tty, run_prep, run_xsct   # noqa: E402

WEAR_ELF = REPO / "build" / "vitis_wear" / "flash_wear" / "build" / "flash_wear.elf"
PROGRAM_G2 = REPO / "ps" / "scripts" / "program_g2.tcl"
SWEEP_RUNNER = REPO / "host" / "run" / "run_sweep_chip.py"
PLOT_DIR = REPO / "build" / "plots"
LOG_ROOT = REPO / "build" / "logs" / "wear"
WEAR_BASE_TB, WEAR_N = 1000, 7                              # S-4 §9 TB 전용 마모 영역 — 인수 시험의 기본값
WEAR_BASE_GROUP = 0                                         # S-1 §2 마모 그룹 0~6 — 읽기 창과 같은 자리. 파일럿·종단 다 여기
                                                            # (reproduce.py "prep-wear" 의 PREP_BASE=0 · PREP_N=7 과 같은 값 — 옮기면 둘 다)
AREA_NAME = {WEAR_BASE_GROUP: "마모 그룹 (S-1 §2)", WEAR_BASE_TB: "TB 전용 (S-4 §9)"}
TALLY_STRIDE = 100                                          # tally 1바이트 = 100사이클 (S-1 §8.1) — 구간의 눈금
PATTERN = 0x00                                              # 파일럿 고정값 (S-1 §1)
ERASE_WARN_US = 400_000                                     # S-1 §10·§13 A6
SEC_PER_CYCLE = 4.0                                         # 대기 상한 산정용 — 마모 런 사이클은 소거 시간과 함께 는다 (chip01 122k 에서 1.05s, 소거 115ms). 2.0 이면 소거 270ms 에서 호스트가 먼저 죽는다 (2026-09-24)
CYCLE_TYP_S = 0.405                                         # S-1 §12 typ — 계획의 예상 시간 표시용
CHECKPOINTS = (100, 1_000, 3_000, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000, 70_000, 80_000, 90_000, 100_000)
"""종단 3칩의 13점 — 정격 내구 100,000 이 종점이다 (S-1 §15 2026-09-26 추기 · 로그 48 [D48-15]).

폭은 파일럿 300k 까지 움직이지 않았으므로(H1) 체크포인트는 폭이 아니라 **prep 소거 시간과 마모 루프 소거 시간의
교정점**이다. 소거 시간이 가파른 앞은 로그로(100 · 1k · 3k), 블라인드 N 이 있을 10k 이상은 10k 등간격으로.
100 은 파일럿 때(2026-09-22)부터 A 시험(S-1 §13, 100사이클)을 겸한다 — 사이클 수도 판정도 같다.
파일럿 chip01 은 옛 12점(100 · 300 · 600 · 1,400 · 3,000 · 6,400 · 13,800 · 29,600 · 63,700 · 137,000 · 294,500 · 300,000)
으로 돌았다 — 세션 폴더의 checkpoints.csv 가 그 기록이다.

0 은 이 목록에 없다 — 마모 전 신품 측정(S-2, `run_sweep_chip.py --mode newchip --mhz 25`)이 그 점이다.
그래서 accept 전에 그 칩의 유효 25MHz 런이 집계표에 있는지 사람이 확인한다 (chip01 은 2026-09-22 에 채웠다 —
그때까지 "이미 있다" 고 적혀 있었지만 chip01 에는 없었다).
마모 그룹(--base-sector 0)에만 적용된다 — TB 영역에는 체크포인트가 없다."""
SEG_CHUNK = 30_000                                          # 체크포인트 사이를 이만큼씩 끊어 파일로 흘린다 (약 3.4h · 로그 17MB · RSS 250MB)
CP_COST_S = 120.0                                           # 체크포인트 1점의 기본 비용 (prep + 스윕 59초 + ELF 교체) — 실측되면 갈아탄다
CP_HEADER = ("cycle,area,sweep_csv,chip_id,base_sector,n_reads,mhz,session,"
             "t_erase_p50,t_erase_p99,t_erase_max,t_program_p50,t_program_p99,t_program_max,"
             "cycle_s_p50,cp_s\n")
PROBE_TOTAL = WEAR_N * 4096 * 8                               # 7섹터 전 비트 = 229,376 — probe 의 정답 (pattern 0x00)


# ── 순수 함수 — pytest 가 잰다 ──────────────────────────────────────────────
def judge_accept(log, status, tally, dumps, uid, expected_uid, n=100, probe=None, start=0, erase_check=True):
    """S-1 §13 A1~A7 + C + probe. [(항목, 통과, 설명)]. A6 는 실칩에서만 뜻이 있다 (mock·sim 은 시계가 가짜).

    `erase_check` — A6(소거 < 400ms)는 **인수 시험(TB 영역)에서만** 채점한다. 신품이 데이터시트 최대를
    넘기면 배선·전원을 의심하라는 시험대 검사이지 칩의 기준이 아니다. 마모 런에서는 소거가 길어지는
    것이 잴 대상이라 채점하지 않는다 — 값은 A.txt·checkpoints.csv 에 그대로 남는다 (로그 48 §12).

    `start` 은 이 구간이 시작한 누적값이다. A2·A3·A5 의 행은 **이 세션이 본 것만** 세므로 기준도
    구간이어야 한다 — 그래야 이어 돌리기·무인 구간이 매번 FAIL 로 나오지 않는다. A1·A4 는 칩이
    들고 있는 절대값(카운터·tally)이라 누적 그대로 본다. 결함이 보인 뒤에는 검사 주기가 10 으로
    조밀해지므로(S-1 §7) B 행은 「기대치 이상」으로 받는다.

    probe 는 멈춘 뒤 BLANK 를 부른 결과다 — 마지막 동작이 소거였으니 0xFF 를 0x00 과 대조하면
    전량(PROBE_TOTAL)이 나와야 한다. 0 이면 세는 경로가 죽은 것이고, 그때는 B 행의 0 도 못 믿는다
    (harness.check_probe 와 같은 검사, 워크플로 12 §3.3). None 은 BLANK 자체가 거부된 것."""
    cycle, state, defect_seen, _ = status
    ta, tb, mismatch = tally
    b_cycle = log.b[-1]["cycle"] if log.b else None
    ids = {h["chip_id"] for h in log.h}
    erase = [a["t_erase_us"] for a in log.a]
    seg, b_want = n - start, n // 100 - start // 100
    paths = {"카운터": cycle, "A행수÷7": start + len(log.a) / 7, "tally×100": ta}
    want = {"카운터": n, "A행수÷7": n, "tally×100": n - n % 100}   # tally 는 100마다 1바이트라 눈금이 굵다
    if b_cycle is not None:
        paths["B의 cycle"], want["B의 cycle"] = b_cycle, n
    out = [
        ("A1", cycle == n, f"카운터 {cycle} (기대 {n})"),
        ("A2", len(log.a) == seg * 7, f"A 행 {len(log.a)} (기대 {seg * 7}), 깨진 행 {len(log.rejected)}"),
        ("A3", len(log.b) >= b_want if defect_seen else len(log.b) == b_want,
         f"B 행 {len(log.b)} (기대 {b_want}" + (" 이상 — 결함 뒤 조밀화)" if defect_seen else ")")),
        ("A4", all(d.count(0) == n // 100 for d in dumps),
         "tally 0x00 " + "/".join(str(d.count(0)) for d in dumps) + f" (기대 각 {n // 100})"),
        ("A5", not mismatch and all(paths[k] == want[k] for k in paths),
         f"{paths}" + (" tally 불일치" if mismatch else "")
         + (f" · tally 기대 {want['tally×100']}" if n % 100 else "")
         + ("" if b_cycle is not None else " · 이 구간엔 검사 사이클이 없다")),
        *([("A6", bool(erase) and max(erase) < ERASE_WARN_US,
            f"t_erase_us max {max(erase) if erase else '-'} median {sorted(erase)[len(erase) // 2] if erase else '-'}"
            " (실칩에서만 뜻이 있다)")] if erase_check else []),
        ("A7", ids == {expected_uid} and uid == expected_uid,
         f"로그 chip_id {sorted(ids)} · 경계 7 {uid} · 등록부 {expected_uid}"),
        ("C", state == "checkpoint_due", f"state={state}"),
        ("probe", probe is not None and probe.erase_residual_bits == 0 and probe.program_fail_bits == PROBE_TOTAL,
         "BLANK 거부 — 세는 경로를 확인 못 했다" if probe is None else
         f"program_fail_bits {probe.program_fail_bits} (기대 {PROBE_TOTAL}) 잔류 {probe.erase_residual_bits}"
         + ("" if probe.program_fail_bits else " — 세는 경로가 죽었다, B 행의 0 을 믿지 말 것")),
    ]
    return out


def wear_area(base, n=WEAR_N):
    """장부·판정·화면에 같은 표기로 나가는 섹터 범위."""
    return f"{base}~{base + n - 1}"


def pct(values, q):
    """정렬 없이 쓸 일이 없으므로 그냥 정렬해서 백분위 — 표본이 20만이어도 한 번뿐이다."""
    if not values:
        return None
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def collect(rows, acc):
    """A 행에서 요약에 쓸 값만 뽑아 쌓는다 — 행 자체는 버린다 (33시간치를 들고 있지 않으려고).

    사이클 실소요는 사이클마다의 마지막 ts 차이다. 소거·프로그램에 실제로 걸린 시간이라 마모가
    쌓이면 늘어나고, 예상 시간 계산이 typ 0.405s 대신 이 값을 쓴다."""
    last = {}
    for r in rows:
        if "t_erase_us" in r:
            acc["erase"].append(r["t_erase_us"])
        if "t_program_us" in r:
            acc["prog"].append(r["t_program_us"])
        if "ts" in r:
            last[r["cycle"]] = max(last.get(r["cycle"], 0), r["ts"])
    ks = sorted(last)
    acc["gaps"] += [(last[b] - last[a]) / 1e6 for a, b in zip(ks, ks[1:]) if last[b] > last[a]]
    return acc


def new_acc():
    return {"erase": [], "prog": [], "gaps": []}


def summarize(acc):
    """체크포인트 1점의 요약 — 곡선의 y2(소거 시간)와 다음 구간의 예상 단가가 여기서 나온다."""
    return {"t_erase_p50": pct(acc["erase"], 0.5), "t_erase_p99": pct(acc["erase"], 0.99),
            "t_erase_max": max(acc["erase"]) if acc["erase"] else None,
            "t_program_p50": pct(acc["prog"], 0.5), "t_program_p99": pct(acc["prog"], 0.99),
            "t_program_max": max(acc["prog"]) if acc["prog"] else None,
            "cycle_s_p50": round(pct(acc["gaps"], 0.5), 4) if acc["gaps"] else None}


def measured_cycle_s(logdir, fallback=CYCLE_TYP_S):
    """직전 체크포인트들이 남긴 cycle_s_p50 중 가장 최근 값. 없으면 typ. (값, 출처 문구)."""
    for d in sorted(Path(logdir).glob("*/checkpoints.csv"), key=lambda q: q.stat().st_mtime, reverse=True):
        rows = [ln.split(",") for ln in d.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
        vals = [(float(r[14]), r[7]) for r in rows if len(r) > 14 and r[14]]
        if vals:
            return vals[-1][0], f"실측 {vals[-1][0]:.3f}s/사이클 · 세션 {vals[-1][1]}"
    return fallback, f"typ {fallback}s/사이클 — 실측 없음"


def measured_cp_s(logdir, fallback=CP_COST_S):
    """체크포인트 1점에 실제로 걸린 시간(가장 최근). 없으면 기본 2분."""
    for d in sorted(Path(logdir).glob("*/checkpoints.csv"), key=lambda q: q.stat().st_mtime, reverse=True):
        rows = [ln.split(",") for ln in d.read_text(encoding="utf-8").splitlines()[1:] if ln.strip()]
        vals = [float(r[15]) for r in rows if len(r) > 15 and r[15].strip()]
        if vals:
            return vals[-1]
    return fallback


def estimate(segs, cycle_s, cp_s):
    """예상 시간(초) = 남은 사이클 × 사이클 단가 + 남은 체크포인트 × 점당 비용."""
    return sum(d for _, d, _, _ in segs) * cycle_s + sum(1 for g in segs if g[3]) * cp_s


def split_rows(raw_lines):
    """원문 줄 목록 → {'H': [...], 'A': [...], ...} (체크섬 통과한 행만, 원문 그대로)."""
    out = {k: [] for k in hs.ROW_KINDS}
    for ln in raw_lines:
        i = ln.find(hs.PREFIX)
        if i < 0:
            continue
        row = hs.parse_row(ln[i + len(hs.PREFIX):])
        if row:
            out[row["type"]].append(ln[i:].rstrip())
    return out


def host_log_max_from(session_dir):
    """이전 세션 폴더의 A.txt 에서 A 로그 최대 cycle."""
    log = hs.WearLog()
    p = Path(session_dir) / "A.txt"
    if not p.exists():
        raise Abort(f"{p} 가 없다")
    log.feed(p.read_bytes())
    return log.max_cycle


def start_command(cycle, delta, session, base=WEAR_BASE_GROUP):
    """사람이 확인할 START 한 줄 — 보내는 것과 같은 문자열."""
    return hs.format_cmd("START", 1, base=base, n_sectors=WEAR_N, pattern=PATTERN,
                         cycle=cycle, delta=delta, session=session)


def plan_segments(cycle, to, step, confirm_first, checkpoints=()):
    """[(시작 누적, 이번 구간 사이클, 사람이 확인하나, 끝이 체크포인트인가)].

    경계는 **체크포인트**다 — 거기서 재야 곡선의 점이 생긴다. 체크포인트 사이가 step 보다 길면
    더 쪼개는데(호스트가 33시간치를 들고 있지 않도록 구간 끝마다 판정하고 파일로 흘린다) 그
    쪼갠 경계에서는 재지도 묻지도 않는다. 확인은 앞의 confirm_first 체크포인트에만 붙는다."""
    stops = sorted({c for c in checkpoints if cycle < c <= to} | {to})
    out, cur, seen = [], cycle, 0
    for stop in stops:
        is_cp = bool(checkpoints) and (stop in checkpoints or stop == to)   # 끝점도 점이다 — 거기서 잰다
        while cur < stop:
            size = min(step, stop - cur)
            if size <= 0:
                raise Abort("구간 크기가 0 이하다 — --delta 를 확인할 것")
            cur += size
            last = cur == stop
            mark = (last and is_cp) or not checkpoints       # 확인이 붙을 수 있는 경계
            out.append((cur - size, size, mark and seen < confirm_first, last and is_cp))
            seen += mark
    return out


def fmt_dur(seconds):
    return f"{seconds / 3600:.1f}시간" if seconds >= 3600 else f"{max(1, round(seconds / 60))}분"


def plan_banner(chip, uid, segs, to, base=WEAR_BASE_GROUP, mhz=25, measure=True,
                tally=None, note=None, cycle_s=CYCLE_TYP_S, src="", cp_s=CP_COST_S,
                total=None, unknown=0, wear_baud=921600, sweep_baud=921600):
    """승인 전에 사람이 읽는 계획 한 장 — 어디를·어디서부터·얼마나·어디서 재고·어디까지 사람이 보나."""
    confirm = sum(1 for g in segs if g[2])
    cps = [g[0] + g[1] for g in segs if g[3]]
    start, span = segs[0][0], to - segs[0][0]
    dur = fmt_dur(estimate(segs, cycle_s, cp_s))
    out = ["── 마모 계획 ────────────────────────────────────────────────",
           f"칩         : {chip}  UID {uid}",
           f"baud rate  : 마모 {wear_baud} · 스윕 {sweep_baud}"]
    if tally is not None:
        out.append(f"tally      : {tally:,}  (마모 사이클만 집계 · 2벌 일치)" + (f"  ⚠ {note}" if note else ""))
    if total is not None:
        out.append(f"누적 P/E   : {total:,}  ({wear_area(base)} · 장부 기준 — 마모 + prep · 체크포인트)"
                   + (f"  ⚠ 증분 미상 행 {unknown}개는 합계에서 제외" if unknown else ""))
    out += [
        f"마모 섹터  : {wear_area(base)} (7섹터 · 112페이지)",
        "보호 섹터  : 근접 대조군 7~13 · 원격 대조군 2,041~2,047 · tally 2벌 512 · 1,536 (엔진이 거부)",
        f"마모 패턴  : 0x{PATTERN:02x} (셀당 8비트가 1→0)",
        f"누적       : {start:,} → {to:,} ({span:,} 사이클 · 예상 {dur} · {src})",
    ]
    if cps:
        out.append("체크포인트 : " + f"{len(cps)}점 — " + " · ".join(f"{c:,}" for c in cps))
        out.append(f"측정 방식  : 체크포인트마다 {wear_area(base)} 소거 + PRBS 기록(P/E +1) → "
                   f"{mhz}MHz 스윕 → 분석 · plot" if measure else
                   "측정 방식  : 이번 실행은 재지 않는다 — 태우기만 한다")
    else:
        out.append("체크포인트 : 없음 — 이 자리는 곡선을 만들지 않는다 (인수 시험)")
    out += [
        f"편성       : 앞 {confirm}구간은 마모 진행 후 유인 확인, 나머지는 무인" if confirm
        else "편성       : 전 구간 무인",
        "정지       : 구간 FAIL · checkpoint_due 아님 → 자동 정지",
        "확인       : 유인 구간 끝에서 q 입력하여 정지 · 진행 시에는 enter 입력",
        "─────────────────────────────────────────────────────────────",
    ]
    return "\n".join(out)


def resolve_accept(ap, args):
    """사람이 안 준 것을 정한다 — 체크포인트와 목표. 칩이 닳는 양은 --to 만이 정한다."""
    if args.checkpoints is None:                             # 마모 그룹에만 점을 찍는다
        args.checkpoint_list = CHECKPOINTS if args.base_sector == WEAR_BASE_GROUP else ()
    elif args.checkpoints.strip().lower() == "none":
        args.checkpoint_list = ()
    else:
        try:
            args.checkpoint_list = tuple(sorted(int(x) for x in args.checkpoints.split(",")))
        except ValueError:
            ap.error("--checkpoints 는 누적값을 쉼표로 이은 것 (예: 300,600,1400) 또는 none")
    for name, vals in (("--to", [args.to] if args.to is not None else []),
                       ("--checkpoints", list(args.checkpoint_list))):
        for v in vals:
            if v % TALLY_STRIDE:
                near = v // TALLY_STRIDE * TALLY_STRIDE
                ap.error(f"{name} {v:,} — {TALLY_STRIDE} 의 배수로 준다. 칩의 tally 는 {TALLY_STRIDE} "
                         f"사이클마다 1바이트라 그 사이에서 끊으면 칩의 눈금과 호스트의 숫자가 어긋난다 "
                         f"(§13 A5). {near:,} 또는 {near + TALLY_STRIDE:,} 로 다시 친다 "
                         f"(--cycle 은 예외 — 복구 채택값이 배수가 아닐 수 있다)")


def resolve_target(ap_error, args, cycle):
    """--cycle 이 정해진 뒤에 목표를 정한다 — 기본은 마지막 체크포인트, 없으면 100사이클(인수 시험)."""
    to = args.to if args.to is not None else \
        (args.checkpoint_list[-1] if args.checkpoint_list else cycle + 100)
    if to < cycle:
        ap_error(f"--to {to:,} 는 현재 누적 {cycle:,} 보다 작을 수 없다")
    return to


def build_segments(args, cycle, to):
    return plan_segments(cycle, to, SEG_CHUNK, args.confirm_first, args.checkpoint_list) \
        or [(cycle, 0, True, False)]


# ── 세션 ──────────────────────────────────────────────────────────────────
class Run:
    def __init__(self, args):
        self.args = args
        self.session = args.session or int(time.time())
        self.dir = Path(args.logdir) / str(self.session)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.ses = Session(str(self.session))
        self.ses.path = self.dir / "session.log"
        self.ser = self.link = None

    def open(self, program=False):
        a = self.args
        if a.sim:
            env = dict(os.environ)
            if a.sim_image:
                env["WEAR_FAKE_IMAGE"] = a.sim_image
            if a.sim_state:
                env["WEAR_FAKE_STATE"] = a.sim_state
            env["WEAR_FAKE_TRACE"] = str(self.dir / "fake_trace.txt")
            self.ses.log(f"sim: {a.sim}")
            transport = wl.PipeTransport([a.sim], env=env)
        else:
            import serial
            self.ser = serial.Serial(a.port, a.wear_baud, timeout=0.5)
            reader = self.ser
            if program:
                if not WEAR_ELF.exists():
                    raise Abort(f"missing {WEAR_ELF} — vitis -s ps/scripts/build_flash_wear.py 먼저")
                self.ser.reset_input_buffer()
                pre = run_xsct([PROGRAM_G2, WEAR_ELF], self.ses, "엔진 프로그래밍 (g2_jedec + flash_wear)", ser=self.ser)
                reader = Drained(self.ser, pre)
            transport = wl.SerialTransport(self.ser, reader=reader)
        self.link = wl.WearLink(transport, timeout=a.timeout)
        return self.link

    def close(self):
        if self.link:
            self.link.close()
        if self.ser:
            self.ser.close()
        self.flush()

    def flush(self):
        """받은 원문·행을 파일에 덧붙이고 메모리를 비운다. 구간마다 부른다 — 33시간치를 들고 있지 않고,
        호스트가 죽어도 직전 구간까지는 디스크에 남는다."""
        if not self.link:
            return
        n = len(self.link.t.raw)                             # 수신 스레드가 뒤에 더 붙여도 안전하게
        raw = [r.decode(errors="replace") for r in self.link.t.raw[:n]]
        del self.link.t.raw[:n]
        with (self.dir / "raw.txt").open("a", encoding="utf-8") as f:
            f.write("".join(raw))
        for kind, rows in split_rows(raw).items():
            if rows:
                with (self.dir / f"{kind}.txt").open("a", encoding="utf-8") as f:
                    f.write("\n".join(rows) + "\n")
        with (self.dir / "commands.txt").open("a", encoding="utf-8") as f:
            f.write("\n".join(self.link.responses) + "\n")
        self.link.responses.clear()
        self.link.log = hs.WearLog()

    def close_link(self):
        """체크포인트 측정이 보드·포트를 가져가야 한다 — 흘려 쓰고 놓는다."""
        self.flush()
        if self.link:
            self.link.close()
        if self.ser:
            self.ser.close()
        self.ser = self.link = None

    def write_checkpoint(self, n, csv, summary, cp_s):
        """C 행 (S-1 §9) — 마모 경로와 측정 경로를 잇는 못. 요약까지 한 행에 둔다."""
        a = self.args
        f = self.dir / "checkpoints.csv"
        if not f.exists():
            f.write_text(CP_HEADER, encoding="utf-8")
        row = ",".join(str(x if x is not None else "") for x in [
            n, wear_area(a.base_sector), csv.name if csv else "", self.expected_uid(),
            a.base_sector, 112, a.sweep_mhz, self.session,
            summary.get("t_erase_p50"), summary.get("t_erase_p99"), summary.get("t_erase_max"),
            summary.get("t_program_p50"), summary.get("t_program_p99"), summary.get("t_program_max"),
            summary.get("cycle_s_p50"), cp_s])
        with f.open("a", encoding="utf-8") as fh:
            fh.write(row + "\n")
        self.ses.log(f"체크포인트 {n}: {row}")
        return row

    def expected_uid(self):
        uid = chip_registry.parse().get(self.args.chip)
        if not uid:
            raise Abort(f"등록부에 {self.args.chip} 의 UID 가 없다 (docs/chip_registry.md)")
        return uid

    def check_uid(self):
        """S-1 §8.3 1 · §4 1 — 등록부와 다르면 아무것도 하지 않는다."""
        want = self.expected_uid()
        got = self.link.uid_read()
        if got != want:
            raise Abort(f"UID 불일치 — 소켓 {got}, 등록부 {self.args.chip}={want}. P/E 를 내지 않는다")
        self.ses.log(f"UID OK: {got} = {self.args.chip}")
        return got

    def pe_row(self, sectors, delta, source, note=""):
        chip_pe.append_pe(datetime.now(timezone.utc).strftime("%Y-%m-%d"), self.args.chip,
                          self.expected_uid(), sectors, delta, source, note, path=self.args.chip_pe)
        self.ses.log(f"chip_pe: {self.args.chip} {sectors} {delta} — {source} {note}")


# ── 서브커맨드 ────────────────────────────────────────────────────────────
def checkpoint_measure(run, n, acc):
    """체크포인트 — 마모를 멈춘 자리를 잰다. 소거+PRBS 기록(P/E +1, 장부는 기계가) → 스윕 → 분석·plot.

    prep 은 범위 전용 ELF(`build/vitis_prep_<base>_<n>`)를 쓰고, 스윕·분석·plot 은 `run_sweep_chip.py
    --mode sweep` 을 그대로 부른다 — 측정의 정본은 그 스크립트 하나다. 실패하면 마모를 잇지 않는다.
    C 행(S-1 §9)에는 스윕 CSV 와 함께 **직전 구간의 소거 시간 요약**이 같이 들어간다 — 곡선의 두
    축(윈도우 폭 · 소거 시간)이 한 행에서 나오고, 다음 구간의 예상 단가도 여기서 읽는다."""
    a = run.args
    t0 = time.monotonic()
    elf = REPO / f"build/vitis_prep_{a.base_sector}_{WEAR_N}" / "flash_prep" / "build" / "flash_prep.elf"
    if not elf.exists():
        raise Abort(f"missing {elf.relative_to(REPO)} — 체크포인트 prep ELF 가 없다 "
                    f"(PREP_BASE={a.base_sector} PREP_N={WEAR_N} vitis -s ps/scripts/build_flash_prep.py)")
    import serial
    run.close_link()
    print(f"체크포인트 {n:,} — {wear_area(a.base_sector)} 소거 + PRBS 기록 (P/E +1)")
    with serial.Serial(a.port, a.wear_baud, timeout=2) as ser:
        uid = run_prep(ser, run.ses, elf=elf)
    if uid != run.expected_uid():
        raise Abort(f"체크포인트 prep 의 UID 가 다르다 — 소켓 {uid}, 등록부 {run.expected_uid()}")
    run.pe_row(wear_area(a.base_sector), "+1", f"run_wear checkpoint (session {run.session})",
               f"체크포인트 {n} — 소거+PRBS (측정용, 마모 카운터에는 안 센다)")
    cmd = [sys.executable, str(SWEEP_RUNNER), "--mode", "sweep", "--mhz", str(a.sweep_mhz),
           "--chip", a.chip, "--port", a.port, "--baud", str(a.sweep_baud)]
    run.ses.log("체크포인트 스윕: " + " ".join(cmd))
    print(f"체크포인트 {n:,} — {a.sweep_mhz}MHz 스윕 (약 1분)")
    if subprocess.run(cmd).returncode != 0:
        raise Abort(f"체크포인트 {n} 스윕 실패 — 마모를 잇지 않는다. 사람이 본다")
    csv = max((REPO / "build" / "data").glob("sweep_*.csv"), key=lambda q: q.stat().st_mtime, default=None)
    png = PLOT_DIR / f"bathtub_{csv.stem}.png" if csv else None
    run.write_checkpoint(n, csv, summarize(acc), round(time.monotonic() - t0, 1))
    return csv, png


def checkpoint_confirm(run, n, csv, png, left):
    """유인 체크포인트 — 사람이 볼 것 셋(판정·장부·plot)을 짚어 주고 enter 를 기다린다."""
    a = run.args
    ledger = [ln for ln in Path(a.chip_pe).read_text(encoding="utf-8").splitlines()
              if f"| {a.chip} |" in ln][-2:]
    print(f"\n체크포인트 {n:,} 확인 (남은 유인 {left}회)")
    print(f"  판정  {run.dir / 'verdict.txt'} — 이번 구간 9줄이 전부 PASS 인가")
    print("  장부  docs/chip_pe.md 마지막 두 행 — 마모 증분과 체크포인트 prep +1 이 둘 다 들어갔나 확인")
    for ln in ledger:
        print(f"        {ln}")
    print(f"  plot  {png if png else '(스윕 CSV 를 못 찾았다 — build/data 확인)'}")
    print("확인했으면 enter · 멈추려면 q")
    try:
        ans = input("> ").strip().lower()
    except EOFError:
        ans = "q"
    run.ses.log(f"체크포인트 {n} 확인: {'중단' if ans == 'q' else 'enter'}")
    return ans != "q"


def run_segment(run, link, uid, start, delta, head, acc=None):
    """구간 하나 — START → 완주 대기 → 장부 → 판정(인수 시험 9줄 · 마모 런 8줄). 전부 통과했으면 True.
    acc 를 주면 A 행의 소거·프로그램 시간과 사이클 실소요를 거기에 쌓는다 (체크포인트 요약용)."""
    base = run.args.base_sector
    cmd = start_command(start, delta, run.session, base)
    run.ses.log(f"START: {cmd}")
    print(f"START → {cmd}", file=sys.stderr)
    link.wear_start(base, WEAR_N, PATTERN, start, delta, run.session)
    status = link.wait_stopped(timeout=delta * SEC_PER_CYCLE + 60)
    run.ses.log(f"stopped: {status}")
    done = status[0] - start
    if done > 0:
        run.pe_row(wear_area(base), f"+{done}", f"run_wear accept (session {run.session})",
                   f"cycle {start}→{status[0]}" + ("" if status[1] == "checkpoint_due" else f" · {status[1]}"))
    tally = link.tally_read()
    dumps = link.tally_dump()
    try:                                                     # 시험 버튼 — 읽기 전용, 판정은 judge_accept
        probe = link.blank_check(base, WEAR_N)
    except hs.Reject as e:
        run.ses.log(f"probe BLANK 거부: {e}")
        probe = None
    if acc is not None:
        collect(link.log.a, acc)                             # 행은 곧 버려진다 — 값만 남긴다
    verdict = judge_accept(link.log, status, tally, dumps, uid, run.expected_uid(),
                           n=start + delta, start=start, probe=probe,
                           erase_check=(base == WEAR_BASE_TB))     # A6 는 인수 시험(TB 영역)에서만
    lines = [f"{'PASS' if ok else 'FAIL'}  {item:5s} {detail}" for item, ok, detail in verdict]
    if link.log.r:
        lines.append("R 행: " + " | ".join(f"{r['kind']}@{r['cycle']}" for r in link.log.r))
    with (run.dir / "verdict.txt").open("a", encoding="utf-8") as f:
        f.write(("" if head is None else head + "\n") + "\n".join(lines) + "\n")
    for ln in lines:
        run.ses.log(ln)
    print("\n".join(lines))
    return all(ok for _, ok, _ in verdict)


def parse_area(text):
    """장부의 「섹터 범위」 칸 → (lo, hi). `0~6` · `1000~1006` · `512` 를 받는다. 모르면 None."""
    t = text.replace(",", "").replace("\\", "").strip()
    try:
        if "~" in t:
            lo, hi = (int(x) for x in t.split("~", 1))
            return lo, hi
        return int(t), int(t)
    except ValueError:
        return None


def ledger_rows(path, chip):
    """그 칩의 장부 행들을 위에서 아래 순서로. 각 행은 (섹터범위, 증분, 출처, 비고)."""
    out = []
    for ln in Path(path).read_text(encoding="utf-8").splitlines():
        c = [x.strip() for x in ln.strip().strip("|").split("|")]
        if len(c) >= 7 and c[1] == chip and c[0][:2].isdigit():
            out.append((c[3], c[4], c[5], c[6]))
        elif len(c) >= 6 and c[1] == chip and c[0][:2].isdigit():
            out.append((c[3], c[4], c[5], ""))
    return out


def ledger_wear(rows):
    """**마지막 tally-erase 이후**의 마모 증분 합계와 그 영역들 — tally 와 맞대볼 값.

    tally 는 영역을 구분하지 않고 마모 루프만 센다(S-1 §8.1). 그래서 대조 상대는 「그 칩의,
    마지막 실험 개시 소거 이후의, run_wear accept 증분 합계」다 — 체크포인트 prep(+1)과 재소거(±1)는
    tally 에 들어가지 않으므로 뺀다. 반환: (합계, 영역 집합, 읽지 못한 행 수)."""
    start = 0
    for i, (_, _, src, note) in enumerate(rows):
        if "tally-erase" in src or "tally erase" in note:
            start = i + 1
    total, areas, unknown = 0, set(), 0
    for area, delta, src, _ in rows[start:]:
        if not src.startswith("run_wear accept"):
            continue
        try:
            total += int(delta.replace(",", "").lstrip("+"))
            areas.add(area)
        except ValueError:
            unknown += 1
    return total, areas, unknown


def ledger_area_total(rows, base, n):
    """그 **영역이 실제로 받은 P/E 합**(마모 + prep + 체크포인트) — 범위가 겹치는 행을 다 센다.
    곡선 x축의 진짜 값이다. `미상`·`(봉인)`·`±1` 처럼 값을 모르는 행은 세지 않고 개수만 돌려준다."""
    total, unknown = 0, 0
    for area, delta, _, _ in rows:
        rng = parse_area(area)
        if not rng or rng[1] < base or rng[0] > base + n - 1:
            continue                                         # 겹치지 않는 영역
        try:
            total += int(delta.replace(",", "").lstrip("+"))
        except ValueError:
            unknown += 1
    return total, unknown


def ledger_correction(cycle, tally, wear):
    """START 전에 장부에 덧붙일 보정 증분. 장부가 tally 눈금 밖(A 로그·resume 채택값)까지 못 따라온 만큼만이다.

    호스트가 먼저 죽어 마지막 구간 행이 안 적힌 경우(장부 300 · tally 300 · 채택값 337)에는 +37 이 맞다.
    엔진이 error 로 서서 구간 행(+done)이 이미 적힌 경우(장부 122,164 · tally 122,100 · 채택값 122,164)에는
    0 이어야 한다 — tally 와 비교하면 +64 를 이중으로 적는다 (2026-09-24 chip01 재개에서 발견).
    장부를 못 읽었으면(wear=None) tally 가 유일한 기준이다."""
    base = tally if wear is None else max(wear, tally)
    return cycle - base if cycle > base else 0


def start_cycle(run, link):
    """어디서부터 세나 — 그리고 칩과 장부가 같은 이야기를 하는지 본다.

    ① tally 두 벌이 어긋나면 중단 (§8.2 병합은 resume 의 일이다)
    ② **tally ≤ 장부의 마모 합계 < tally+100** 이어야 한다. tally 는 100 눈금이고 장부는 1 눈금이라
       같음이 아니라 창이며, 이 창은 엔진의 `E_CYCLE` 창과 같다
    ③ 그 합계에 **다른 영역**이 섞여 있으면 중단 — tally 는 영역을 구분하지 않으므로 x축이 밀린다.
       새 실험이면 `tally-erase` 로 0 부터 시작하는 것이 S-1 §8.1 의 「실험 개시 소거」다

    반환: (시작 누적, tally, 누적 P/E, 계획에 띄울 덧말)"""
    a = run.args
    ta, tb, mismatch = link.tally_read()
    if mismatch:
        raise Abort(f"tally 두 벌이 어긋난다 (a={ta:,} b={tb:,}) — 자동으로 쓰지 않는다. "
                    f"resume 으로 판정하거나 --cycle 로 명시할 것")
    area, note = wear_area(a.base_sector), []
    try:
        rows = ledger_rows(a.chip_pe, a.chip)
    except OSError:
        rows = None
    total = unknown = None
    wear = None
    if rows is not None:
        wear, areas, bad = ledger_wear(rows)
        total, unknown = ledger_area_total(rows, a.base_sector, WEAR_N)
        if bad:
            note.append(f"장부에 읽지 못한 마모 행 {bad}개 — 대조를 못 했다")
            wear = None
        elif areas - {area}:
            raise Abort(
                f"tally {ta:,} 에 **다른 영역**의 마모가 섞여 있다 (장부: {' · '.join(sorted(areas))}).\n"
                f"  tally 는 영역을 구분하지 않으므로 이대로 {area} 를 태우면 x축이 {ta:,} 만큼 밀린다.\n"
                f"  ① 새 실험이면 → tally-erase 로 x축을 0 부터 (S-1 §8.1 실험 개시 소거)\n"
                f"  ② 그 영역을 이어 태우는 것이면 → --base-sector 를 그 영역으로")
        elif not (ta <= wear < ta + TALLY_STRIDE):
            raise Abort(
                f"칩과 장부가 다른 이야기를 한다 — tally {ta:,} · 장부의 마모 합계 {wear:,} "
                f"(창 {ta:,}~{ta + TALLY_STRIDE - 1:,} 를 벗어난다)\n"
                f"  ① 장부가 빠진 것이면 → docs/chip_pe.md 에 정정 행을 덧붙여 맞춘 뒤 다시\n"
                f"  ② resume 이 준 채택값으로 이어야 하면 → --cycle <값> "
                f"(엔진은 {ta:,}~{ta + TALLY_STRIDE - 1:,} 만 받는다)\n"
                f"  ③ 새 실험이면 → tally-erase 로 x축을 0 부터")
        elif wear != ta:
            note.append(f"장부 {wear:,} (tally 눈금 밖 {wear - ta} 사이클 — A 로그 기준)")
    if a.cycle is not None:
        if a.cycle != ta:
            note.append(f"--cycle {a.cycle:,} 로 덮었다")
        return a.cycle, ta, wear, total, unknown, " · ".join(note) or None
    return ta, ta, wear, total, unknown, " · ".join(note) or None


def cmd_accept(run):
    a = run.args
    link = run.open(program=not a.no_program)
    status = link.wear_status()
    run.ses.log(f"boot: {status}")
    if status[1] == "error":
        raise Abort("엔진이 error 로 부팅했다 (SPI/JEDEC/UID) — 배선·칩 확인. START 를 보내지 않는다")
    if status[1] == "running":
        raise Abort("엔진이 running 이다 — halt 로 세우거나 끝나기를 기다릴 것")
    uid = run.check_uid()
    cycle, tally, wear, total, unknown, note = start_cycle(run, link)
    cycle_s, src = measured_cycle_s(a.logdir)
    cp_s = measured_cp_s(a.logdir)

    ap = build_parser()                                      # 계획 화면에서 옵션을 고쳐 다시 파싱한다
    while True:
        to = resolve_target(lambda m: print(f"  ⚠ {m}", file=sys.stderr), a, cycle)
        segs = build_segments(a, cycle, to)
        banner = plan_banner(a.chip, uid, segs, to, a.base_sector, a.sweep_mhz,
                             a.measure and not a.sim, tally, note, cycle_s, src, cp_s, total, unknown,
                             a.wear_baud, a.sweep_baud)
        print(banner)
        if a.sim or a.i_approve_real_pe:                     # 비대화형·연습은 확인 화면을 건너뛴다
            break
        print("진행 enter · 고칠 옵션 입력 (예: --to 100000 --confirm-first 3) · 취소 q")
        try:
            typed = input("> ").strip()
        except EOFError:
            typed = "q"
        if not typed:
            break
        if typed.lower() == "q":
            raise Abort("사람이 계획을 승인하지 않았다 — START 를 보내지 않는다")
        try:
            new = ap.parse_args(list(a.argv) + shlex.split(typed))
            resolve_accept(ap, new)
        except SystemExit:                                   # 잘못 친 옵션 — 계획을 다시 보인다
            continue
        new.argv, new.chip_pe, new.logdir = a.argv, a.chip_pe, a.logdir
        run.args = a = new
        if a.cycle is not None:
            cycle = a.cycle
    (run.dir / "plan.txt").write_text(banner + "\n", encoding="utf-8")
    for ln in banner.splitlines():
        run.ses.log(ln)
    fix = ledger_correction(cycle, tally, wear)              # 장부가 못 따라온 만큼만 — 이미 적힌 구간 행은 다시 안 센다
    if fix:                                                  # (cycle < tally 는 적지 않는다 — 엔진이 E_DIRTY·E_CYCLE 로 막을 자리이고, 장부를 먼저 더럽히면 안 된다)
        run.pe_row(wear_area(a.base_sector), f"+{fix}",
                   f"run_wear accept (session {run.session})",
                   f"cycle 보정: 장부 {cycle - fix} → 시작 {cycle} (A 로그·resume 채택값 기준)")

    left, acc, rc = sum(1 for g in segs if g[2]), new_acc(), 0
    for i, (start, delta, confirm, is_cp) in enumerate(segs, 1):
        n = start + delta
        head = (f"[구간 {i}/{len(segs)}] 누적 {start:,} → {n:,} · {delta:,} 사이클 · "
                f"예상 {fmt_dur(delta * cycle_s)} · 섹터 {wear_area(a.base_sector)}")
        print(head)
        run.ses.log(head)
        if not run_segment(run, link, uid, start, delta, head if len(segs) > 1 else None, acc):
            print("이 구간이 FAIL 로 끝났다 — 다음 구간을 시작하지 않는다. 사람이 본다")
            run.ses.log("구간 FAIL — 여기서 멈춘다")
            rc = 1
            break
        run.flush()                                          # 구간 끝 = 파일로 흘리고 메모리를 비우는 자리
        csv = png = None
        if is_cp and a.measure and not a.sim:
            csv, png = checkpoint_measure(run, n, acc)        # 보드를 가져갔다 돌려준다
            link = run.open(program=True)
            if link.wear_status()[1] == "error":
                raise Abort("측정 뒤 엔진이 error 로 부팅했다 — 배선·칩 확인")
            run.check_uid()
        elif is_cp:
            why = "sim" if a.sim else "--no-measure"
            print(f"체크포인트 {n:,} — 측정을 건너뛴다 ({why})")
            run.ses.log(f"체크포인트 {n} 측정 생략 ({why})")
        if is_cp:
            s = summarize(acc)
            if csv is None:                                  # 안 쟀어도 소거 시간 곡선은 남긴다
                run.write_checkpoint(n, None, s, "")
            if s.get("cycle_s_p50"):
                cycle_s, src = s["cycle_s_p50"], f"실측 {s['cycle_s_p50']:.3f}s/사이클"
            print(f"  소거 p50 {s.get('t_erase_p50')}µs · p99 {s.get('t_erase_p99')}µs · "
                  f"max {s.get('t_erase_max')}µs   쓰기 p50 {s.get('t_program_p50')}µs · "
                  f"p99 {s.get('t_program_p99')}µs · max {s.get('t_program_max')}µs   "
                  f"사이클 {s.get('cycle_s_p50')}s")
            acc = new_acc()
        if confirm and i < len(segs):
            if not checkpoint_confirm(run, n, csv, png, left):
                print(f"사람이 멈췄다 — 누적 {n:,}. 이어 가려면 --cycle {n} 으로 다시")
                break
            left -= 1
            if left == 0:
                print(f"유인 확인 종료 — 여기부터 {to:,} 까지 무인 실행")
    print(f"세션 로그: {run.dir}")
    return rc


def cmd_resume(run):
    a = run.args
    if a.host_log_max is None and not a.from_session:
        raise Abort("--host-log-max N 또는 --from-session <이전 세션 폴더> 가 필요하다 (A 로그의 최대 cycle)")
    host_max = a.host_log_max if a.host_log_max is not None else host_log_max_from(a.from_session)
    link = run.open(program=not a.no_program)
    if link.wear_status()[1] == "running":
        raise Abort("엔진이 running 이다 — halt 로 세울 것")
    run.check_uid()                                                       # §8.3 1
    info = link.wear_resume()                                             # §8.3 2 — recovering
    verdict, restored = hs.decide_resume(info, host_max)                  # §8.3 3·4
    out = [f"마모 섹터 {wear_area(a.base_sector)} ({AREA_NAME.get(a.base_sector, '사람이 지정')})",
           f"tally_a={info.tally_a} tally_b={info.tally_b} mismatch={info.mismatch} "
           f"next_byte={info.next_byte} write_ok={info.write_ok} host_log_max={host_max}",
           f"판정 {verdict} 채택값 {restored}"]
    if restored is None:
        out.append("사람을 부른다 — START 를 보내지 않는다")
    else:
        bc = link.blank_check(a.base_sector, WEAR_N)                              # §8.3 5
        out.append(f"blank_check 잔류 {bc.erase_residual_bits} program_fail {bc.program_fail_bits} "
                   f"addr_count {bc.addr_count} worst_page {bc.worst_page_idx}/{bc.worst_page_bits}")
        if bc.erase_residual_bits:
            rr = link.reerase(a.base_sector, WEAR_N, timeout=a.timeout + 30)
            after = link.blank_check(a.base_sector, WEAR_N)
            sectors = sorted({r["sector"] for r in link.log.r if r["kind"] == "reerase"})
            out.append(f"reerase ok={rr.ok} t_erase_us={rr.t_erase_us} resid_after={rr.resid_after} "
                       f"섹터 {sectors} → 재확인 잔류 {after.erase_residual_bits}")
            for s in sectors:
                run.pe_row(str(s), "±1", f"run_wear resume (session {run.session})", "reerase · ±1")
            if not rr.ok or after.erase_residual_bits:
                out.append("재소거 뒤에도 잔류 — 사람을 부른다. START 를 보내지 않는다")
                restored = None
        if restored is not None:
            out.append(f"다음 명령 (사람이 친다): run_wear.py accept --chip {a.chip} --base-sector {a.base_sector} "
                       f"--cycle {restored} --delta <n> --i-approve-real-pe")
    (run.dir / "resume.txt").write_text("\n".join(out) + "\n")
    for ln in out:
        run.ses.log(ln)
    print("\n".join(out))
    return 0 if restored is not None else 2


def cmd_tally_erase(run):
    """tally 두 벌(512·1,536) 소거 — 같은 칩으로 0 부터 다시 시작할 때. 자물쇠 셋:
    ① --i-approve-tally-erase ② 사람이 그 칩의 UID 를 직접 타이핑 ③ 지우기 전 값을 chip_pe.md 에 먼저 적는다
    (장부 기입이 실패하면 소거를 보내지 않는다). 엔진 쪽 자물쇠(idle · UID 대조)는 flash_wear.c."""
    a = run.args
    if not a.sim and not a.i_approve_tally_erase:
        raise Abort("tally 를 지운다 — --i-approve-tally-erase 를 명시해야 한다 (--sim 은 예외)")
    link = run.open(program=not a.no_program)
    status = link.wear_status()
    run.ses.log(f"boot: {status}")
    if status[1] != "idle":
        raise Abort(f"엔진이 {status[1]} 이다 — TALLY_ERASE 는 idle(부팅 직후)에서만. 리셋 뒤 다시")
    uid = run.check_uid()
    ta, tb, m = link.tally_read()
    ledger = [ln for ln in Path(a.chip_pe).read_text(encoding="utf-8").splitlines() if f"| {a.chip} |" in ln]
    print(f"칩 {a.chip} uid={uid}")
    print(f"지울 tally: a={ta // 100} b={tb // 100} 바이트 (사이클 {ta}/{tb}){' · 두 벌 불일치' if m else ''}")
    print(f"chip_pe.md 의 {a.chip} 이력 (최근 5행):")
    print("\n".join(ledger[-5:]) or "(없음)")
    print("tally 두 벌(512·1,536)을 소거한다 — 칩이 스스로 기억하는 마모 눈금이 지워진다.")
    print("진행하려면 이 칩의 UID 를 그대로 입력 (다르면 지우지 않는다):")
    try:
        typed = input("UID> ").strip().upper()
    except EOFError:
        typed = ""
    if typed != uid:
        raise Abort(f"입력 {typed or '(빈 값)'} ≠ 소켓 {uid} — 지우지 않는다")
    for s in (512, 1536):                                            # ③ 장부가 먼저 — 칩의 기억을 옮긴다
        run.pe_row(str(s), "+1", f"run_wear tally-erase (session {run.session})",
                   f"tally erase · 지운 값 a={ta // 100} b={tb // 100}")
    r = link.tally_erase(uid)
    line = (f"tally 소거: 지운 값 a={r.count_a // 100} b={r.count_b // 100} t_erase_us={r.t_erase_us} "
            f"clean={int(r.clean)}" + ("" if r.clean else " — 소거 뒤에도 0xFF 가 아니다, 엔진은 error 로 앉았다"))
    run.ses.log(line)
    print(line)
    return 0 if r.clean else 1


def cmd_simple(run):
    a = run.args
    link = run.open()
    if a.cmd == "status":
        c, s, d, lr = link.wear_status()
        print(f"cycle={c} state={s} defect_seen={int(d)} last_reject={lr}")
    elif a.cmd == "halt":
        link.halt()                                                       # OK 는 다음 사이클 경계에서 온다
        c, s, _, _ = link.wait_stopped(timeout=60)
        print(f"halted: cycle={c} state={s}  → 이어 가려면 accept --cycle {c} --delta <n>")
    elif a.cmd == "tally":
        ta, tb, m = link.tally_read()
        print(f"tally_a={ta // 100} tally_b={tb // 100} (바이트) mismatch={int(m)} → 사이클 {ta}/{tb}")
    elif a.cmd == "dump":
        for i, d in enumerate(link.tally_dump()):
            p = run.dir / f"tally_{i}.hex"
            p.write_text(d.hex())
            odd = {b for b in d if b not in (0x00, 0xFF)}
            print(f"copy {i}: 0x00 {d.count(0)}개, 0x00/0xFF 외 값 {sorted(odd)} → {p}")
    elif a.cmd == "uid":
        uid = link.uid_read()
        print(f"uid={uid} 등록부={chip_registry.label_for(uid) or '(없음)'}")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("cmd", choices=("accept", "status", "halt", "resume", "tally", "dump", "uid", "tally-erase"),
                    help="accept = 계획을 승인하고 마모를 돌린다 (인수 시험도 같은 명령 — --base-sector 1000)")
    link = ap.add_argument_group("링크")
    link.add_argument("--port", default="/dev/ttyUSB1", help="Windows 는 COM<N>")
    link.add_argument("--wear-baud", type=int, default=921600,
                      help="마모 링크 + 체크포인트 prep — 호스트 포트와 펌웨어 양쪽 (UART_BAUD 로 xsct 에 전달)")
    link.add_argument("--sweep-baud", type=int, default=921600,
                      help="체크포인트 스윕만 — run_sweep_chip.py --baud 로 넘긴다. 921600 스윕에서 행이 빠지는 PC 는 115200")
    link.add_argument("--sim", metavar="BIN", help="호스트 시뮬레이션 바이너리 (build/sim/flash_wear_sim) — 실칩 대신")
    link.add_argument("--sim-image", help="fake NOR 초기 이미지 (테스트용)")
    link.add_argument("--sim-state", help="fake NOR 상태 파일 (테스트용)")
    link.add_argument("--timeout", type=float, default=wl.CMD_TIMEOUT_S, help="명령 응답 대기 초")
    ap.add_argument("--no-program", action="store_true", help="accept/resume 에서 xsct 프로그래밍 생략")
    ap.add_argument("--chip", metavar="chipNN",
                    help="등록부 라벨 — UID 대조. accept·resume·tally-erase 는 필수 (기본값을 두지 않는다 — "
                         "소켓에 chip01 이 꽂힌 채 --chip 을 빼먹으면 기본값과 UID 가 우연히 맞아 통과했다)")
    ap.add_argument("--base-sector", type=int, default=WEAR_BASE_GROUP, metavar="N",
                    help=f"태울 자리(7섹터의 시작). {WEAR_BASE_GROUP} = 마모 그룹 0~6 (S-1 §2, 기본 — "
                         f"본 실험도 같은 자리) · {WEAR_BASE_TB} = TB 전용 (S-4 §9, 인수 시험). 대조군"
                         "(7~13·2,041~)과 tally(512·1,536)는 엔진이 거부한다. accept·resume 이 같은 값을 써야 한다")
    ap.add_argument("--session", type=int, help="세션 id (UTC epoch 초). 생략하면 지금")
    ap.add_argument("--logdir", default=str(LOG_ROOT))
    ap.add_argument("--chip-pe", default=str(chip_pe.CHIP_PE), help="증분 기입 파일 (기본 docs/chip_pe.md)")
    acc = ap.add_argument_group("accept")
    acc.add_argument("--cycle", type=int, metavar="N",
                     help="어디서부터인가. 안 주면 **칩의 tally**(누적의 정본)를 읽어 쓴다. "
                          "복구 뒤에는 resume 이 준 채택값을 명시한다")
    acc.add_argument("--to", type=int, metavar="N",
                     help=f"여기까지 누적으로 태운다. 기본은 마지막 체크포인트({CHECKPOINTS[-1]:,}), "
                          "체크포인트가 없으면(TB) 100사이클")
    acc.add_argument("--confirm-first", type=int, default=1, metavar="K",
                     help="앞의 K 체크포인트에서 사람이 확인한다 (enter 로 계속 · q 로 정지). "
                          "K 번 치고 나면 그 뒤는 무인. 기본 1")
    acc.add_argument("--checkpoints", metavar="목록",
                     help=f"체크포인트 누적값을 쉼표로. 기본은 --base-sector {WEAR_BASE_GROUP} 이면 고정 "
                          f"{len(CHECKPOINTS)}점, TB 면 없음. 'none' 이면 끄고 --to 까지 쭉 간다")
    acc.add_argument("--sweep-mhz", type=int, default=25, choices=(25, 45, 75),
                     help="체크포인트 스윕의 SPI 클럭 (S-1 §3 은 25MHz 고정). 마모 속도와는 무관하다")
    acc.add_argument("--no-measure", dest="measure", action="store_false",
                     help="체크포인트에서 재지 않고 태우기만 한다 (prep·스윕 생략)")
    acc.add_argument("--i-approve-real-pe", action="store_true",
                     help="계획 확인 화면을 건너뛴다 — 비대화형(스크립트)에서 실칩에 P/E 를 낼 때 필요")
    te = ap.add_argument_group("tally-erase")
    te.add_argument("--i-approve-tally-erase", action="store_true",
                    help="tally 두 벌 소거를 승인한다 — 그래도 UID 를 직접 타이핑해야 지운다")
    res = ap.add_argument_group("resume")
    res.add_argument("--host-log-max", type=int, help="호스트 A 로그의 최대 cycle")
    res.add_argument("--from-session", help="이전 세션 폴더 — A.txt 에서 최대 cycle 을 읽는다")
    return ap


def main(argv=None):
    ap = build_parser()
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:                                             # 명령 없이 친 사람에게 usage 대신 길을 준다
        print("run_wear.py: 명령이 필요하다. 흔한 것:\n"
              "  accept --chip chipNN      마모 — 계획을 띄우고 enter 를 기다린다\n"
              "  uid · tally · status      읽기 전용 — 소켓의 칩과 누적 확인 (P/E 0)\n"
              "  resume --from-session …   전원이 나갔다 온 뒤 채택값 계산\n"
              "전체 목록은 --help, 명령 정본은 docs/commands.md §3", file=sys.stderr)
        return 2
    args = ap.parse_args(argv)
    args.argv = argv
    os.environ["UART_BAUD"] = str(args.wear_baud)           # program_g2.tcl 이 마모·prep ELF 의 g_uart_baud 를 이 값으로 덮어쓴다
                                                             # (스윕은 run_sweep_chip.py 자식이 --baud 로 자기 값을 다시 넣는다)
    if args.sim and args.cmd in ("accept", "resume", "tally-erase") \
            and Path(args.chip_pe).resolve() == chip_pe.CHIP_PE.resolve():
        ap.error("--sim 연습은 임시 장부로 한다 — cp docs/chip_pe.md /tmp/practice_pe.md 뒤 "
                 "--chip-pe /tmp/practice_pe.md 를 줄 것. 연습은 P/E 를 내지 않으므로 "
                 "진짜 이력에 행이 붙으면 그 행이 거짓이 되고, tally 대조가 그것을 세어 "
                 "다음 실칩 실행을 막는다")
    if args.cmd in ("accept", "resume", "tally-erase") and not args.chip:
        ap.error(f"{args.cmd} 는 --chip 이 필수다 — 어느 칩을 태울지는 사람이 선언하고 기계가 UID 로 검증한다. "
                 "소켓의 칩은 run_wear.py uid 로 확인")
    if args.cmd == "accept":
        resolve_accept(ap, args)
        if not args.sim and not args.i_approve_real_pe and not sys.stdin.isatty():
            print("중단: 실칩에 P/E 를 낸다 — 계획을 확인할 사람이 없으면 "
                  "--i-approve-real-pe 를 명시해야 한다", file=sys.stderr)
            return 3
    if args.cmd in ("accept", "tally-erase") and not args.sim and not args.no_program:
        require_tty(f"실칩 {args.cmd} 는 사람이 보는 자리에서")
    run = Run(args)
    try:
        rc = {"accept": cmd_accept, "resume": cmd_resume, "tally-erase": cmd_tally_erase}.get(args.cmd, cmd_simple)(run)
    except (Abort, hs.Reject, TimeoutError, ConnectionError) as e:
        run.ses.log(str(e))
        print(f"중단: {e}", file=sys.stderr)
        rc = 3
    finally:
        run.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
