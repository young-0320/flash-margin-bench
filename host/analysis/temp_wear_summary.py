# temp_wear_summary.py — 온도 마모 런 요약: 체크포인트 표 · 구간/측정/시간별 온도 · 그림 2장
#
# 사용: uv run python host/analysis/temp_wear_summary.py --chip chip17 \
#         --sessions data/wear/1790851785 data/wear/1790879592 --temp 'data/temp_chip17_*.csv'
#
# 입력: run_wear 세션 폴더(session.log · checkpoints.csv) — 구간·체크포인트의 시각(UTC)과 소거·프로그램 요약
#       data/session_<chip>_*.log · data/sweep_<chip>_*.analysis.json — 체크포인트 스윕의 폭과 창 위치(recenter)
#       hw/temp_logger.py CSV (host_utc,ms,target_c,temp_c,pwm,duty_pct,state,fault) — 1초 온도
#       docs/results/data/wear_curves/ 의 1k 구간 표 · newchip 집계표 — 상온 빠른 무리와의 배율 비교
# 출력: build/data/wear_temp_<chip>.csv (체크포인트 표) · temp_<chip>_intervals.csv (구간·측정·전체) ·
#       temp_<chip>_hourly.csv (KST 시간별) · build/plots/temp_<chip>_timeline.png · wear_temp_<chip>.png
# 시각: 로그는 전부 UTC. 표의 *_utc 열은 UTC, 시간별 표와 그림의 시계는 KST(+9h)

import argparse
import csv
import glob
import json
import math
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt                              # noqa: E402

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wear_checkpoint_csv as wcc                           # noqa: E402

SURVEY_CSV = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"
CURVES_DIR = REPO / "docs" / "results" / "data" / "wear_curves"
ROOM_FAST = ("chip01", "chip04", "chip09")                 # 상온 빠른 무리 교정 칩
KST = timedelta(hours=9)
BAND = (63.0, 67.0)                                         # 「65±2°C 안」 비율의 띠

# 플롯 팔레트 (dataviz 검증 통과 — 강조 1색 + 회색, 측정 표시 1색)
SURFACE = "#fcfcfb"
INK, INK2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE = "#e1e0d9", "#c3c2b7"
HOT, MEAS = "#4a3aa7", "#eb6834"

TS = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] (.*)")


def session_events(sdir):
    """session.log → [(UTC datetime, 본문)]. 줄의 시각은 시:분:초뿐이라 세션 번호(시작 유닉스 시각)의 날짜에서 자정을 넘긴다."""
    day = datetime.fromtimestamp(int(Path(sdir).name), timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    out, prev = [], None
    for line in (Path(sdir) / "session.log").read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS.match(line)
        if not m:
            continue
        tod = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3])
        if prev is not None and tod < prev - 600:
            day += timedelta(days=1)
        prev = tod
        out.append((day + timedelta(seconds=tod), m[4]))
    return out


def timeline(sessions):
    """세션들 → 마모 구간 [(a, b, t0, t1)] · 체크포인트 {cycle: dict(prep0, prep1, end, sweep_csv)}."""
    segs, cps = [], {}
    for sdir in sessions:
        ev = session_events(sdir)
        start = prep0 = prep1 = None
        for t, msg in ev:
            if msg.startswith("START:"):
                m = re.search(r"cycle=(\d+) delta=(\d+)", msg)
                start = (t, int(m[1]), int(m[1]) + int(m[2]))
            elif msg.startswith("stopped:") and start:
                segs.append((start[1], int(re.search(r"\((\d+),", msg)[1]), start[0], t))
                start = None
            elif "세션1 프로그래밍 (g2_jedec + flash_prep)" in msg:
                prep0, prep1 = t, None
            elif "run_wear checkpoint" in msg and prep0 and prep1 is None:
                prep1 = t
            elif (m := re.match(r"체크포인트 (\d+): \d+,[^,]*,(sweep_[^,]+\.csv)", msg)):
                cps[int(m[1])] = {"prep0": prep0, "prep1": prep1 or prep0, "end": t, "sweep_csv": m[2],
                                  "session": Path(sdir).name}
                prep0 = prep1 = None
    return segs, cps


def load_temp(pattern):
    rows = []
    for path in sorted(glob.glob(pattern)):
        with open(path, newline="") as f:
            for r in csv.DictReader(f):
                rows.append((datetime.fromisoformat(r["host_utc"]).timestamp(), float(r["temp_c"]),
                             float(r["target_c"]), r["state"]))
    rows.sort()
    t = np.array([r[0] for r in rows])
    return t, np.array([r[1] for r in rows]), np.array([r[2] for r in rows]), np.array([r[3] for r in rows])


def stats(temp, target, state, mask):
    v = temp[mask]
    if not len(v):
        return {"n": 0}
    run = state[mask] == "RUN"
    sp = sorted({f"{x:g}" for x in target[mask][run]})
    return {"n": int(len(v)), "mean_c": round(float(v.mean()), 2), "sd_c": round(float(v.std(ddof=1)) if len(v) > 1 else 0.0, 2),
            "min_c": round(float(v.min()), 2), "p5_c": round(float(np.percentile(v, 5)), 2),
            "p95_c": round(float(np.percentile(v, 95)), 2), "max_c": round(float(v.max()), 2),
            "in_63_67_pct": round(100.0 * float(((v >= BAND[0]) & (v <= BAND[1])).mean()), 1),
            "run_pct": round(100.0 * float(run.mean()), 1), "setpoint_c": "/".join(sp)}


def sweep_info(chip):
    """data/ 의 스윕 세션 로그 → {sweep_csv: (batch, recenter 스텝)} · analysis.json → {sweep_csv: 폭 3종 · 바닥}."""
    info = {}
    for log in glob.glob(str(REPO / "data" / f"session_{chip}_*.log")):
        txt = Path(log).read_text(encoding="utf-8", errors="replace")
        m, b, r = re.search(r"\bVALID (sweep_\S+\.csv)", txt),re.search(r"batch (\w+):", txt), re.search(r"-> (-?\d+) 스텝", txt)
        if m:
            info[m[1]] = {"batch": b[1] if b else "", "recenter": int(r[1]) if r else ""}
    for js in glob.glob(str(REPO / "data" / f"sweep_{chip}_*.analysis.json")):
        a = json.loads(Path(js).read_text())
        key = Path(js).name.replace(".analysis.json", ".csv")
        info.setdefault(key, {}).update({k: a.get(f"width_ps@{th}") for k, th in
                                         (("w2", "0.01"), ("w3", "0.001"), ("w4", "0.0001"))} | {"floor": a.get("floor_ber")})
    return info


def fresh_values():
    with open(SURVEY_CSV, newline="") as f:
        return {r["label"]: float(r["erase_us_median"]) for r in csv.DictReader(f) if r["erase_us_median"]}


def ratio_curve(path, fresh_us):
    """1k 구간 표 → (구간 끝 사이클 배열, 섹터 p50 의 중앙값 ÷ 신품값)."""
    by = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            by.setdefault(int(r["bin_end"]), []).append(float(r["erase_us_p50"]))
    ends = sorted(by)
    return np.array(ends), np.array([float(np.median(by[e])) / fresh_us for e in ends])


def style(ax):
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=8.5)
    ax.grid(True, color=GRID, lw=0.6)
    ax.set_axisbelow(True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="온도 마모 런 요약 — 체크포인트 표 · 온도 통계 · 그림")
    ap.add_argument("--chip", required=True)
    ap.add_argument("--sessions", nargs="+", required=True, help="run_wear 세션 폴더, 시간 순")
    ap.add_argument("--temp", required=True, help="temp_logger CSV glob")
    ap.add_argument("--curves", help="이 칩의 1k 구간 표 (wear_curves.py 산출) — 없으면 배율 칸을 그리지 않는다")
    ap.add_argument("--outdir", default=str(REPO / "build" / "data"))
    ap.add_argument("--plotdir", default=str(REPO / "build" / "plots"))
    a = ap.parse_args(argv)
    out, pdir = Path(a.outdir), Path(a.plotdir)
    out.mkdir(parents=True, exist_ok=True)
    pdir.mkdir(parents=True, exist_ok=True)

    segs, cps = timeline(a.sessions)
    t, temp, target, state = load_temp(a.temp)
    fresh = fresh_values()
    sw = sweep_info(a.chip)

    # ── 구간·측정·전체 온도 ──
    def win(t0, t1):
        return (t >= t0.timestamp()) & (t <= t1.timestamp())
    rows, wear_mask, meas_mask = [], np.zeros(len(t), bool), np.zeros(len(t), bool)
    seg_stats = {}
    for c0, c1, t0, t1 in segs:
        m = win(t0, t1)
        wear_mask |= m
        s = stats(temp, target, state, m)
        seg_stats[c1] = s
        rows.append({"kind": "wear", "label": f"{c0:,}→{c1:,}", "cycle_from": c0, "cycle_to": c1,
                     "start_utc": f"{t0:%Y-%m-%dT%H:%M:%SZ}", "end_utc": f"{t1:%Y-%m-%dT%H:%M:%SZ}",
                     "minutes": round((t1 - t0).total_seconds() / 60, 1)} | s)
    cp_stats = {}
    for cyc in sorted(cps):
        c = cps[cyc]
        for kind, t0, t1 in (("prep", c["prep0"], c["prep1"]), ("sweep", c["prep1"], c["end"])):
            m = win(t0, t1)
            meas_mask |= m
            s = stats(temp, target, state, m)
            cp_stats[(cyc, kind)] = s
            rows.append({"kind": f"checkpoint_{kind}", "label": f"체크포인트 {cyc:,}", "cycle_from": cyc, "cycle_to": cyc,
                         "start_utc": f"{t0:%Y-%m-%dT%H:%M:%SZ}", "end_utc": f"{t1:%Y-%m-%dT%H:%M:%SZ}",
                         "minutes": round((t1 - t0).total_seconds() / 60, 1)} | s)
    total_cycles = sum(c1 - c0 for c0, c1, _, _ in segs)
    cyc_w = sum((c1 - c0) * seg_stats[c1]["mean_c"] for c0, c1, _, _ in segs) / total_cycles
    for kind, label, m in (("overall", "마모 구간 전체 (시간 가중)", wear_mask),
                           ("overall", "체크포인트 측정 전체", meas_mask),
                           ("overall", "로그 전체", np.ones(len(t), bool))):
        rows.append({"kind": kind, "label": label, "minutes": round(m.sum() / 60, 1)} | stats(temp, target, state, m))
    rows.append({"kind": "overall", "label": "마모 구간 전체 (사이클 가중)", "cycle_from": 0, "cycle_to": total_cycles,
                 "mean_c": round(cyc_w, 2)})
    fields = ["kind", "label", "cycle_from", "cycle_to", "start_utc", "end_utc", "minutes", "n", "mean_c", "sd_c",
              "min_c", "p5_c", "p95_c", "max_c", "in_63_67_pct", "run_pct", "setpoint_c"]
    with (out / f"temp_{a.chip}_intervals.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    # ── KST 시간별 ──
    hour = np.floor((t + KST.total_seconds()) / 3600).astype(int)
    hrows = []
    for h in np.unique(hour):
        m = hour == h
        hk = datetime.fromtimestamp(h * 3600, timezone.utc)                # 이미 KST 로 민 값
        hrows.append({"hour_kst": f"{hk:%m-%d %H}:00", "wear_pct": round(100 * float(wear_mask[m].mean()), 1),
                      "measure_pct": round(100 * float(meas_mask[m].mean()), 1)} | stats(temp, target, state, m))
    hf = ["hour_kst", "n", "mean_c", "sd_c", "min_c", "p5_c", "p95_c", "max_c", "in_63_67_pct", "run_pct", "setpoint_c",
          "wear_pct", "measure_pct"]
    with (out / f"temp_{a.chip}_hourly.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=hf)
        w.writeheader()
        w.writerows(hrows)

    # ── 체크포인트 표 (상온 칩 표와 같은 열 + 온도·창 위치) ──
    ck = {}
    for sdir in a.sessions:
        with open(Path(sdir) / "checkpoints.csv", newline="") as f:
            for r in csv.DictReader(f):
                ck[int(r["cycle"])] = r
    cfields = ["cycle", "mhz", "width_1e2_ps", "width_1e3_ps", "width_1e4_ps", "floor_ber", "erase_us_p50", "erase_us_p99",
               "erase_us_max", "program_us_p50", "program_us_p99", "program_us_max", "cycle_s_p50", "recenter_steps",
               "temp_wear_c", "temp_prep_c", "temp_sweep_c", "sweep_batch", "wear_session", "note"]
    crows = []
    wear_start = datetime.fromtimestamp(int(Path(a.sessions[0]).name), timezone.utc)
    x0 = wcc.pick_x0(a.chip, [s for s in wcc.session_logs(a.chip, REPO / "data") if s["t"] < wear_start],
                     warn=lambda m: print(m, file=sys.stderr))         # x=0 — 상온 newchip (상온 칩 표와 같은 규칙)
    if x0:
        s0 = sw.get(x0["sweep"], {})
        crows.append({"cycle": 0, "mhz": 25, "width_1e2_ps": s0.get("w2"), "width_1e3_ps": s0.get("w3"),
                      "width_1e4_ps": s0.get("w4"), "floor_ber": s0.get("floor"), "erase_us_p50": wcc.med(x0["erase"]),
                      "recenter_steps": s0.get("recenter", ""), "sweep_batch": s0.get("batch", ""),
                      "note": f"x=0 신품 — newchip prep 소거 n={len(x0['erase'])} (집계표 §1). 상온 newchip — 마모 온도·리그와 다를 수 있다"})
    for cyc in sorted(ck):
        r, s = ck[cyc], sw.get(ck[cyc]["sweep_csv"], {})
        crows.append({"cycle": cyc, "mhz": int(r["mhz"]), "width_1e2_ps": s.get("w2"), "width_1e3_ps": s.get("w3"),
                      "width_1e4_ps": s.get("w4"), "floor_ber": s.get("floor"),
                      **{k: r[k.replace("erase_us", "t_erase").replace("program_us", "t_program")]
                         for k in cfields[6:12]},
                      "cycle_s_p50": r["cycle_s_p50"], "recenter_steps": s.get("recenter", ""),
                      "temp_wear_c": seg_stats.get(cyc, {}).get("mean_c", ""),
                      "temp_prep_c": cp_stats.get((cyc, "prep"), {}).get("mean_c", ""),
                      "temp_sweep_c": cp_stats.get((cyc, "sweep"), {}).get("mean_c", ""),
                      "sweep_batch": s.get("batch", ""), "wear_session": r["session"], "note": r["measured"]})
    with (out / f"wear_temp_{a.chip}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cfields)
        w.writeheader()
        w.writerows(crows)

    plt.rcParams["font.family"] = "Noto Sans CJK JP"

    # ── 그림 1: 시계 축 온도 ──
    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=150)
    fig.patch.set_facecolor(SURFACE)
    style(ax)
    tk = np.array([datetime.fromtimestamp(x, timezone.utc).replace(tzinfo=None) + KST for x in t])
    for cyc in sorted(cps):
        c = cps[cyc]
        ax.axvspan(c["prep0"].replace(tzinfo=None) + KST, c["end"].replace(tzinfo=None) + KST, color=GRID, alpha=0.9, lw=0)
    ax.plot(tk, temp, color=MUTED, lw=0.5, alpha=0.55, label="1초 측정")
    sp = np.where(state == "RUN", target, np.nan)
    ax.plot(tk, sp, color=INK2, lw=1, ls=(0, (4, 3)), label="설정 온도")
    hx = [datetime.strptime(f"2026-{r['hour_kst']}", "%Y-%m-%d %H:%M") for r in hrows]
    hx[0] = max(hx[0], tk[0])
    ax.step(hx + [hx[-1] + timedelta(hours=1)], [r["mean_c"] for r in hrows] + [hrows[-1]["mean_c"]],
            where="post", color=HOT, lw=2, label="시간별 평균")
    for cyc in (100, 10000, 50000, 100000):
        if cyc in cps:
            x = cps[cyc]["end"].replace(tzinfo=None) + KST
            ax.annotate(f"{cyc // 1000}k" if cyc >= 1000 else f"{cyc}", (x, 70.6), ha="center", fontsize=8, color=INK2)
    ylo = 54
    offs = [i for i in range(1, len(t)) if state[i] == "OFF" and state[i - 1] == "RUN"]
    for k, i in enumerate(offs):
        j = i + int(np.argmin(temp[i:i + 600]))
        right = (t[j] - t[0]) < 0.2 * (t[-1] - t[0])                 # 앞쪽 사건은 글을 오른쪽에
        ax.annotate(f"로거 재시작 → 히터 꺼짐 (최저 {temp[j]:.1f}°C)", (tk[j], max(temp[j], ylo + 0.3)),
                    xytext=(14 if right else -150, (4 if right else 14 + 14 * k)), textcoords="offset points", fontsize=8, color=INK2,
                    arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.8))
    first68 = next((i for i in range(len(t)) if state[i] == "RUN" and target[i] >= 68), None)
    ax.annotate("설정 65°C — 제어가 출렁여 짧게 58°C 까지", (tk[0] + timedelta(minutes=40), 58.9), fontsize=8, color=INK2)
    if first68 is not None:
        ax.annotate("설정 68°C — 히터 출력 상한(86%)에 붙어 약 65.4°C 에서 평형", (tk[first68] + timedelta(hours=2), 68.4),
                    fontsize=8, color=INK2)
    ax.set_ylim(ylo, 71.5)
    ax.set_ylabel("칩 위 온도 (°C, TMP117)", color=INK2, fontsize=9)
    ax.set_xlabel("시각 (KST) · 회색 띠 = 체크포인트 측정(prep + 스윕)", color=INK2, fontsize=9)
    import matplotlib.dates as mdates
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax.legend(loc="lower center", frameon=False, fontsize=8.5, labelcolor=INK2, ncol=3)
    ax.set_title(f"{a.chip} 온도 마모 런 — 마모 중 칩 위 온도", color=INK, fontsize=11, loc="left")
    fig.tight_layout()
    fig.savefig(pdir / f"temp_{a.chip}_timeline.png", facecolor=SURFACE)
    plt.close(fig)

    # ── 그림 2: 사이클 축 세 칸 (온도 · 폭 변화 · 소거 배율) ──
    nrow = 3 if a.curves else 2
    fig, axes = plt.subplots(nrow, 1, figsize=(10, 2.6 * nrow + 0.6), dpi=150, sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax in axes:
        style(ax)
    ax = axes[0]
    for c0, c1, _, _ in segs:
        s = seg_stats[c1]
        ax.fill_between([c0 / 1e3, c1 / 1e3], s["p5_c"], s["p95_c"], color=HOT, alpha=0.15, lw=0)
        ax.plot([c0 / 1e3, c1 / 1e3], [s["mean_c"]] * 2, color=HOT, lw=2,
                label="마모 구간 평균 (띠 5-95%)" if c0 == 0 else None)
    mx = [cyc / 1e3 for cyc in sorted(cps)]
    my = [cp_stats[(cyc, "prep")]["mean_c"] for cyc in sorted(cps)]
    ax.scatter(mx, my, s=28, color=MEAS, edgecolor=SURFACE, lw=1.5, zorder=3, label="체크포인트 prep 중 (소거 측정)")
    ax.set_ylabel("온도 (°C)", color=INK2, fontsize=9)
    ax.set_ylim(55, 69)
    ax.legend(loc="lower right", frameon=False, fontsize=8.5, labelcolor=INK2, ncol=2)
    ax.set_title("마모 중 온도 — 사이클 축", color=INK, fontsize=10.5, loc="left")

    ax = axes[1]
    w100 = next(r["width_1e2_ps"] for r in crows if r["cycle"] == 100)
    ax.axhspan(-42, 42, color=GRID, alpha=0.7, lw=0)
    ax.annotate("재장착 3σ (±42ps)", (101, 42), xytext=(0, -11), textcoords="offset points", ha="right", fontsize=8, color=INK2)
    for chip in ROOM_FAST:
        p = REPO / "docs" / "results" / "data" / "wear" / (f"wear_pilot_{chip}_2026-09.csv" if chip == "chip01"
                                                           else f"wear_endurance_{chip}_2026-09.csv")
        if not p.exists():
            continue
        with open(p, newline="") as f:
            pts = [(int(r["cycle"]), float(r["width_1e2_ps"])) for r in csv.DictReader(f)
                   if r["mhz"] == "25" and r["width_1e2_ps"] and r["cycle"].isdigit() and 100 <= int(r["cycle"]) <= 100000]
        if pts:
            base = dict(pts).get(100, pts[0][1])
            xs, ys = zip(*sorted(set(pts)))
            ax.plot([x / 1e3 for x in xs], [y - base for y in ys], color=MUTED, lw=1, alpha=0.8,
                    label="상온 빠른 무리 (chip01 · chip04)" if chip == "chip01" else None)
    cx = [r["cycle"] / 1e3 for r in crows if r["cycle"] >= 100]
    cy = [r["width_1e2_ps"] - w100 for r in crows if r["cycle"] >= 100]
    ax.plot(cx, cy, color=HOT, lw=2, marker="o", ms=4.5, mec=SURFACE, mew=1.2, label=f"{a.chip} (65°C)")
    ax.annotate(f"{a.chip} (65°C)", (cx[-1], cy[-1]), xytext=(4, 0), textcoords="offset points", va="center",
                fontsize=8.5, color=INK)
    ax.legend(loc="lower left", frameon=False, fontsize=8.5, labelcolor=INK2, ncol=2)
    ax.set_ylabel("폭 변화 (ps, 100 사이클 대비)", color=INK2, fontsize=9)
    ax.set_ylim(-80, 80)
    ax.set_title("25MHz 유효 창 폭 (BER 1e-2) — 100 사이클 대비 변화", color=INK, fontsize=10.5, loc="left")

    if a.curves:
        ax = axes[2]
        for chip in ROOM_FAST:
            p = CURVES_DIR / f"wear_curves_{chip}_2026-09.csv"
            x, y = ratio_curve(p, fresh[chip])
            m = x <= 100000
            ax.plot(x[m] / 1e3, y[m], color=MUTED, lw=1.2, alpha=0.85,
                    label="상온 빠른 무리 (chip01 · 04 · 09)" if chip == "chip01" else None)
            ax.annotate(f"{chip} (상온)", (x[m][-1] / 1e3, y[m][-1]), xytext=(4, 0), textcoords="offset points",
                        va="center", fontsize=8, color=MUTED)
        x, y = ratio_curve(a.curves, fresh[a.chip])
        ax.plot(x / 1e3, y, color=HOT, lw=2.2, label=f"{a.chip} (65°C)")
        ax.legend(loc="upper left", frameon=False, fontsize=8.5, labelcolor=INK2)
        ax.annotate(f"{a.chip} (65°C)", (x[-1] / 1e3, y[-1]), xytext=(4, 0), textcoords="offset points", va="center",
                    fontsize=8.5, color=INK)
        ax.set_ylabel("소거 시간 ÷ 신품값", color=INK2, fontsize=9)
        ax.set_title("소거 시간 배율 — 섹터 0-6 의 1k 구간 p50 중앙값 ÷ 신품값(상온 newchip)", color=INK, fontsize=10.5, loc="left")
    axes[-1].set_xlabel("누적 P/E 사이클 (k)", color=INK2, fontsize=9)
    axes[-1].set_xlim(0, 112)
    fig.tight_layout()
    fig.savefig(pdir / f"wear_temp_{a.chip}.png", facecolor=SURFACE)
    plt.close(fig)

    # ── 콘솔 요약: 상온 빠른 무리와의 배율 비교 ──
    print(f"마모 구간 {len(segs)}개 · 체크포인트 {len(cps)}개 · 온도 표본 {len(t):,}")
    for r in rows:
        if r["kind"] == "overall":
            print(f"  {r['label']}: 평균 {r.get('mean_c')} °C · sd {r.get('sd_c', '')} · 63-67 안 {r.get('in_63_67_pct', '')}%")
    if a.curves:
        x17, y17 = ratio_curve(a.curves, fresh[a.chip])
        ref = {c: ratio_curve(CURVES_DIR / f"wear_curves_{c}_2026-09.csv", fresh[c]) for c in ROOM_FAST}
        for xe in (10000, 50000, 100000):
            r17 = float(y17[x17 == xe][0])
            others = {c: float(v[1][v[0] == xe][0]) for c, v in ref.items() if xe in v[0]}
            lo = np.log(list(others.values()))
            tval = (math.log(r17) - lo.mean()) / (lo.std(ddof=1) * math.sqrt(1 + 1 / len(lo)))
            p = 1 - abs(tval) / math.sqrt(2 + tval ** 2) if len(lo) == 3 else float("nan")   # t 분포 자유도 2 의 양측 p
            print(f"  {xe // 1000}k 배율 {a.chip} {r17:.2f} · " + " · ".join(f"{c} {v:.2f}" for c, v in others.items())
                  + f" · 예측구간 t {tval:.2f} (df {len(lo) - 1}) p {p:.2f}")
        r_end = float(y17[-1])
        for c, (x, y) in ref.items():
            hit = np.nonzero(y >= r_end)[0]
            if len(hit):
                print(f"  {a.chip} 의 100k 배율 {r_end:.2f} 에 {c} 는 {x[hit[0]]:,} 사이클에 닿음 → 속도 비 {100000 / x[hit[0]]:.2f}")


if __name__ == "__main__":
    main()
