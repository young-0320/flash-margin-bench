# wear_checkpoint_table.py — 칩 × 체크포인트 한눈 표 (폭 · 소거 p50 · 프로그램 p50) 를 md 한 장으로
#
# 사용: uv run python host/analysis/wear_checkpoint_table.py [-o build/data/wear_checkpoint_table_2026-10.md]
#       uv run python host/analysis/wear_checkpoint_table.py --plot build/plots/wear_checkpoint_width_program_2026-10.png
#                                                        # 폭 변화 · 프로그램의 칩 간 그림 (2×2 — 행 = 지표, 열 = 무리)
#
# 입력: docs/results/data/wear/wear_*_20*.csv (칩별 체크포인트 표 — 칩 라벨은 파일 이름에서) ·
#       docs/results/data/newchip_survey_2026-09.csv (신품 행 · 무리 = 신품 소거 40ms 기준)
# 출력: md 한 장 — 표 셋(폭 · 소거 · 프로그램, 행 = 체크포인트, 열 = 칩) + 파일럿(격자가 다른 칩) 표 + 주.
#       손으로 고치지 않는다 — 칩 표가 늘면(chip12) 다시 뽑는다
# 규칙: 칩 표에서 사이클마다 **첫 25MHz 행**이 그 체크포인트다 (뒤의 사다리·newchip·반복 행은 같은 사이클의 다른 측정).
#       둘 이상의 칩에 있는 사이클이 행이 되고, 한 칩에만 있는 사이클은 「격자 밖」 으로 주에 적는다.
#       비고가 있는 행(「직후」 제외)은 [n] 을 달고 주에 비고를 그대로 옮긴다. 폭·소거가 다 빈 행은 「결측」

import argparse
import csv
import glob
import math
import re
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import plot_wear_curves as pwc                              # noqa: E402 — 칩 색·면 색은 배율 그림과 같게

REPO = Path(__file__).resolve().parents[2]
TABLES = str(REPO / "docs" / "results" / "data" / "wear" / "wear_*_20*.csv")
SURVEY = REPO / "docs" / "results" / "data" / "newchip_survey_2026-09.csv"
PLOTS = REPO / "docs" / "results" / "plots"                 # 표 문서(data/wear/)에서 ../../plots/
FAST_US = 40_000                                            # 신품 소거 40ms 미만 = 빠른 무리 (S-1 §15)
COLORS = {**pwc.CHIP_COLORS, "chip17": "#4a3aa7", "chip12": "#008300",   # 칸마다 --pairs all 검증 통과 (빠른 5색 · 느린 3색)
          "chip18": "#006300"}                              # 빠른 칸 5번째 — 팔레트 44단계 중 이것만 통과 (2026-10-04)
H1_PS = 42                                                  # S-1 §15 H1′ — 체크포인트 100 대비 3σ
SEPARATE = {"chip12": "구매처 미검증 — 같은 칩으로 보지 않는다, 로그 48 [D48-77]"}   # 무리에 넣지 않고 표·그림에서 뺀다


def load(pattern=TABLES):
    """칩 표들 → {chip: {"pilot": bool, "temp": °C|None, "rows": {cycle: row}}}. row 는 그 사이클의 첫 25MHz 행."""
    out = {}
    for path in sorted(glob.glob(pattern)):
        chip = re.search(r"(chip\d+)", Path(path).name).group(1)
        if chip in SEPARATE:
            continue
        rows, temps = {}, []
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                cyc = int(r["cycle"])
                if r["mhz"] == "25" and cyc > 0 and cyc not in rows:
                    rows[cyc] = r
                if r.get("temp_wear_c"):
                    temps.append(float(r["temp_wear_c"]))
        out[chip] = {"pilot": Path(path).name.startswith("wear_pilot_"),
                     "temp": round(statistics.mean(temps)) if temps else None, "rows": rows}
    return out


def survey(path=SURVEY):
    with open(path, newline="", encoding="utf-8") as f:
        return {r["label"]: r for r in csv.DictReader(f)}


def figures(chips):
    """이 표의 숫자를 그린 그림 — plots/ 에서 찾는다. 칩 이름이 든 그림(단일 스윕 욕조 bathtub_* 는 뺀다)과 칩을 겹친 배율 그림."""
    link = lambda name, label=None: f"[{label or name}](../../plots/{name})"
    wp = " · ".join(link(p.name) for p in sorted(PLOTS.glob("wear_checkpoint_width_program_*.png")))
    rows = [("폭 변화 · 프로그램 — 칩 간 (이 표의 그림)", wp or "그림 없음 — 이 표가 정본"),
            ("소거 — 칩 겹침 (신품 대비 배율)", " · ".join(link(p.name) for p in sorted(PLOTS.glob("wear_ratio_curves_*.png"))))]
    per_chip = [(c, p.name) for c in sorted(chips) for p in sorted(PLOTS.glob(f"wear_curves_{c}_*.png"))]
    rows.append(("소거 — 칩별 섹터 곡선 (1k 구간)", " · ".join(link(n, c) for c, n in per_chip)))
    for c in sorted(chips):
        other = sorted(p.name for p in PLOTS.glob(f"*{c}_*.png") if not p.name.startswith(("bathtub_", "wear_curves_")))
        if other:
            rows.append((f"{c} 의 그림", " · ".join(link(n) for n in other)))
    return ["## 그림", "", "| 무엇 | 그림 |", "|---|---|"] + [f"| {a} | {b} |" for a, b in rows if b] + [""]


def num(v, scale, fmt):
    return fmt.format(float(v) / scale) if v not in ("", None) else None


def build(chips, fresh, title):
    main = [c for c in chips if not chips[c]["pilot"]]
    main.sort(key=lambda c: (chips[c]["temp"] is not None, int(fresh[c]["erase_us_median"]) >= FAST_US, c))
    counts = {}
    for c in main:
        for cyc in chips[c]["rows"]:
            counts[cyc] = counts.get(cyc, 0) + 1
    grid = sorted(cyc for cyc, n in counts.items() if n >= 2)
    notes, mark = [], {}
    for c in main:
        for cyc in grid:
            r = chips[c]["rows"].get(cyc)
            if r and (r.get("note") or "") not in ("", "직후"):
                notes.append(f"[{len(notes) + 1}] {c} {cyc:,} — {r['note']}")
                mark[(c, cyc)] = len(notes)

    def head(c):
        group = "빠른" if int(fresh[c]["erase_us_median"]) < FAST_US else "느린"
        return f"{c} ({group}" + (f" · {chips[c]['temp']}°C)" if chips[c]["temp"] is not None else ")")

    def cell(c, cyc, key, scale, fmt):
        if cyc == 0:
            v = {"width_1e2_ps": fresh[c]["width_1e2_ps"], "erase_us_p50": fresh[c]["erase_us_median"]}.get(key)
            return num(v, scale, fmt) or "—"
        r = chips[c]["rows"].get(cyc)
        if r is None:
            return ""
        v = "결측" if not r["width_1e2_ps"] and not r["erase_us_p50"] else num(r[key], scale, fmt) or "—"
        return v + (f" [{mark[(c, cyc)]}]" if (c, cyc) in mark else "")

    out = [f"# {title} — 칩 × 체크포인트 한눈 표 (폭 · 소거 · 프로그램)", "",
           "> 수치만 모은다. 칩별 표(`wear_*_20*.csv`)에서 `host/analysis/wear_checkpoint_table.py` 가 뽑았다 — 손으로 고치지 않고",
           "> 다시 뽑는다. 해석은 `../../wear/` 의 칩별 문서, 조건·원본은 칩별 수치 문서(`wear_*_20*.md`).", "",
           "- **무엇**: 체크포인트마다 25MHz 욕조 폭(BER 10⁻²) · 직전 구간 마모 루프의 소거 p50 · 프로그램 p50 (섹터 0-6 합산)",
           "- **신품 행**: 집계표 §1 (newchip — 다른 날·다른 장착). 소거는 prep 의 섹터 32-127 중앙값이라 마모 루프와 재는 자리가 다르고,",
           "  프로그램은 눈금이 달라(PRBS prep) 비워 둔다. 폭의 전후 비교는 체크포인트 100 기준이다(S-1 §15 H1′)",
           "- **열**: 빠른 무리(신품 소거 40ms 미만) → 느린 무리 → 온도 칩. 빈 칸은 아직 없는 점, `결측` 은 호스트가 놓쳐 못 잰 점,",
           "  `[n]` 은 아래 주",
           "- **뺀 칩**: " + " · ".join(f"{c} ({why})" for c, why in SEPARATE.items()) + " — 칩별 수치 문서에만 둔다", ""]
    out += figures(chips)
    for title_, key, scale, fmt in (("욕조 폭 (25MHz · BER 10⁻² · ps)", "width_1e2_ps", 1, "{:,.1f}"),
                                    ("소거 p50 (ms)", "erase_us_p50", 1e3, "{:.1f}"),
                                    ("프로그램 p50 (ms)", "program_us_p50", 1e3, "{:.2f}")):
        out += [f"## {title_}", "", "| 누적 P/E | " + " | ".join(head(c) for c in main) + " |",
                "|---|" + "---|" * len(main)]
        for cyc in [0] + grid:
            out.append(f"| {'신품' if cyc == 0 else f'{cyc:,}'} | " + " | ".join(cell(c, cyc, key, scale, fmt) for c in main) + " |")
        out.append("")
    for c in (c for c in chips if chips[c]["pilot"]):
        out += [f"## {c} — 파일럿 (체크포인트 격자가 다르다)", "", "| 누적 P/E | 폭 (ps) | 소거 p50 (ms) | 프로그램 p50 (ms) |", "|---|---|---|---|"]
        for cyc in [0] + sorted(chips[c]["rows"]):
            out.append(f"| {'신품' if cyc == 0 else f'{cyc:,}'} | {cell(c, cyc, 'width_1e2_ps', 1, '{:,.1f}')} | "
                       f"{cell(c, cyc, 'erase_us_p50', 1e3, '{:.1f}')} | {cell(c, cyc, 'program_us_p50', 1e3, '{:.2f}')} |")
        out.append("")
    off = [(c, cyc, r) for c in main for cyc, r in sorted(chips[c]["rows"].items()) if cyc not in grid]
    out += ["## 주", ""] + [f"- {n}" for n in notes]
    for c, cyc, r in off:
        out.append(f"- 격자 밖: {c} {cyc:,} — 폭 {num(r['width_1e2_ps'], 1, '{:,.1f}')} ps · 소거 {num(r['erase_us_p50'], 1e3, '{:.1f}')} ms · "
                   f"프로그램 {num(r['program_us_p50'], 1e3, '{:.2f}')} ms — {r.get('note') or ''}".rstrip(" —"))
    out += ["", "## 재현", "", "```bash",
            "uv run python host/analysis/wear_checkpoint_table.py --plot build/plots/wear_checkpoint_width_program_2026-10.png   # 그 뒤 plots/ 로 승격",
            f"uv run python host/analysis/wear_checkpoint_table.py -o build/data/{title}.md   # 그 뒤 data/wear/ 로 승격 (그림 링크는 plots/ 를 보고 단다)",
            "```", ""]
    return "\n".join(out)


def plot(chips, fresh, out_png, xmax=100_000):
    """폭 변화(체크포인트 100 대비) · 프로그램 p50 — 행 = 지표, 열 = 무리. 같은 칸 안의 칩 색은 --pairs all 로 검증했다.
    폭은 비고에 「계측 사건」 이 든 행부터 그리지 않는다(기준이 달라 마모와 비교할 수 없다 — 표의 주). 휴지 뒤 점은 속 빈 표식,
    온도 칩은 점선. 파일럿(300k)은 xmax 까지만 — 그 너머는 표에 있다."""
    new = sorted(c for c in chips if c not in COLORS)
    if new:
        print(f"색 미지정 {', '.join(new)} — 회색으로 그린다. COLORS 에 넣고 --pairs all 검증 뒤 다시 그린다")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fast = lambda c: int(fresh[c]["erase_us_median"]) < FAST_US
    cols = (("빠른 무리 (신품 40ms 미만) · 점선은 65°C", sorted(c for c in chips if fast(c))),
            ("느린 무리 (신품 40ms 이상)", sorted(c for c in chips if not fast(c))))
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.4), sharex=True, sharey="row", dpi=160)
    fig.set_facecolor(pwc.SURFACE)
    ends = {}                                                # 칸 → [(x, y, 라벨)] — 끝 라벨은 축 범위가 정해진 뒤에 단다
    for j, (title, members) in enumerate(cols):
        for i in (0, 1):
            ax = axes[i][j]
            ax.set_facecolor(pwc.SURFACE)
            ax.grid(True, color=pwc.GRID, lw=0.7)
            ax.set_axisbelow(True)
            for side in ("left", "bottom"):
                ax.spines[side].set_color(pwc.BASELINE)
            for side in ("right", "top"):
                ax.spines[side].set_visible(False)
            ax.tick_params(colors=pwc.INK2, labelsize=8.5)
        axes[0][j].axhspan(-H1_PS, H1_PS, color=pwc.GRID, alpha=0.55, lw=0)
        axes[0][j].axhline(0, color=pwc.BASELINE, lw=1)
        axes[0][j].set_title(title, color=pwc.INK, fontsize=10.5, loc="left")
        for c in members:
            rows = sorted((cyc, r) for cyc, r in chips[c]["rows"].items() if cyc <= xmax)
            base = float(chips[c]["rows"][100]["width_1e2_ps"])
            cut = next((cyc for cyc, r in rows if "계측 사건" in (r.get("note") or "")), None)
            x = [cyc / 1e3 for cyc, _ in rows]
            dw = [float(r["width_1e2_ps"]) - base if r["width_1e2_ps"] and (cut is None or cyc < cut) else math.nan for cyc, r in rows]
            pg = [float(r["program_us_p50"]) / 1e3 if r["program_us_p50"] else math.nan for _, r in rows]
            rested = [k for k, (_, r) in enumerate(rows) if (r.get("note") or "").startswith("휴지 뒤")]
            temp = chips[c]["temp"]
            label = c + (f" ({temp}°C)" if temp else "") + (" — 300k 중 100k 까지" if chips[c]["pilot"] else "")
            for i, ys in ((0, dw), (1, pg)):
                ax = axes[i][j]
                ax.plot(x, ys, color=COLORS.get(c, pwc.MUTED), lw=1.8, marker="o", ms=3.4, ls=(0, (4, 2)) if temp else "-", label=label)
                for k in rested:
                    ax.plot(x[k], ys[k], marker="o", ms=6, mfc=pwc.SURFACE, mec=COLORS.get(c, pwc.MUTED), mew=1.5, ls="none")
                last = max((k for k, v in enumerate(ys) if not math.isnan(v)), default=None)
                if last is not None and not chips[c]["pilot"]:       # 잘린 파일럿 선은 범례로만 — 끝 라벨이 다른 선 위에 얹힌다
                    ends.setdefault((i, j), []).append((x[last], ys[last], c))
            if cut is not None:
                axes[0][j].annotate(f"{c}: {cut:,} 부터 계측 사건 — 폭 기준이 달라 뺐다 (표의 주)", (0.99, 0.96),
                                    xycoords="axes fraction", ha="right", va="top", fontsize=8, color=pwc.INK2)
            missing = [cyc for cyc, r in rows if not r["width_1e2_ps"] and not r["erase_us_p50"]]
            if missing:
                axes[1][j].annotate(f"{c}: " + " · ".join(f"{m:,}" for m in missing) + " 결측 — 선이 끊긴 자리 (표의 주)",
                                    (0.99, 0.03), xycoords="axes fraction", ha="right", va="bottom", fontsize=8, color=pwc.INK2)
        axes[0][j].annotate(f"H1′ 기준 ±{H1_PS}ps (3σ)", (1, H1_PS), xytext=(2, -3), textcoords="offset points",
                            va="top", fontsize=8, color=pwc.MUTED)
        axes[1][j].legend(frameon=False, fontsize=8.5, labelcolor=pwc.INK2, loc="upper left")
        axes[1][j].set_xlabel("누적 P/E 사이클 (천 회)", color=pwc.INK2, fontsize=9)
    axes[0][0].set_ylabel("폭 변화 (ps) — 체크포인트 100 대비", color=pwc.INK2, fontsize=9)
    axes[1][0].set_ylabel("프로그램 p50 (ms)", color=pwc.INK2, fontsize=9)
    axes[0][0].set_xlim(0, xmax / 1e3 * 1.1)
    for (i, j), items in ends.items():                       # 끝 라벨 — 끝 x 가 가까운 것끼리만 겹치지 않게 위아래로 민다
        lo, hi = axes[i][j].get_ylim()
        gap, prev = (hi - lo) * 0.055, {}
        for xe, ye, text in sorted(items, key=lambda t: t[1]):
            key = round(xe / (xmax / 1e3 * 0.08))
            ye = ye if key not in prev or ye - prev[key] >= gap else prev[key] + gap
            axes[i][j].annotate(text, (xe, ye), xytext=(5, 0), textcoords="offset points", va="center", fontsize=8.5, color=pwc.INK2)
            prev[key] = ye
    fig.suptitle("체크포인트별 욕조 폭 변화와 프로그램 시간 — 25MHz · 섹터 0-6 · 속 빈 점은 휴지 뒤 측정",
                 color=pwc.INK, fontsize=11, x=0.01, ha="left")
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, facecolor=pwc.SURFACE)
    print(f"→ {out_png}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="칩 × 체크포인트 한눈 표 (md)")
    ap.add_argument("-o", "--out", default=str(REPO / "build" / "data" / "wear_checkpoint_table_2026-10.md"))
    ap.add_argument("--tables", default=TABLES, help="칩별 체크포인트 표 glob")
    ap.add_argument("--plot", metavar="PNG", help="표 대신 폭 변화 · 프로그램의 칩 간 그림을 그린다")
    args = ap.parse_args(argv)
    if args.plot:
        plot(load(args.tables), survey(), args.plot)
        return
    md = build(load(args.tables), survey(), Path(args.out).stem)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(md, encoding="utf-8")
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
