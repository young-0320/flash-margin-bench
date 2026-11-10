# deck_tables.py — 최종 발표 질의응답 부록의 기본 데이터 표 (손으로 옮기지 않으려고 원자료에서 뽑는다)
#
# 사용: uv run python host/analysis/deck_tables.py [-o build/deck/qa_tables.md]
#
# 입력: docs/results/data/wear_curves/wear_curves_chip*_20*.csv · docs/results/data/newchip_survey_2026-09.csv ·
#       docs/chip_registry.md 마킹 표 · docs/results/data/wear/wear_checkpoint_table_2026-10.md · data/wear/<세션>/ (없으면 소요 시간 표를 뺀다)
# 값 정의: 한 칸 = 그 사이클에서 끝나는 1k 구간의 섹터 0-6 소거(또는 프로그램) p50 을 섹터 7개에서 다시 중앙값 낸 것.
#          소거 배율 = 그 값 ÷ 집계표 신품값, 프로그램 배율 = 그 값 ÷ 그 칩의 첫 1k 구간. 슬라이드 7 · 8 · 12쪽 그림과 같은 정의다

import argparse
import csv
import glob
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from statistics import median

REPO = Path(__file__).resolve().parents[2]
RES = REPO / "docs" / "results" / "data"

GROUPS = (("빠른 무리 · 상온", ["chip01", "chip02", "chip04", "chip06", "chip09", "chip18"]),
          ("느린 무리 · 상온", ["chip03", "chip07", "chip15"]),
          ("느린 신품 · 빠른 노화 형 (상온 · 교정 밖)", ["chip12", "chip21"]),
          ("고온 · 빠른 무리", ["chip16", "chip17", "chip24", "chip26"]),
          ("고온 · 느린 무리", ["chip22", "chip23"]),
          ("JV 세대 (상온 · 교정 밖)", ["chip10", "chip14"]))
WORN = [c for _, chips in GROUPS for c in chips]
GRID = [1, 3, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 140, 160, 180, 200, 250, 300]
ROLE = {"chip01": "교정 · 파일럿", "chip02": "교정", "chip03": "교정", "chip04": "교정", "chip06": "상온 블라인드 → 교정", "chip07": "교정",
        "chip08": "블라인드 대기", "chip09": "교정", "chip10": "교정 밖 (JV)", "chip12": "교정 밖 (마킹 지워짐)", "chip14": "교정 밖 (JV)",
        "chip15": "교정", "chip16": "온도 65°C", "chip17": "온도 65°C", "chip18": "교정", "chip21": "교정 밖 (빠른 노화 형)",
        "chip22": "온도 85°C", "chip23": "온도 85°C · 판정 불합격", "chip24": "온도 85°C", "chip26": "온도 85°C · 판정 합격 · 시연"}


def load(chip):
    path, = glob.glob(str(RES / "wear_curves" / f"wear_curves_{chip}_*.csv"))
    out = defaultdict(dict)
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if int(r["sector"]) <= 6:
                out[int(r["bin_start"])][int(r["sector"])] = (float(r["erase_us_p50"]) / 1e3, float(r["program_us_p50"]) / 1e3,
                                                              float(r["erase_us_p10"]) / 1e3, float(r["erase_us_p90"]) / 1e3)
    return out


def survey():
    with open(RES / "newchip_survey_2026-09.csv", newline="", encoding="utf-8") as f:
        return {r["label"]: r for r in csv.DictReader(f)}


def markings():
    out = {}
    for line in (REPO / "docs" / "chip_registry.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 3 and re.fullmatch(r"chip\d+", cells[0]) and ("25Q64" in cells[1] or "지워짐" in cells[1]):
            out[cells[0]] = ("JV" if "JV" in cells[1] else "FV" if "FV" in cells[1] else "미상", cells[2].strip("`"))
    return out


def at(data, k, idx):
    v = data.get((k - 1) * 1000 + 1)
    return median(x[idx] for x in v.values()) if v else None


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return out + [""]


def tb_chips(sv, mk, data):
    rows = []
    for label in sorted(sv):
        r = sv[label]
        gen, code = mk.get(label, ("미상", "-"))
        if not r["erase_us_median"]:
            rows.append((label, gen, code, "측정 불가", "-", "-", "-", "-", "-", "신품 측정 불가"))
            continue
        ms = float(r["erase_us_median"]) / 1e3
        d = data.get(label)
        end = f"{max(d) + 999:,}" if d else "-"
        if label == "chip23":
            end = "26,528"
        elif label == "chip26":
            end = "70,000"
        rows.append((label, gen, code, "빠른" if ms < 40 else "느린", f"{ms:.1f}", f"{float(r['erase_us_min']) / 1e3:.1f}-{float(r['erase_us_max']) / 1e3:.1f}",
                     f"{float(r['width_1e2_ps']):,.0f}", end, r["date"][5:], ROLE.get(label, "미배정")))
    return table(["칩", "세대", "날짜 코드", "무리", "신품 소거 ms", "신품 섹터 범위 ms", "신품 폭 ps", "마모 끝", "신품 측정일", "용도"], rows)


def tb_metric(data, fresh, idx, title):
    out = []
    for name, chips in GROUPS:
        out.append(f"**{title} · {name}**\n")
        ks = [k for k in GRID if any(at(data[c], k, idx) is not None for c in chips)]
        rows = []
        for k in ks:
            row = [f"{k}k"]
            for c in chips:
                v = at(data[c], k, idx)
                if v is None:
                    row.append("-")
                    continue
                base = fresh[c] if idx == 0 else at(data[c], 1, 1)
                row.append(f"{v:.1f} ({v / base:.2f})" if idx == 0 else f"{v:.2f} ({v / base:.2f})")
            rows.append(row)
        out += table(["누적"] + chips, rows)
    return out


def tb_spread_between(data, fresh):
    def row(k, chips):
        e = [at(data[c], k, 0) / fresh[c] for c in chips if at(data[c], k, 0) is not None]
        p = [at(data[c], k, 1) / at(data[c], 1, 1) for c in chips if at(data[c], k, 1) is not None]
        if len(e) < 2:
            return None
        return (f"{k}k", len(e), f"{min(e):.2f}", f"{median(e):.2f}", f"{max(e):.2f}", f"{max(e) / min(e):.2f}", f"{min(p):.2f}", f"{median(p):.2f}", f"{max(p):.2f}")
    out = []
    for name, chips in (("빠른 무리 상온 6칩", GROUPS[0][1]), ("느린 무리 상온 3칩", GROUPS[1][1])):
        out.append(f"**{name}**\n")
        out += table(["누적", "칩 수", "소거 배율 최소", "중앙", "최대", "최대 ÷ 최소", "프로그램 배율 최소", "중앙", "최대"],
                     [r for r in (row(k, chips) for k in (1, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 150, 200)) if r])
    return out


def tb_spread_within(data):
    rows = []
    for c in WORN:
        for k in (100, 200):
            v = data[c].get((k - 1) * 1000 + 1)
            if v:
                ps = [x[0] for x in v.values()]
                rows.append((c, f"{k}k", f"{min(ps):.1f}", f"{max(ps):.1f}", f"{max(ps) - min(ps):.1f}", f"{median(x[3] - x[2] for x in v.values()):.1f}"))
    return table(["칩", "누적", "섹터 p50 최소 ms", "최대 ms", "섹터 간 차이 ms", "같은 섹터 p10-p90 폭 중앙 ms"], rows)


STEP_DOC = {"chip01": ("7/7", "34-62k", "19.7-22.0"), "chip02": ("7/7", "148-178k", "17.5-21.0"), "chip04": ("7/7", "25-47k", "18.5-22.7"),
            "chip06": ("7/7", "90k(섹터 0) · 116-158k", "18.1-21.3"), "chip09": ("7/7", "92k(섹터 6) · 110-157k", "18.1-21.3"), "chip18": ("5/7", "53-100k", "19.7-23.1"),
            "chip16": ("7/7", "해석 문서 참고", "-"), "chip24": ("3/7", "78-100k", "17-21")}   # 해석 문서(wear/*.md) 값 — 전환 시점 정의가 105ms 첫 도달과 다르다


def tb_steps(data):
    rows = []
    for c in WORN:
        first, jumps = {}, []
        for s in range(7):
            prev, best = None, 0.0
            for b in sorted(data[c]):
                if s not in data[c][b]:
                    prev = None
                    continue
                v = data[c][b][s][0]
                if prev is not None:
                    best = max(best, v - prev)
                if v >= 105 and s not in first:
                    first[s] = b + 999
                prev = v
            jumps.append(best)
        f = sorted(first.values())
        doc = STEP_DOC.get(c, ("없음", "-", "-"))
        rows.append((c, doc[0], doc[1], doc[2], f"{len(first)}/7", f"{f[0] / 1e3:.0f}-{f[-1] / 1e3:.0f}k" if f else "-", f"{min(jumps):.1f}-{max(jumps):.1f}"))
    return table(["칩", "계단 섹터", "계단 시점 (문서)", "높이 ms (문서)", "105ms 넘은 섹터 (계산)", "105ms 첫 도달 (계산)", "1k 구간 최대 상승 ms (계산)"], rows)


def tb_margin():
    text = (RES / "wear" / "wear_checkpoint_table_2026-10.md").read_text(encoding="utf-8")
    sec = text.split("## 욕조 폭")[1].split("\n## ")[0].splitlines()
    head = [c.strip() for c in sec[2].strip("|").split("|")]
    cols = defaultdict(list)
    for line in sec[4:]:
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(head):
            continue
        k = cells[0].replace(",", "")
        for name, c in zip(head[1:], cells[1:]):
            m = re.search(r"[\d,]+\.\d", c)
            if m:
                cols[name.split()[0]].append((k, float(m.group().replace(",", ""))))
    rows = []
    for chip, vals in cols.items():
        d = dict(vals)
        if "100" not in d:
            continue
        ref = d["100"]
        pts = [(int(k), v - ref) for k, v in vals if k.isdigit()]
        in100 = [x for k, x in pts if k <= 100_000]
        rows.append((chip, f"{ref:,.1f}", f"{min(in100):+.1f}", f"{max(in100):+.1f}", f"{max(k for k, _ in pts):,}", f"{min(x for _, x in pts):+.1f}", f"{max(x for _, x in pts):+.1f}"))
    return table(["칩", "체크포인트 100 폭 ps", "100k 안 최소 변화 ps", "최대 ps", "끝 사이클", "전 구간 최소 ps", "최대 ps"], rows)


def tb_durations(mk_uid):
    root = REPO / "data" / "wear"
    if not root.exists():
        return ["(리포 밖 `data/wear/` 가 없어 뺐다)", ""]
    sess = defaultdict(list)
    for s in sorted(os.listdir(root)):
        d = root / s
        if not (s.isdigit() and (d / "A.txt").exists() and (d / "A.txt").stat().st_size and (d / "session.log").exists()):
            continue
        m = re.search(r"chip_id=([0-9A-F]{16})", (d / "H.txt").open(errors="replace").readline())
        chip = mk_uid.get(m.group(1), "?") if m else "?"
        first = subprocess.run(["head", "-1", str(d / "A.txt")], capture_output=True, text=True, errors="replace").stdout
        last = subprocess.run(["tail", "-1", str(d / "A.txt")], capture_output=True, text=True, errors="replace").stdout
        c0, c1 = (int(re.search(r"cycle=(\d+)", x).group(1)) for x in (first, last))
        total, prev = 0, None
        for line in (d / "session.log").open(errors="replace"):
            t = re.match(r"\[(\d\d):(\d\d):(\d\d)\]", line)
            if t:
                sec = int(t[1]) * 3600 + int(t[2]) * 60 + int(t[3])
                if prev is not None:
                    total += sec - prev + (86400 if sec < prev else 0)
                prev = sec
        sess[chip].append((c0, c1, total / 3600))
    rows = []
    for c in WORN:
        ss = sess.get(c)
        if not ss:
            continue
        lo = sum(h for _, c1, h in ss if c1 <= 100_000)
        hi = sum(h for _, c1, h in ss if c1 > 100_000)
        cross = [s for s in ss if s[0] <= 100_000 < s[1]]
        note = "" if not cross else f"{cross[0][1]:,} 까지 한 세션이 100k 를 걸침"
        if c == "chip16":
            note = "로그 시각이 맞지 않아 뺐다 — 다음 세션이 24.6시간 뒤에 시작"
            lo = None
        rows.append((c, f"{max(s[1] for s in ss):,}", f"{lo:.1f}" if lo else "-", f"{hi:.1f}" if hi else "-", f"{sum(h for *_, h in ss):.1f}" if lo is not None else "-", note))
    return table(["칩", "끝 사이클", "10만 번까지 시간", "그 뒤 시간", "합계 시간", "비고"], rows)


def main():
    ap = argparse.ArgumentParser(description="질의응답 부록 기본 데이터 표")
    ap.add_argument("-o", "--out", default=str(REPO / "build" / "deck" / "qa_tables.md"))
    args = ap.parse_args()
    sv, mk = survey(), markings()
    data = {c: load(c) for c in WORN}
    fresh = {k: float(v["erase_us_median"]) / 1e3 for k, v in sv.items() if v["erase_us_median"]}
    uid = {v["uid"]: k for k, v in sv.items()}
    parts = {"CHIPS": tb_chips(sv, mk, data), "ERASE": tb_metric(data, fresh, 0, "소거 ms (÷신품)"), "PROGRAM": tb_metric(data, fresh, 1, "프로그램 ms (÷첫 1k)"),
             "BETWEEN": tb_spread_between(data, fresh), "WITHIN": tb_spread_within(data), "STEPS": tb_steps(data), "MARGIN": tb_margin(), "HOURS": tb_durations(uid)}
    out = []
    for key, lines in parts.items():
        out += [f"<!--{key}-->"] + lines
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"→ {args.out}")


if __name__ == "__main__":
    main()
