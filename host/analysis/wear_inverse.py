# wear_inverse.py — 수명 역산 1차(현장) 모델: 개봉 prep 의 섹터별 소거 시간 → 마모 섹터 0-6 의 누적 P/E 구간
#
# 사용:
#   uv run python host/analysis/wear_inverse.py data/session_chipNN_<uid>_<stamp>.log [prep 로그 더]   # 블라인드 개봉
#   uv run python host/analysis/wear_inverse.py --loco                                                   # 모의 블라인드
#   옵션: --scale ms|ratio (소거 시간 눈금 — S-1 §15 2026-09-30 추기의 규칙으로 고른다) · --split-ms 40 · --curves <glob>
#
# 모델 (S-1 §15 2026-09-30 추기):
#   입력 A  섹터 32-127 소거 시간의 중앙값  = 이 칩의 신품값. 40ms 아래면 빠른 무리(chip01·chip04 곡선), 위면 느린 무리(chip03·chip07)
#   입력 B  섹터 0-6 의 소거 시간 (prep 을 k 번 돌렸으면 7k 개)
#   입력 C  섹터 0-6 의 프로그램 시간 — A 의 무리 선택이 맞는지 확인만 (빠른 무리 7.0ms 근처 · 느린 무리 올라 있음)
#   교정    wear_curves CSV(1k 구간 × 섹터 × p10/p50/p90). 무리 안 칩 × 섹터 하나하나를 그 구간의 "구성원"으로 두고,
#           구성원마다 p50 을 중심, (p90-p10)/2.56 을 폭으로 하는 정규분포를 놓는다
#   계산    구간마다 관측 B 가 나올 우도 = 관측별 (구성원 평균 밀도) 의 기하 평균 — 7개 관측은 같은 칩이라 독립으로 곱하지 않는다.
#           평평한 사전으로 정규화 → 구간별 확률
#   출력    확률이 가장 큰 구간(MAP) · 68% · 95% 최고밀도 집합(사이클 범위로 합쳐서). 100k 너머는 교정이 없어 답하지 않는다
#           MAP 구간의 밴드(구성원 p10 최소 ~ p90 최대) 밖에 있는 관측 수를 같이 찍는다 — 전부 밖이면 교정 범위 밖이다
#
# --loco: 교정 칩 하나를 빼고 그 칩의 구간별 p50(섹터 7개)을 관측으로 넣어, 나머지 칩만으로 맞힌다. 블라인드 전에 기대 오차를 얻는
#         유일한 방법이다. 눈금(ms/ratio)은 이 결과가 더 좁고 정답을 더 자주 품는 쪽으로 고른다 — 규칙은 S-1 에 먼저 적었다

import argparse
import csv
import glob
import math
import re
import statistics
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CURVES_GLOB = str(REPO / "docs" / "results" / "data" / "wear_curves" / "wear_curves_*_2026-09.csv")
SURVEY_CSV = REPO / "docs" / "results" / "data" / "newchip" / "newchip_survey_2026-09.csv"
WORN = range(0, 7)
REFERENCE = range(32, 128)                 # 마모 영역에서 128KB 넘게 떨어진 섹터 — 세 칩에서 신품 대비 1.00
SIGMA_FLOOR = 0.02                         # 구간이 판판해도 폭을 p50 의 2% 아래로 두지 않는다 (한 표본의 자릿수 흔들림)
LOCO_CYCLES = (1_000, 3_000, 10_000, 20_000, 30_000, 40_000, 50_000, 60_000, 70_000, 80_000, 90_000, 100_000)

PREP_ERASE = re.compile(r"#PREP ERASE (\d+) (\d+)\s*$", re.M)
PREP_PROGRAM = re.compile(r"#PREP PROGRAM (\d+) (\d+)\s*$", re.M)


# ---------- 입력 ----------

def load_curves(pattern=CURVES_GLOB):
    """wear_curves CSV 들 → {chip: {bin_start: {sector: (p10, p50, p90)}}} (µs)."""
    curves = defaultdict(lambda: defaultdict(dict))
    for path in sorted(glob.glob(pattern)):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                curves[r["chip"]][int(r["bin_start"])][int(r["sector"])] = (
                    int(r["erase_us_p10"]), int(r["erase_us_p50"]), int(r["erase_us_p90"]))
    if not curves:
        raise SystemExit(f"교정 표가 없다: {pattern} — docs/results/data/wear_curves/wear_curves_2026-09.md 의 재현 명령으로 만든다")
    return curves


def load_fresh(path=SURVEY_CSV):
    """신품 집계표 → {chip: 신품 소거 중앙값 µs}. 교정 칩의 무리 판정과 ratio 눈금의 분모."""
    with open(path, newline="", encoding="utf-8") as f:
        return {r["label"]: int(r["erase_us_median"]) for r in csv.DictReader(f) if r["erase_us_median"]}


def parse_prep_logs(paths):
    """prep 세션 로그들 → (섹터→소거 µs 목록, 섹터→프로그램 µs 목록). 로그 여러 개면 같은 섹터에 값이 쌓인다."""
    erase, program = defaultdict(list), defaultdict(list)
    for p in paths:
        txt = Path(p).read_text(encoding="utf-8", errors="replace")
        for m in PREP_ERASE.finditer(txt):
            erase[int(m.group(1))].append(int(m.group(2)))
        for m in PREP_PROGRAM.finditer(txt):
            program[int(m.group(1))].append(int(m.group(2)))
    if not erase:
        raise SystemExit("#PREP ERASE 행이 없다 — newchip prep 의 세션 로그인가")
    return erase, program


def observation(erase):
    """입력 A(신품값)와 B(마모 섹터 소거 시간 목록)."""
    ref = [v for s in REFERENCE for v in erase.get(s, [])]
    worn = [v for s in WORN for v in erase.get(s, [])]
    if not ref or not worn:
        raise SystemExit("섹터 32-127 또는 0-6 의 소거 시간이 없다 — 전 범위 prep(0-127) 이어야 한다")
    return statistics.median(ref), worn


# ---------- 모델 ----------

def group_of(fresh_us, split_us):
    return "fast" if fresh_us < split_us else "slow"


def members(curves, fresh, chips, scale):
    """무리 안 칩들의 구간별 구성원 목록 → {bin_start: [(mu, sigma), ...]} (선택한 눈금)."""
    out = defaultdict(list)
    for chip in chips:
        div = fresh[chip] if scale == "ratio" else 1.0
        for b, sectors in curves[chip].items():
            for p10, p50, p90 in sectors.values():
                mu = p50 / div
                sigma = max((p90 - p10) / 2.5631 / div, SIGMA_FLOOR * mu)
                out[b].append((mu, sigma))
    return out


def _logpdf(x, mu, sigma):
    z = (x - mu) / sigma
    return -0.5 * z * z - math.log(sigma) - 0.9189385332046727


def _logmeanexp(vals):
    m = max(vals)
    return m + math.log(sum(math.exp(v - m) for v in vals) / len(vals))


def posterior(obs, mem):
    """관측 목록(선택한 눈금) → {bin_start: 확률}. 평평한 사전.

    관측 7개(또는 7k 개)는 같은 칩·같은 prep 에서 나와 독립이 아니다 — 로그 우도를 더하면 구간이 7배 정보를 가진 것처럼
    좁아진다. 그래서 관측 수로 나눈다(기하 평균) — 'prep 한 번 = 관측 하나'로 치는 가장 보수적인 쪽. 이 처리는 잠정이며
    모의 블라인드(--loco)가 정답을 품는 비율로 검증한다."""
    ll = {b: sum(_logmeanexp([_logpdf(x, mu, s) for mu, s in ms]) for x in obs) / len(obs) for b, ms in mem.items()}
    m = max(ll.values())
    w = {b: math.exp(v - m) for b, v in ll.items()}
    z = sum(w.values())
    return {b: v / z for b, v in w.items()}


def hpd(post, mass):
    """확률 상위부터 모아 mass 를 넘는 순간까지의 구간 집합."""
    acc, keep = 0.0, []
    for b, p in sorted(post.items(), key=lambda kv: -kv[1]):
        keep.append(b)
        acc += p
        if acc >= mass:
            break
    return sorted(keep)


def ranges(bins, width=1000):
    """[1, 1001, 2001, 5001] → [(1, 3000), (5001, 6000)] — 이어진 구간을 합친다."""
    out = []
    for b in bins:
        if out and out[-1][1] + 1 == b:
            out[-1] = (out[-1][0], b + width - 1)
        else:
            out.append((b, b + width - 1))
    return out


def invert(ref_us, worn_us, curves, fresh, scale, split_us):
    """입력 A·B → 결과 dict. 눈금 변환은 여기서만 한다."""
    grp = group_of(ref_us, split_us)
    chips = [c for c in curves if group_of(fresh[c], split_us) == grp]
    if not chips:
        raise SystemExit(f"{grp} 무리의 교정 칩이 없다")
    obs = [v / ref_us for v in worn_us] if scale == "ratio" else list(worn_us)
    mem = members(curves, fresh, chips, scale)
    post = posterior(obs, mem)
    top = max(post, key=post.get)
    lo = min(mu - 1.2816 * s for mu, s in mem[top])           # 밴드 = 구성원 p10 최소 ~ p90 최대
    hi = max(mu + 1.2816 * s for mu, s in mem[top])
    outside = sum(1 for x in obs if not lo <= x <= hi)
    return {"group": grp, "chips": chips, "map": (top, top + 999), "hpd68": ranges(hpd(post, 0.68)),
            "hpd95": ranges(hpd(post, 0.95)), "outside_at_map": outside, "n_obs": len(obs)}


def program_check(program, grp):
    """입력 C — 무리 선택의 교차 확인 문구. 판정에 넣지 않는다."""
    worn = [v for s in WORN for v in program.get(s, [])]
    if not worn:
        return "프로그램 시간 없음 (구 prep) — 교차 확인 생략"
    med = statistics.median(worn) / 1000
    hint = "빠른 무리와 맞음" if med < 7.3 else "느린 무리와 맞음"
    ok = (hint.startswith("빠른")) == (grp == "fast")
    return f"마모 섹터 프로그램 중앙값 {med:.2f}ms → {hint}" + ("" if ok else " — **입력 A 의 무리 선택과 어긋난다**")


def fmt_ranges(rs):
    return " · ".join(f"{a:,}-{b:,}" for a, b in rs)


# ---------- 모의 블라인드 ----------

def loco(curves, fresh, scale, split_us, cycles=LOCO_CYCLES):
    """교정 칩 하나씩 빼고 자기 p50 으로 맞힌다. 행마다 (칩, 정답, MAP, 68%, 95%, 정답∈68, 정답∈95)."""
    rows = []
    for chip in sorted(curves):
        rest = {c: v for c, v in curves.items() if c != chip}
        grp = group_of(fresh[chip], split_us)
        if not any(group_of(fresh[c], split_us) == grp for c in rest):
            continue
        for cyc in cycles:
            b = (cyc - 1) // 1000 * 1000 + 1
            if b not in curves[chip]:
                continue                                  # 공백 구간 (chip07 60k·80k)
            worn = [p50 for _, p50, _ in curves[chip][b].values()]
            r = invert(fresh[chip], worn, rest, fresh, scale, split_us)
            in68 = any(a <= cyc <= z for a, z in r["hpd68"])
            in95 = any(a <= cyc <= z for a, z in r["hpd95"])
            rows.append((chip, cyc, r["map"], r["hpd68"], r["hpd95"], in68, in95))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="수명 역산 1차 모델 — prep 소거 시간 → 누적 P/E 구간")
    ap.add_argument("logs", nargs="*", help="개봉 prep 세션 로그 (여러 개면 같은 칩의 반복 prep)")
    ap.add_argument("--loco", action="store_true", help="모의 블라인드 — 교정 칩을 하나씩 빼고 맞힌다")
    ap.add_argument("--scale", choices=("ms", "ratio"), default="ms", help="소거 시간 눈금 (기본 ms)")
    ap.add_argument("--split-ms", type=float, default=40.0, help="빠른/느린 무리 경계, 신품 소거 ms (기본 40)")
    ap.add_argument("--curves", default=CURVES_GLOB, help="교정 표 glob")
    args = ap.parse_args(argv)

    curves, fresh = load_curves(args.curves), load_fresh()
    split = args.split_ms * 1000

    if args.loco:
        rows = loco(curves, fresh, args.scale, split)
        if not rows:
            raise SystemExit("같은 무리에 칩이 둘 이상 있어야 모의 블라인드가 된다")
        print(f"모의 블라인드 · 눈금 {args.scale} · 경계 {args.split_ms:g}ms · 교정 칩 {sorted(curves)}")
        print("| 칩 | 정답 | MAP | 68% | 95% | 정답∈68 | 정답∈95 |\n|---|---|---|---|---|---|---|")
        for chip, cyc, mp, h68, h95, i68, i95 in rows:
            print(f"| {chip} | {cyc:,} | {mp[0]:,}-{mp[1]:,} | {fmt_ranges(h68)} | {fmt_ranges(h95)} | "
                  f"{'O' if i68 else 'X'} | {'O' if i95 else 'X'} |")
        w68 = [sum(z - a + 1 for a, z in h68) for *_, h68, _, _, _ in rows]
        print(f"정답∈68 {sum(r[5] for r in rows)}/{len(rows)} · 정답∈95 {sum(r[6] for r in rows)}/{len(rows)} · "
              f"68% 폭 중앙값 {statistics.median(w68):,.0f} 사이클")
        return

    if not args.logs:
        ap.error("prep 세션 로그를 주거나 --loco")
    erase, program = parse_prep_logs(args.logs)
    ref, worn = observation(erase)
    r = invert(ref, worn, curves, fresh, args.scale, split)
    print(f"입력 A  기준(32-127) 소거 중앙값 {ref / 1000:.1f}ms → {r['group']} 무리 (교정 {r['chips']}) · 눈금 {args.scale}")
    print(f"입력 B  마모 섹터 소거 {len(worn)}개: " + ", ".join(f"{v / 1000:.1f}" for v in worn) + " ms")
    print(f"입력 C  {program_check(program, r['group'])}")
    print(f"답      MAP {r['map'][0]:,}-{r['map'][1]:,} · 68% {fmt_ranges(r['hpd68'])} · 95% {fmt_ranges(r['hpd95'])}")
    if r["outside_at_map"]:
        print(f"주의    MAP 구간 밴드 밖 관측 {r['outside_at_map']}/{r['n_obs']}" +
              (" — 전부 밖: 교정 범위 밖이거나 무리 선택이 틀렸다" if r["outside_at_map"] == r["n_obs"] else ""))


if __name__ == "__main__":
    main()
