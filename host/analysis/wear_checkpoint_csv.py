# wear_checkpoint_csv.py — 상온 마모 런 → 칩별 체크포인트 CSV (docs/results/data/wear/wear_endurance_<chip>_*.csv 와 같은 열)
#
# 사용: uv run python host/analysis/wear_checkpoint_csv.py --chip chip12 data/wear/1790852877 data/wear/1790880923
#
# 입력: run_wear 세션 폴더(들) — checkpoints.csv(C 행) · plan.txt(체크포인트 격자) · A.txt(빈 C 행 재계산)
#       data/session_<chip>_*.log — 모드·클럭·batch · VALID 스윕 · #PREP ERASE/PROGRAM (섹터별)
#       data/sweep_<chip>_*.analysis.json — 폭 3종 · 바닥
# 행 (시간 순으로 이 다섯 가지):
#   x=0       첫 마모 세션 전의 prep 세션(newchip) — 소거 128섹터 중앙값이 집계표 §1 과 같은 것, 없으면 마지막 것
#   마모 전    x=0 뒤 · 마모 전의 25MHz 아닌 스윕 = 클럭 사다리 (25MHz 스윕은 x=0 이 맡으므로 넣지 않고 화면에 알린다)
#   체크포인트  C 행. 소거·프로그램이 비면(휴지 뒤 잰 점) 직전 체크포인트 다음부터 그 점까지의 A 행을 run_wear.summarize 로
#   결측       plan.txt 격자에 있고 마지막 체크포인트보다 앞인데 C 행이 없는 점 — 수치 칸은 비운다
#   마모 뒤    마지막 체크포인트 뒤의 스윕(사다리·반복)과 newchip. newchip 소거·프로그램 = prep 의 마모 섹터 0-6 중앙값
#   그 밖에 마모 중 C 행에 없는 스윕(수기 체크포인트·복구 점)은 cycle 을 비워 넣는다 — 사람이 채운다
# 출력: build/data/wear_endurance_<chip>.csv. note 열은 행 종류만 적는다 — 사건·장착 사유는 사람이 덧붙인다

import argparse
import csv
import glob
import json
import re
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "host" / "tests"))
sys.path.insert(0, str(REPO / "host" / "run"))
import host_side as hs                                      # noqa: E402
import run_wear                                             # noqa: E402

FIELDS = ["cycle", "mhz", "width_1e2_ps", "width_1e3_ps", "width_1e4_ps", "floor_ber", "erase_us_p50", "erase_us_p99",
          "erase_us_max", "program_us_p50", "program_us_p99", "program_us_max", "sweep_batch", "wear_session", "note"]
SURVEY = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"
WEAR_SECTORS = range(7)                                     # 마모 그룹 0-6 (S-1 §2)


def utc(stamp):
    return datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)


def read_session_log(path):
    """세션 로그 한 개 → dict(batch, t, mode, mhz, sweep, erase{섹터: us}, program{섹터: us}). VALID 스윕이 없으면 None."""
    txt = Path(path).read_text(encoding="utf-8", errors="replace")
    v = re.search(r"\bVALID (sweep_\S+\.csv)", txt)         # \b — 「INVALID sweep_…_invalid.csv」(무효 런)는 잡지 않는다
    if not v:
        return None
    batch = Path(path).stem.rsplit("_", 1)[1]
    h = re.search(r"mode=(\w+) chip=\S+ mhz=(\d+)", txt)
    mhz = int(h[2]) if h else int(re.search(r"== running \((\d+) MHz\)", txt)[1])
    erase = {int(s): int(u) for s, u in re.findall(r"#PREP ERASE (\d+) (\d+)\s*$", txt, re.M)}
    prog = {int(s): int(u) for s, u in re.findall(r"#PREP PROGRAM (\d+) (\d+)\s*$", txt, re.M)}
    mode = h[1] if h else ("newchip" if erase else "sweep")
    return {"batch": batch, "t": utc(batch), "mode": mode, "mhz": mhz, "sweep": v[1], "erase": erase, "program": prog}


def survey_erase(chip):
    with SURVEY.open(newline="", encoding="utf-8") as f:
        v = [r["erase_us_median"] for r in csv.DictReader(f) if r["label"] == chip and r["erase_us_median"]]
    return int(v[-1]) if v else None


def widths(datadir, sweep_csv, warn=print):
    p = Path(datadir) / sweep_csv.replace(".csv", ".analysis.json")
    if not p.exists():
        warn(f"{p.name} 없음 — 폭을 비운다. uv run python host/analysis/bathtub_analysis.py --json {Path(datadir) / sweep_csv}")
        return {}
    a = json.loads(p.read_text())
    return {"width_1e2_ps": a.get("width_ps@0.01"), "width_1e3_ps": a.get("width_ps@0.001"),
            "width_1e4_ps": a.get("width_ps@0.0001"), "floor_ber": a.get("floor_ber")}


def plan_grid(sdir):
    p = Path(sdir) / "plan.txt"
    m = re.search(r"체크포인트 : \d+점 — (.+)", p.read_text(encoding="utf-8")) if p.exists() else None
    return [int(x.replace(",", "")) for x in m[1].split(" · ")] if m else []


def recompute(sessions, lo, hi):
    """A 행 lo < cycle <= hi → run_wear.summarize. 뒤 세션이 같은 (cycle, sector) 를 덮는다 (wear_curves.py 와 같은 규칙)."""
    rows = {}
    for d in sessions:
        p = Path(d) / "A.txt"
        if not p.exists():
            continue
        for line in p.open(encoding="utf-8", errors="replace"):
            i = line.find(hs.PREFIX)
            r = hs.parse_row(line[i + len(hs.PREFIX):]) if i >= 0 else None
            if r and r["type"] == "A" and lo < r["cycle"] <= hi:
                rows[(r["cycle"], r["sector"])] = r
    return run_wear.summarize(run_wear.collect(rows.values(), run_wear.new_acc()))


def med(d, keys=None):
    v = [d[k] for k in (keys if keys is not None else d) if k in d]
    return round(statistics.median(v)) if v else None          # 집계표(prep_survey_parse.py)와 같은 반올림


def fmt(v):
    return f"{v:.2f}" if isinstance(v, float) and v != 0.0 else v


def session_logs(chip, datadir):
    return [s for s in (read_session_log(p) for p in sorted(glob.glob(str(Path(datadir) / f"session_{chip}_*.log")))) if s]


def pick_x0(chip, pre, warn=print):
    """마모 전 세션 로그 → x=0 세션. prep 이 있는 것 중 집계표 §1 신품값과 같은 것, 없으면 마지막 것. 없으면 None."""
    x0 = [s for s in pre if s["erase"]]
    if not x0:
        return None
    fresh = survey_erase(chip)
    same = [s for s in x0 if med(s["erase"]) == fresh]
    if same:
        return same[-1]
    if len(x0) > 1:
        warn(f"x=0: 집계표 신품값 {fresh} 와 같은 prep 이 없다 — 마지막 newchip {x0[-1]['batch']} 를 쓴다")
    return x0[-1]


def build(chip, sessions, datadir, warn=print):
    logs = session_logs(chip, datadir)
    by_sweep = {s["sweep"]: s for s in logs}
    wear_start = datetime.fromtimestamp(int(Path(sessions[0]).name), timezone.utc)

    ck, grid = {}, {}
    for sdir in sessions:
        p = Path(sdir) / "checkpoints.csv"
        if p.exists():
            for r in csv.DictReader(p.open(newline="", encoding="utf-8")):
                ck[int(r["cycle"])] = r
        for c in plan_grid(sdir):
            grid[c] = Path(sdir).name                       # 그 점을 계획에 둔 마지막 세션 — 놓친 세션
    if not ck:
        raise SystemExit("C 행이 없다 — 세션 폴더를 확인")
    last = max(ck)
    last_t = by_sweep[ck[last]["sweep_csv"]]["t"] if ck[last]["sweep_csv"] in by_sweep else wear_start

    rows = []
    pre = [s for s in logs if s["t"] < wear_start]
    s = pick_x0(chip, pre, warn)
    if s:
        rows.append({"cycle": 0, "mhz": s["mhz"], **widths(datadir, s["sweep"], warn), "erase_us_p50": med(s["erase"]),
                     "sweep_batch": s["batch"], "note": f"x=0 신품 — newchip prep 소거 n={len(s['erase'])}"})
        for s2 in pre:
            if s2["t"] <= s["t"]:
                continue
            if s2["mhz"] == 25:
                warn(f"제외: {s2['batch']} — 마모 전 25MHz 스윕 (x=0 은 {s['batch']})")
                continue
            rows.append({"cycle": 0, "mhz": s2["mhz"], **widths(datadir, s2["sweep"], warn), "sweep_batch": s2["batch"],
                         "note": "마모 전 클럭 사다리 (--mode sweep, P/E 0)"})
    else:
        warn("x=0 없음 — 마모 전 prep 세션 로그가 data/ 에 없다")

    prev = 0
    for c in sorted(set(ck) | {g for g in grid if g < last}):
        if c not in ck:
            rows.append({"cycle": c, "mhz": 25, "wear_session": grid[c], "note": "결측 — plan 격자에 있으나 C 행 없음"})
            continue
        r = ck[c]
        s = by_sweep.get(r["sweep_csv"])
        if s is None:
            warn(f"체크포인트 {c}: {r['sweep_csv']} 의 세션 로그가 data/ 에 없다 — 폭·batch 를 비운다")
        t = {k: r[k] for k in ("t_erase_p50", "t_erase_p99", "t_erase_max", "t_program_p50", "t_program_p99", "t_program_max")}
        note = ""
        if not r["t_erase_p50"]:
            t = recompute(sessions, prev, c)
            note = f"소거·프로그램은 A 행 {prev + 1:,}-{c:,} 에서 run_wear.summarize 로 계산 (C 행이 비어 있음)"
        if r.get("measured") and r["measured"] != "직후":    # 「휴지 뒤」 — 한눈 표 그림이 이 머리말로 속 빈 점을 찍는다
            note = f"{r['measured']} — {note}" if note else r["measured"]
        rows.append({"cycle": c, "mhz": int(r["mhz"]), **(widths(datadir, r["sweep_csv"], warn) if s else {}),
                     **{k.replace("t_erase", "erase_us").replace("t_program", "program_us"): v for k, v in t.items()},
                     "sweep_batch": s["batch"] if s else "", "wear_session": r["session"], "note": note})
        prev = c

    used = {r["sweep_csv"] for r in ck.values()}
    for s in logs:
        if s["t"] < wear_start or s["sweep"] in used:
            continue
        if s["t"] < last_t:
            rows.append({"cycle": "", "mhz": s["mhz"], **widths(datadir, s["sweep"], warn), "sweep_batch": s["batch"],
                         "note": "마모 중 C 행에 없는 스윕 (수기 체크포인트·복구 점?) — cycle 은 사람이 채운다"})
        elif s["erase"]:
            rows.append({"cycle": last, "mhz": s["mhz"], **widths(datadir, s["sweep"], warn),
                         "erase_us_p50": med(s["erase"], WEAR_SECTORS), "program_us_p50": med(s["program"], WEAR_SECTORS),
                         "sweep_batch": s["batch"],
                         "note": "마모 뒤 newchip (prep 0-127 +1 → 스윕) — 소거·프로그램은 prep 의 마모 섹터 0-6 중앙값"})
        else:
            rows.append({"cycle": last, "mhz": s["mhz"], **widths(datadir, s["sweep"], warn), "sweep_batch": s["batch"],
                         "note": "마모 뒤 스윕 (--mode sweep, P/E 0)"})
    return [{k: fmt(r.get(k)) if r.get(k) is not None else "" for k in FIELDS} for r in rows]


def main(argv=None):
    ap = argparse.ArgumentParser(description="상온 마모 런 → 칩별 체크포인트 CSV")
    ap.add_argument("sessions", nargs="+", help="run_wear 세션 폴더 (checkpoints.csv 가 있는 곳), 시간 순")
    ap.add_argument("--chip", required=True)
    ap.add_argument("--data", default=str(REPO / "data"), help="세션 로그 · 스윕 analysis.json 이 있는 폴더")
    ap.add_argument("-o", "--out", help="출력 CSV. 기본 build/data/wear_endurance_<chip>.csv")
    a = ap.parse_args(argv)
    rows = build(a.chip, a.sessions, a.data, warn=lambda m: print(m, file=sys.stderr))
    out = Path(a.out or REPO / "build" / "data" / f"wear_endurance_{a.chip}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, lineterminator="\n")              # 승격본과 같은 LF
        w.writeheader()
        w.writerows(rows)
    print(f"{out} — {len(rows)}행")


if __name__ == "__main__":
    main()
