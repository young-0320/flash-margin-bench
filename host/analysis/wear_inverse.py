# wear_inverse.py — 수명 역산 1차(현장) 모델: 개봉 prep 의 섹터별 소거 시간 → 마모 섹터 0-6 의 누적 P/E 사이클 x 의 구간
#
# 사용:
#   uv run python host/analysis/wear_inverse.py data/session_chipNN_<uid>_<stamp>.log [prep 로그 더]   # 블라인드 개봉
#   uv run python host/analysis/wear_inverse.py --loco                                                   # 모의 블라인드
#   옵션: --scale ms|ratio (기본 ratio — 규칙은 S-1 §15 2026-09-30 추기, 4칩 LOCO 로 확정) · --rate-range 2.0 · --split-ms 40 · --curves <glob>
#         --synthetic N [--plot <png>]  합성 복원 (가정대로 만든 가짜 칩으로 포함률) · --prep-indep  시험용 우도 (기본 꺼짐)
#         --out <경로>  추정 결과를 파일로도 — 머리말에 git_rev · 인자 · 입력 로그 sha256 · 교정 표 (블라인드 기록용)
#
# 모델 (S-1 §15 2026-09-30 추기):
#   입력 A  섹터 32-127 소거 시간의 중앙값  = 이 칩의 신품값. 40ms 아래면 빠른 무리(chip01·chip04 곡선), 위면 느린 무리(chip03·chip07)
#   입력 B  섹터 0-6 의 소거 시간 (prep 을 k 번 돌렸으면 7k 개)
#   입력 C  섹터 0-6 의 프로그램 시간 — A 의 무리 선택이 맞는지 확인만 (빠른 무리 7.0ms 근처 · 느린 무리 올라 있음)
#   교정    wear_curves CSV(1k 구간 × 섹터 × p10/p50/p90). 무리 안 칩 × 섹터 하나하나를 그 구간의 "구성원"으로 두고,
#           구성원마다 p50 을 중심, (p90-p10)/2.56 을 폭으로 하는 정규분포를 놓는다
#   계산    곡선 지점 M 마다 관측 B 가 나올 우도 = 관측별 (구성원 평균 밀도) 의 기하 평균 — 7개 관측은 같은 칩이라 독립으로 곱하지 않는다.
#   속도 r  같은 무리 안에서도 사이클당 손상량이 칩마다 다르다 — 곡선 모양은 같고 가로축만 r 배 늘어난다(chip01 대 chip04 약 1.4,
#           chip03 대 chip07 약 1.25). 누적 사이클 x 인 칩은 교정 곡선의 M = x·r 지점처럼 보인다. r 은 [1/R, R] 에서 로그 균등으로
#           적분한다. R 의 규칙: 두 쌍의 로그 차이 평균 ÷ 1.13 = 개체 표준편차(약 0.25), 새 칩 하나 대 교정 칩 하나의 95% 범위
#           = √2 × 1.96 × 표준편차 → R ≈ 2.0. LOCO 결과에 맞춰 조정하지 않는다 (--rate-range 2.0 · 1 이면 끔)
#           x 의 사전은 1-100k 에 평평. → x 구간별 확률. 기호: 누적 P/E 사이클 = x (N 은 위상당 읽기 112 에만 쓴다, 로그 51 [D51-1])
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
RATE_RANGE = 2.0                           # 속도 배율 r 의 범위 [1/R, R]. 교정 5칩 LOCO 가 명목에 가장 가까운 값 (로그 48 [D48-60]) — rate_rule() 의 3.84 는 곡선 혼합과 r 이 칩 산포를 두 번 세어 버렸다
N_RATE = 41                                # r 격자 (로그 등간격, 홀수라 r=1 이 포함된다)
MAX_CYCLE = 100_000                        # 답하는 범위(x)의 끝 — 교정 4칩이 모두 닿는 곳. 곡선 지점 M = x·r 은 그 너머(chip01 의
                                           # 100k-300k)도 쓴다 — r > 1 인(교정 칩보다 빨리 늙는) 칩의 x ≤ 100k 를 설명하려면 필요하다
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


def curve_loglik(obs, mem, runs=1):
    """곡선 지점(bin_start)마다 관측 B 의 로그 우도.

    관측 수로 나눠(기하 평균) prep 전부를 관측 하나로 친다(runs=1, 기본). 측정 잡음만 보면 따로 돌린 prep 은 독립이라
    runs(prep 횟수)를 곱할 수 있지만, 처음 보는 칩에는 교정 곡선과의 차이가 있고 그것은 prep 을 반복해도 줄지 않는다 —
    합성 복원에서 runs 를 곱하면 정체 칩을 뺀 prep 5회의 95% 구간이 82% 만 품었다(곱하지 않으면 96%). 그래서 기본은 1,
    --prep-indep 는 시험용 (2026-10-01, 로그 48 [D48-58] · docs/results/data/inverse/synthetic_recovery_2026-10.md)."""
    return {b: runs * sum(_logmeanexp([_logpdf(x, mu, s) for mu, s in ms]) for x in obs) / len(obs)
            for b, ms in mem.items()}


def posterior(obs, mem, rate_range=1.0, runs=1):
    """관측 목록(선택한 눈금) → {x 구간 bin_start: 확률}. x(누적 사이클)는 1-MAX_CYCLE 에 평평한 사전.

    속도 배율 r 을 [1/R, R] 로그 균등으로 적분한다: P(x) ∝ Σ_r L(곡선 지점 x·r). 곡선에 없는 지점(교정 범위 밖)은 0 —
    그래서 큰 x 는 r 이 작은 쪽만 기여하고, 그것이 교정 범위가 주는 자연스러운 제약이다. rate_range ≤ 1 이면 r = 1 하나."""
    ll = curve_loglik(obs, mem, runs)
    m = max(ll.values())
    if rate_range <= 1:
        rs = [1.0]
    else:
        rs = [rate_range ** (-1 + 2 * i / (N_RATE - 1)) for i in range(N_RATE)]
    post = {}
    for xb in range(1, MAX_CYCLE + 1, 1000):
        c = xb + 499                                           # x 구간 중앙
        tot = 0.0
        for r in rs:
            mb = int((c * r - 1) // 1000) * 1000 + 1           # 곡선 지점 M = x·r 이 든 구간
            if mb in ll:
                tot += math.exp(ll[mb] - m)
        if tot > 0:
            post[xb] = tot / len(rs)
    z = sum(post.values())
    return {b: v / z for b, v in post.items()}


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


def invert(ref_us, worn_us, curves, fresh, scale, split_us, rate_range=1.0, runs=1):
    """입력 A·B → 결과 dict. 눈금 변환은 여기서만 한다."""
    grp = group_of(ref_us, split_us)
    chips = [c for c in curves if group_of(fresh[c], split_us) == grp]
    if not chips:
        raise SystemExit(f"{grp} 무리의 교정 칩이 없다")
    obs = [v / ref_us for v in worn_us] if scale == "ratio" else list(worn_us)
    mem = members(curves, fresh, chips, scale)
    post = posterior(obs, mem, rate_range, runs)
    top = max(post, key=post.get)
    # 밴드 검사는 r 을 빼고 곡선 위에서 가장 그럴듯한 지점(M*)의 구성원 p10 최소 ~ p90 최대로 한다
    ll = curve_loglik(obs, mem)
    mstar = max(ll, key=ll.get)
    lo = min(mu - 1.2816 * s for mu, s in mem[mstar])
    hi = max(mu + 1.2816 * s for mu, s in mem[mstar])
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

def loco(curves, fresh, scale, split_us, cycles=LOCO_CYCLES, rate_range=1.0):
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
            r = invert(fresh[chip], worn, rest, fresh, scale, split_us, rate_range)
            in68 = any(a <= cyc <= z for a, z in r["hpd68"])
            in95 = any(a <= cyc <= z for a, z in r["hpd95"])
            rows.append((chip, cyc, r["map"], r["hpd68"], r["hpd95"], in68, in95))
    return rows


# ---------- 부속 연구 (옵션으로만 켠다 — 등록된 모델·기본 --loco 는 위 경로 그대로) ----------
#
# --loco-obs single : 빠진 칩의 관측을 구간 p50 대신 그 1k 구간 A 행에서 섹터마다 사이클 k 개(--prep-k)를 뽑은 중앙값으로 —
#                     실전 prep k 회와 같은 흔들림. seed 고정(--seed), --reps 회 반복
# --dx 5000|10000   : 두 번째 dose(로그 51 §6). 정답 x 뒤 x+1..x+Δx 의 A 행(7섹터 × Δx)에 직선을 맞춘 기울기를 관측에 더한다.
#                     교정 칩은 같은 방법의 구간별 기울기 곡선이 구성원이다. 속도 배율 r 인 칩의 Δx 실제 사이클은 곡선 위 r·Δx 이므로
#                     관측 기울기는 r × (곡선 지점 x·r 에서 창 r·Δx 의 기울기) 와 맞댄다 — 기울기가 r 을 좁히는 정보가 된다
# A 행 세션은 docs/results/data/wear_curves/wear_curves_2026-09.md 의 재현 명령과 같다

A_SESSIONS = {
    "chip01": (("1790091548", "1790212214"), ()),
    "chip03": (("1790408609",), ()),
    "chip04": (("1790423530", "1790482991", "1790491294"), ((66654, 66671),)),
    "chip07": (("1790494073", "1790562456", "1790643103"), ()),
    "chip09": (("1790786787",), ()),
}
LONG_GAP = 1000                            # Δx 창 안에 이만큼 이어진 결측(모든 섹터 행 없음)이 있으면 그 점은 판정에서 뺀다
SLOPE_MIN_FILL = 0.5                       # 교정 쪽 기울기 창에 행이 이 비율 아래면 그 지점의 구성원은 없는 것으로 친다
BUCKETS = ((0, 3_000, "≤3k"), (3_000, 20_000, "3-20k"), (20_000, 50_000, "20-50k"), (50_000, 100_000, "50-100k"))


class ARows:
    """칩 하나의 A 행 소거 시간 (섹터 × 사이클, µs, 결측 NaN) 과 창 기울기용 누적합."""

    @classmethod
    def load(cls, chip):
        import numpy as np
        import wear_curves as wc
        if chip not in A_SESSIONS:
            raise SystemExit(f"{chip} 의 A 행 세션이 A_SESSIONS 에 없다")
        dirs, drop = A_SESSIONS[chip]
        paths = [REPO / "data" / "wear" / d for d in dirs]
        missing = [str(p) for p in paths if not (p / "A.txt").exists()]
        if missing:
            raise SystemExit(f"{chip} 의 A 행이 없다: {', '.join(missing)}")
        rows, _ = wc.load_sessions(paths, drop)
        e = np.full((7, max(c for c, _ in rows) + 1), np.nan)
        for (c, s), (te, _tp) in rows.items():
            if s in WORN:
                e[s, c] = te
        return cls(e)

    def __init__(self, e):
        """e: (7, 최대 사이클 + 1) 소거 시간 µs, 결측 NaN. 열 0 은 쓰지 않는다."""
        import numpy as np
        self.max_cycle = e.shape[1] - 1
        self.e = e
        ok = ~np.isnan(e)
        x = np.arange(self.max_cycle + 1, dtype=float)
        z = np.zeros((7, 1))
        v = np.where(ok, e, 0.0)
        self.cs = {k: np.concatenate([z, np.cumsum(a, axis=1)], axis=1) for k, a in
                   (("n", ok * 1.0), ("x", ok * x), ("xx", ok * x * x), ("e", v), ("xe", v * x), ("ee", v * v))}
        allmiss = (~ok).all(axis=0)
        allmiss[0] = False
        self.miss_run = self._runs(allmiss)

    @staticmethod
    def _runs(mask):
        out, start = [], None
        for i, m in enumerate(mask):
            if m and start is None:
                start = i
            elif not m and start is not None:
                out.append((start, i - 1))
                start = None
        if start is not None:
            out.append((start, len(mask) - 1))
        return out

    def has_long_gap(self, a, b):
        return any(min(b, z) - max(a, s) + 1 >= LONG_GAP for s, z in self.miss_run if s <= b and z >= a)

    def window_slope(self, a, length):
        """사이클 a..a+length-1 의 7섹터 행에 직선 하나 — (기울기 µs/사이클, σ, 채운 비율) 또는 None.

        σ = max(섹터별 기울기 표준편차/√7, 회귀 표준오차, 2%·|기울기|). µs/사이클은 수치로 ms/1k 와 같다."""
        import numpy as np
        b = a + length
        if a < 1 or b - 1 > self.max_cycle or length < 2:
            return None
        w = {k: v[:, b] - v[:, a] for k, v in self.cs.items()}
        n = w["n"].sum()
        if n < SLOPE_MIN_FILL * 7 * length:
            return None
        sx, sxx, se, sxe, see = (w[k].sum() for k in ("x", "xx", "e", "xe", "ee"))
        vx = sxx - sx * sx / n
        slope = (sxe - sx * se / n) / vx
        ssr = max(see - se * se / n - slope * (sxe - sx * se / n), 0.0)
        se_reg = math.sqrt(ssr / max(n - 2, 1) / vx)
        dx = w["n"] * w["xx"] - w["x"] ** 2
        good = (w["n"] >= 2) & (dx > 0)
        per = (w["n"][good] * w["xe"][good] - w["x"][good] * w["e"][good]) / dx[good]
        spread = float(np.std(per, ddof=1)) / math.sqrt(len(per)) if len(per) > 1 else 0.0
        sigma = max(spread, se_reg, SIGMA_FLOOR * abs(slope), 1e-9)
        return slope, sigma, n / (7 * length)

    def sample_obs(self, b, k, rng):
        """1k 구간 b 에서 섹터마다 사이클 k 개를 뽑은 소거 시간 중앙값 7개 (µs)."""
        import numpy as np
        out = []
        for s in WORN:
            seg = self.e[s, b:b + 1000]
            vals = seg[~np.isnan(seg)].tolist()
            out.append(statistics.median(rng.sample(vals, min(k, len(vals)))))
        return out


def posterior_dx(obs, mem, rate_range, slope_obs, slope_members, dx):
    """posterior 에 기울기 우도를 곱한 것. slope_obs = (기울기, σ) 는 눈금 적용 뒤, slope_members = [(ARows, 분모)]."""
    ll = curve_loglik(obs, mem)
    rs = [1.0] if rate_range <= 1 else [rate_range ** (-1 + 2 * i / (N_RATE - 1)) for i in range(N_RATE)]
    cache = {}
    logt = {}
    for xb in range(1, MAX_CYCLE + 1, 1000):
        c = xb + 499
        terms = []
        for r in rs:
            mb = int((c * r - 1) // 1000) * 1000 + 1
            if mb not in ll:
                continue
            key = (round(c * r), round(dx * r))
            if key not in cache:
                vals = []
                for arows, div in slope_members:
                    w = arows.window_slope(*key)
                    if w is not None:
                        vals.append((w[0] / div, w[1] / div))
                cache[key] = vals
            vals = cache[key]
            if not vals:
                continue
            ls = _logmeanexp([_logpdf(slope_obs[0], r * mu, r * s) for mu, s in vals])
            terms.append(ll[mb] + ls)
        if terms:
            logt[xb] = _logmeanexp(terms) + math.log(len(terms) / len(rs))
    m = max(logt.values())
    post = {b: math.exp(v - m) for b, v in logt.items()}
    z = sum(post.values())
    return {b: v / z for b, v in post.items()}


def loco_study(curves, fresh, scale, split_us, rate_range, obs_mode="p50", prep_k=3, seed=0, reps=20, dx=0,
               arows=None, cycles=LOCO_CYCLES):
    """부속 연구의 모의 블라인드. 행 = dict(칩, 무리, 정답, 반복, MAP, 68%, 95%, 포함 여부) · 뺀 점 = [(칩, 정답, 이유)]."""
    import random
    rows, skipped = [], []
    for chip in sorted(curves):
        rest = {c: v for c, v in curves.items() if c != chip}
        grp = group_of(fresh[chip], split_us)
        cal = [c for c in rest if group_of(fresh[c], split_us) == grp]
        if not cal:
            continue
        for cyc in cycles:
            b = (cyc - 1) // 1000 * 1000 + 1
            if b not in curves[chip]:
                continue
            slope_obs, slope_members = None, None
            if dx:
                if cyc + dx > MAX_CYCLE:
                    skipped.append((chip, cyc, f"x+Δx = {cyc + dx:,} > 100k"))
                    continue
                if arows[chip].has_long_gap(cyc + 1, cyc + dx):
                    skipped.append((chip, cyc, f"창 {cyc + 1:,}-{cyc + dx:,} 이 A 행 결측 구간에 걸림"))
                    continue
                w = arows[chip].window_slope(cyc + 1, dx)
                div = fresh[chip] if scale == "ratio" else 1.0
                slope_obs = (w[0] / div, w[1] / div)
                slope_members = [(arows[c], fresh[c] if scale == "ratio" else 1.0) for c in cal]
            n_rep = reps if obs_mode == "single" else 1
            rng = random.Random(f"{seed}:{chip}:{cyc}")
            for rep in range(n_rep):
                if obs_mode == "single":
                    worn = arows[chip].sample_obs(b, prep_k, rng)
                else:
                    worn = [p50 for _, p50, _ in curves[chip][b].values()]
                if dx:
                    obs = [v / fresh[chip] for v in worn] if scale == "ratio" else list(worn)
                    mem = members(rest, fresh, cal, scale)
                    post = posterior_dx(obs, mem, rate_range, slope_obs, slope_members, dx)
                    top = max(post, key=post.get)
                    h68, h95 = ranges(hpd(post, 0.68)), ranges(hpd(post, 0.95))
                else:
                    r = invert(fresh[chip], worn, rest, fresh, scale, split_us, rate_range)
                    top, h68, h95 = r["map"][0], r["hpd68"], r["hpd95"]
                rows.append({"chip": chip, "group": grp, "x": cyc, "rep": rep, "map": top, "h68": h68, "h95": h95,
                             "in68": any(a <= cyc <= z for a, z in h68), "in95": any(a <= cyc <= z for a, z in h95),
                             "slope": slope_obs[0] if slope_obs else None})
    return rows, skipped


def study_metrics(rows):
    """포함률(반복 평균) · 68% 바깥 폭 중앙값 · 바깥 폭/MAP 중앙값·90분위 · MAP/정답 중앙값."""
    if not rows:
        return None
    outer = [r["h68"][-1][1] - r["h68"][0][0] + 1 for r in rows]
    mapc = [r["map"] + 499.5 for r in rows]
    rel = sorted(o / m for o, m in zip(outer, mapc))
    return {"n_pts": len({(r["chip"], r["x"]) for r in rows}), "n": len(rows),
            "in68": sum(r["in68"] for r in rows) / len(rows), "in95": sum(r["in95"] for r in rows) / len(rows),
            "outer": statistics.median(outer), "rel50": statistics.median(rel), "rel90": rel[min(len(rel) - 1, int(0.9 * len(rel)))],
            "map_ratio": statistics.median(m / r["x"] for m, r in zip(mapc, rows))}


def print_study(rows, skipped, label):
    def line(name, sub):
        m = study_metrics(sub)
        if m is None:
            print(f"| {label} | {name} | 0 | — | — | — | — | — | — |")
            return
        print(f"| {label} | {name} | {m['n_pts']} | {m['in68']:.1%} | {m['in95']:.1%} | {m['outer']:,.0f} | "
              f"{m['rel50']:.2f} | {m['rel90']:.2f} | {m['map_ratio']:.2f} |")
    print("| 조건 | 부분 | 점 | 정답∈68 | 정답∈95 | 68% 바깥 폭 중앙값 | 바깥 폭/MAP 중앙값 | 90분위 | MAP/정답 중앙값 |")
    print("|---|---|---|---|---|---|---|---|---|")
    line("전체", rows)
    for g, name in (("fast", "빠른 무리"), ("slow", "느린 무리")):
        line(name, [r for r in rows if r["group"] == g])
    for lo, hi, name in BUCKETS:
        line(f"x {name}", [r for r in rows if lo < r["x"] <= hi])
    for g, name in (("fast", "빠른"), ("slow", "느린")):
        line(f"{name} · x 50-100k", [r for r in rows if r["group"] == g and 50_000 < r["x"] <= 100_000])
    for chip, cyc, why in skipped:
        print(f"  판정에서 뺀 점: {chip} x={cyc:,} — {why}")


def step_slope_counts(arows, fresh, split_us, dx):
    """칩별로 1k 구간 시작점마다 창 [b, b+Δx) 기울기 ≤ 0 인 구간 수 / 전체 (0-100k 안, 창이 서는 곳만)."""
    out = []
    for chip in sorted(arows):
        n = neg = 0
        for b in range(1, MAX_CYCLE - dx + 2, 1000):
            w = arows[chip].window_slope(b, dx)
            if w is None:
                continue
            n += 1
            neg += w[0] <= 0
        out.append((chip, group_of(fresh[chip], split_us), neg, n))
    return out


def pair_speed(curves, fresh, a, b, lo=1_000, hi=MAX_CYCLE):
    """a 가 b 보다 몇 배 빨리 늙나 — a(x) 와 b(x·r) 의 로그 배율 차 제곱 평균을 r 격자(로그 0.005 간격)에서 최소화.
    곡선은 1k 구간마다 섹터 p50 의 중앙값 ÷ 신품값. → (r, rmse, 맞춘 점 수). 겹치는 점이 30 미만이면 None."""
    def cv(c):
        return {k: statistics.median(v[1] for v in secs.values()) / fresh[c] for k, secs in curves[c].items()}
    A, B = cv(a), cv(b)
    top = max(B)
    best = None
    for i in range(-300, 301):
        r = math.exp(i * 0.005)
        err = []
        for x in range(lo + 500, hi, 1000):
            if x * r > top + 999:
                continue
            ya, yb = A.get(int((x - 1) // 1000) * 1000 + 1), B.get(int((x * r - 1) // 1000) * 1000 + 1)
            if ya and yb:
                err.append((math.log(ya) - math.log(yb)) ** 2)
        if len(err) >= 30 and (best is None or sum(err) / len(err) < best[1] ** 2):
            best = (r, math.sqrt(sum(err) / len(err)), len(err))
    return best


def rate_rule(curves, fresh, split_us):
    """(참고용 — 2026-10-01 [D48-60] 에서 기본 R 로 쓰지 않기로 했다: 교정 곡선 혼합이 이미 칩 산포를 품으므로 이 값은 두 번 센다)
    R 의 규칙 (로그 48 [D48-42]·[D48-53]): 무리 안 모든 쌍(r 은 a→b · b→a 양방향 로그 평균)의 |ln r| 평균 ÷ 1.13 = 개체 표준편차 σ, R = exp(√2 · 1.96 · σ).
    → (R, σ, [(a, b, r, rmse, n)])."""
    groups = defaultdict(list)
    for c in sorted(curves):
        groups[group_of(fresh[c], split_us)].append(c)
    pairs = []
    for chips in groups.values():
        for i, a in enumerate(chips):
            for b in chips[i + 1:]:
                ab, ba = pair_speed(curves, fresh, a, b), pair_speed(curves, fresh, b, a)
                if ab and ba:     # 기준 칩에 따라 겹치는 구간이 달라 비대칭이다 — 양방향 로그 평균
                    r = math.exp((math.log(ab[0]) - math.log(ba[0])) / 2)
                    pairs.append((a, b, r, max(ab[1], ba[1]), min(ab[2], ba[2])))
    sigma = statistics.mean(abs(math.log(p[2])) for p in pairs) / 1.13
    return math.exp(math.sqrt(2) * 1.96 * sigma), sigma, pairs


SYN_LEVELS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.68, 0.8, 0.9, 0.95)


def synthetic(curves, fresh, scale, split_us, rate_range, prep_k, n, seed=0, loo=False, runs_fix=True):
    """합성 복원 — 모델 가정대로 가짜 칩을 만들고 추론이 참값을 복원하는지 n 번. → {level: 포함률}.

    생성: 무리를 고르고 x ~ U(1, MAX_CYCLE)(사전과 같다) · r ~ 로그균등 [1/R, R] · 곡선 지점 M = x·r 에 구간이 있는 그 무리의
    교정 칩 하나를 정체로. prep 마다 섹터 0-6 을 그 칩 그 섹터의 N(p50, (p90-p10)/2.56) 에서 뽑는다 — 한 prep 의 섹터들은 같은
    칩·같은 r 을 공유한다. loo 면 정체 칩을 교정에서 빼고 추론한다. runs_fix=False 는 우도 수정 전(prep 전부를 관측 하나로)."""
    import random
    rng = random.Random(seed)
    groups = defaultdict(list)
    for c in sorted(curves):
        groups[group_of(fresh[c], split_us)].append(c)
    hit = defaultdict(int)
    done = 0
    while done < n:
        grp = rng.choice(sorted(groups))
        x = rng.randint(1, MAX_CYCLE)
        r = rate_range ** rng.uniform(-1, 1) if rate_range > 1 else 1.0
        mb = int((x * r - 1) // 1000) * 1000 + 1
        cands = [c for c in groups[grp] if mb in curves[c]]
        if not cands:
            continue
        chip = rng.choice(cands)
        cal = [c for c in groups[grp] if not (loo and c == chip)]
        if not cal:
            continue
        sec = curves[chip][mb]
        worn = []
        for _ in range(prep_k):
            for p10, p50, p90 in sec.values():
                sd = max((p90 - p10) / 2.5631, SIGMA_FLOOR * p50)
                worn.append(rng.gauss(p50, sd))
        div = fresh[chip] if scale == "ratio" else 1.0
        obs = [v / div for v in worn]
        mem = members({c: curves[c] for c in cal}, fresh, cal, scale)
        post = posterior(obs, mem, rate_range, prep_k if runs_fix else 1)
        for lv in SYN_LEVELS:
            if any(a <= x <= z for a, z in ranges(hpd(post, lv))):
                hit[lv] += 1
        done += 1
    return {lv: hit[lv] / n for lv in SYN_LEVELS}


def plot_synthetic(results, path):
    """명목 확률 대 실제 포함률 — 대각선에 붙으면 모델이 말하는 확률이 정직하다. results: [(제목, {라벨: {level: 률}})]."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    style = {"기본 · prep 5회": ("#2a78d6", "-"), "기본 · prep 1회": ("#eb6834", "-"),
             "prep 독립 · prep 5회": ("#8a8984", (0, (4, 3)))}
    fig, axes = plt.subplots(1, len(results), figsize=(5.2 * len(results), 4.8), sharey=True, facecolor="#fcfcfb")
    for ax, (title, series) in zip(axes if len(results) > 1 else [axes], results):
        ax.set_facecolor("#fcfcfb")
        ax.plot([0, 1], [0, 1], color="#c3c2b7", lw=1, zorder=1)
        for label, cov in series.items():
            color, ls = style[label]
            xs = list(cov)
            ys = [cov[k] for k in xs]
            ax.plot(xs, ys, color=color, ls=ls, lw=2, marker="o", ms=4, label=label, zorder=3)
        ax.set_title(title, fontsize=11, color="#0b0b0b", loc="left")
        ax.set_xlim(0, 1.08)
        ax.set_ylim(0, 1.02)
        ax.set_xlabel("모델이 말한 확률 (최고밀도 구간)", fontsize=9, color="#52514e")
        ax.grid(color="#ebeae6", lw=0.6)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color("#c3c2b7")
        ax.tick_params(colors="#52514e", labelsize=8)
    (axes[0] if len(results) > 1 else axes).set_ylabel("참값이 구간 안에 든 비율", fontsize=9, color="#52514e")
    (axes[0] if len(results) > 1 else axes).legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("합성 복원 — 대각선에 붙을수록 모델이 말한 확률이 정직하다 (각 500회)", fontsize=12, color="#0b0b0b", x=0.02, ha="left")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=160)


def main(argv=None):
    ap = argparse.ArgumentParser(description="수명 역산 1차 모델 — prep 소거 시간 → 누적 P/E 구간")
    ap.add_argument("logs", nargs="*", help="개봉 prep 세션 로그 (여러 개면 같은 칩의 반복 prep)")
    ap.add_argument("--loco", action="store_true", help="모의 블라인드 — 교정 칩을 하나씩 빼고 맞힌다")
    ap.add_argument("--scale", choices=("ms", "ratio"), default="ratio", help="소거 시간 눈금 (기본 ratio — 4칩 LOCO 36/46 대 19/46)")
    ap.add_argument("--rate-range", type=float, default=RATE_RANGE, help=f"속도 배율 r 의 범위 R (기본 {RATE_RANGE}). 1 이면 끔")
    ap.add_argument("--split-ms", type=float, default=40.0, help="빠른/느린 무리 경계, 신품 소거 ms (기본 40)")
    ap.add_argument("--curves", default=CURVES_GLOB, help="교정 표 glob")
    ap.add_argument("--loco-obs", choices=("p50", "single"), default="p50", help="부속 연구: 모의 블라인드 관측 (기본 p50 = 등록된 방식)")
    ap.add_argument("--prep-k", type=int, default=3, help="부속 연구: single 관측의 섹터당 사이클 수 (기본 3)")
    ap.add_argument("--seed", type=int, default=0, help="부속 연구: 난수 seed (기본 0)")
    ap.add_argument("--reps", type=int, default=20, help="부속 연구: single 관측 반복 횟수 (기본 20)")
    ap.add_argument("--dx", type=int, choices=(0, 1000, 2000, 3000, 5000, 10000), default=0, help="부속 연구: 두 번째 dose Δx (기본 0 = 등록된 방식)")
    ap.add_argument("--study", action="store_true", help="부속 연구: 모의 블라인드를 무리·x 구간별 요약표로 (옵션을 안 켜도 요약만 낸다)")
    ap.add_argument("--rate-rule", action="store_true", help="교정 표의 무리 안 모든 쌍에서 R 을 규칙대로 계산해 찍는다")
    ap.add_argument("--synthetic", type=int, metavar="N", help="합성 복원 — 가정대로 만든 가짜 칩 N 개로 포함률을 잰다 (prep 1·5회, 수정 전후, 교정 포함·제외)")
    ap.add_argument("--prep-indep", action="store_true", help="시험용: 따로 돌린 prep 을 독립 관측으로 친다 (기본은 prep 전부를 관측 하나로 — 처음 보는 칩에서 과신하지 않는다)")
    ap.add_argument("--plot", metavar="경로", help="--synthetic 결과 그림 (PNG)")
    ap.add_argument("--out", metavar="경로", help="추정 결과를 파일로도 쓴다 — 머리말에 git_rev · 인자 · 입력 로그 sha256 · 교정 표 (블라인드 기록용)")
    args = ap.parse_args(argv)

    curves, fresh = load_curves(args.curves), load_fresh()
    split = args.split_ms * 1000

    if args.rate_rule:
        R, sigma, pairs = rate_rule(curves, fresh, split)
        print(f"R 규칙 · 교정 칩 {sorted(curves)} · 경계 {args.split_ms:g}ms")
        for a, b, r, rmse, n in pairs:
            print(f"  {a} 대 {b}: r {r:.3f} (|ln r| {abs(math.log(r)):.3f}) · 맞춤 rmse {rmse:.3f} · {n}점")
        print(f"  개체 표준편차 σ {sigma:.3f} → R = exp(√2·1.96·σ) = {R:.2f}")
        return

    if args.synthetic:
        results = []
        for title, loo in (("교정에 정체 칩 포함", False), ("정체 칩을 교정에서 뺌", True)):
            series = {}
            for label, k, fix in (("기본 · prep 5회", 5, False), ("기본 · prep 1회", 1, False), ("prep 독립 · prep 5회", 5, True)):
                series[label] = synthetic(curves, fresh, args.scale, split, args.rate_range, k, args.synthetic, args.seed, loo, fix)
            results.append((title, series))
        lv = SYN_LEVELS
        print(f"합성 복원 · 눈금 {args.scale} · R {args.rate_range:g} · N {args.synthetic} · seed {args.seed} · 교정 칩 {sorted(curves)}")
        print("| 조건 | " + " | ".join(f"{int(v * 100)}%" for v in lv) + " |\n|---|" + "---|" * len(lv))
        for title, series in results:
            for label, cov in series.items():
                print(f"| {title} · {label} | " + " | ".join(f"{cov[v] * 100:.0f}" for v in lv) + " |")
        if args.plot:
            plot_synthetic(results, args.plot)
        return

    if args.loco and (args.study or args.loco_obs != "p50" or args.dx):
        arows = {c: ARows.load(c) for c in sorted(curves)} if (args.loco_obs == "single" or args.dx) else None
        label = f"{args.loco_obs}" + (f" k={args.prep_k}" if args.loco_obs == "single" else "") + f" · Δx {args.dx:,}"
        rows, skipped = loco_study(curves, fresh, args.scale, split, args.rate_range, args.loco_obs, args.prep_k,
                                   args.seed, args.reps, args.dx, arows)
        print(f"부속 연구 · 모의 블라인드 · 눈금 {args.scale} · R {args.rate_range:g} · 관측 {label}"
              + (f" · seed {args.seed} · 반복 {args.reps}" if args.loco_obs == "single" else ""))
        print_study(rows, skipped, label)
        if args.dx:
            print(f"창 기울기 ≤ 0 인 1k 구간 (Δx {args.dx:,}, 0-100k):")
            for chip, grp, neg, n in step_slope_counts(arows, fresh, split, args.dx):
                print(f"  {chip} ({grp}) {neg}/{n}")
            fast = [r for r in rows if r["group"] == "fast" and r["rep"] == 0]
            print(f"  빠른 무리 LOCO 점의 관측 기울기 ≤ 0: {sum(r['slope'] <= 0 for r in fast)}/{len(fast)}")
        return

    if args.loco:
        rows = loco(curves, fresh, args.scale, split, rate_range=args.rate_range)
        if not rows:
            raise SystemExit("같은 무리에 칩이 둘 이상 있어야 모의 블라인드가 된다")
        print(f"모의 블라인드 · 눈금 {args.scale} · 속도 배율 R {args.rate_range:g} · 경계 {args.split_ms:g}ms · 교정 칩 {sorted(curves)}")
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
    runs = sum(1 for p in args.logs if PREP_ERASE.search(Path(p).read_text(encoding="utf-8", errors="replace")))
    r = invert(ref, worn, curves, fresh, args.scale, split, args.rate_range, runs if args.prep_indep else 1)
    out = [f"입력 A  기준(32-127) 소거 중앙값 {ref / 1000:.1f}ms → {r['group']} 무리 (교정 {r['chips']}) · 눈금 {args.scale} · R {args.rate_range:g}",
           f"입력 B  마모 섹터 소거 {len(worn)}개 (prep {runs}회{' · 독립' if args.prep_indep else ''}): " + ", ".join(f"{v / 1000:.1f}" for v in worn) + " ms",
           f"입력 C  {program_check(program, r['group'])}",
           f"답      MAP {r['map'][0]:,}-{r['map'][1]:,} · 68% {fmt_ranges(r['hpd68'])} · 95% {fmt_ranges(r['hpd95'])}"]
    if r["outside_at_map"]:
        out.append(f"주의    MAP 구간 밴드 밖 관측 {r['outside_at_map']}/{r['n_obs']}" +
                   (" — 전부 밖: 교정 범위 밖이거나 무리 선택이 틀렸다" if r["outside_at_map"] == r["n_obs"] else ""))
    print("\n".join(out))
    if args.out:
        write_record(args.out, argv, args.logs, args.curves, out)


def write_record(path, argv, logs, curves_glob, out):
    """추정 결과 + 재현에 필요한 것(코드 · 인자 · 입력 · 교정 표)을 한 파일에. 블라인드에서 결과 커밋이 곧 기록이다."""
    import datetime, hashlib, subprocess, sys
    def git(*a):
        return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True).stdout.strip()
    dirty = git("status", "--porcelain", "--", "host/analysis/wear_inverse.py")
    head = [f"# 생성   {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')}",
            f"# 코드   git_rev {git('rev-parse', '--short', 'HEAD')}" + (" (wear_inverse.py 커밋 안 된 수정 있음)" if dirty else ""),
            "# 인자   " + " ".join(sys.argv[1:] if argv is None else argv),
            "# 입력"]
    head += [f"#   {hashlib.sha256(Path(p).read_bytes()).hexdigest()}  {p}" for p in logs]
    head += ["# 교정 표"] + [f"#   {Path(c).resolve().relative_to(REPO)}" for c in sorted(glob.glob(curves_glob))]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(head + [""] + out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
