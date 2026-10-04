# pe_end.py — PE 종료 뒤 기계적 갱신 (워크플로 13). 1단계는 build/pe_end/<chip>/ 에만 쓰고, 사람이 훑어본 뒤 --promote 로 승격한다
#
# 사용: uv run python host/analysis/pe_end.py --chip chip18                  # 상온 · 교정에 넣는다
#       uv run python host/analysis/pe_end.py --chip chip12 --no-calib       # 상온 · 교정에서 뺀다 (곡선 이름 _nocal)
#       uv run python host/analysis/pe_end.py --chip chip17 --temp           # 온도 런 · 교정 밖 (곡선 이름 _<마모 평균 °C>C)
#       덧붙임: --drop-cycles A-B (반복 · wear_curves.py 로 넘긴다) · --from <보드 B 묶음 폴더>
#       uv run python host/analysis/pe_end.py --chip chip18 --promote [--overwrite]
#
# 1단계: 세션 찾기(plan.txt 의 「칩 : <chip>」, A.txt 있는 폴더) → raw 를 data/ 로 (덮지 않음 · 다르면 멈춤) → 없는 analysis.json 생성 →
#        1k 곡선(wear_curves.py) → 체크포인트 CSV(상온 wear_checkpoint_csv.py · 온도 temp_wear_summary.py) → 마모 뒤 newchip 현장 역산 →
#        manifest.json · 요약
# 2단계: 산출물 → docs/results/ (내용이 다른 파일이 있으면 --overwrite 없이는 멈춤) → 교정 칩이면 칩별 곡선 그림 → 한눈 표 md·그림
# 이름의 <YYYY-MM> 은 마지막 체크포인트 스윕의 달

import argparse
import csv
import filecmp
import glob
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import wear_checkpoint_csv as wcc                           # noqa: E402

ANALYSIS = REPO / "host" / "analysis"
TEMP_LOGS = lambda chip: (f"temp_{chip}_*T??????Z.csv", f"temp_{chip}_*T??????Z_events.txt")   # temp_logger.py 원본만 — 요약 산출물(temp_<chip>_hourly.csv 등)은 아니다
TABLE_MD = "wear_checkpoint_table_2026-10.md"               # 한눈 표 — 이름은 승격본 그대로
TABLE_PNG = "wear_checkpoint_width_program_2026-10.png"
RATIO_PNG = "wear_ratio_curves_calib.png"                   # 교정 칩 배율 겹침 — 교정 칩이 늘 때마다 다시 그린다
RATIO_MARK = (1.63, "chip06 관측 (블라인드, 신품의 1.63배)")    # 10/2 그림과 같은 관측선
HUMAN = ["8·9 해석 문서 docs/results/wear/<축>_<chip>.md 와 results README 해석 목록 한 줄",
         "3 수치 md (같은 이름 .md) — 표·세션·재현 명령, 사건 각주 (inverse.txt 는 현장 역산 절 재료)",
         "11 등록부 용도 칸 · 13 S-1 §15 판정 · 14 보고서 재료 · 15 로그 48 · 16 다른 해석 문서의 상호참조",
         "12 data/README.md 보관 현황 한 행 (1단계 요약의 제안 문구)"]


def plan_chip(d):
    """plan.txt → 칩 라벨. 마모 그룹 0~6 이 아닌 세션(인수 시험 TB 1000~1006)은 None — 곡선에 섞이면 안 된다."""
    p = Path(d) / "plan.txt"
    txt = p.read_text(encoding="utf-8") if p.exists() else ""
    m = re.search(r"^칩\s*:\s*(chip\d+)\s", txt, re.M)
    return m[1] if m and re.search(r"^마모 섹터\s*:\s*0~6\s", txt, re.M) else None


def find_sessions(chip, roots, deep=False):
    """roots 아래 세션 폴더 중 plan.txt 의 칩이 chip 이고 A.txt 가 있는 것 → 세션 번호 순. 같은 번호는 앞 root 가 이긴다."""
    found = {}
    for root in roots:
        dirs = [p.parent for p in Path(root).rglob("plan.txt")] if deep else Path(root).glob("*/")
        for d in dirs:
            if d.name.isdigit() and d.name not in found and (d / "A.txt").exists() and plan_chip(d) == chip:
                found[d.name] = d
    return [found[k] for k in sorted(found, key=int)]


def same(a, b):
    return filecmp.cmp(a, b, shallow=True)


def copy_raw(chip, sessions, file_roots, data, deep=False):
    """세션 폴더 · sweep/session/temp 파일 → data/. 이미 있으면 같은지만 본다 — 다르면 아무것도 옮기기 전에 멈춘다."""
    plan = []
    for s in sessions:
        for f in s.rglob("*"):
            if f.is_file():
                plan.append((f, data / "wear" / s.name / f.relative_to(s)))
    for root in file_roots:
        for pat in (f"sweep_{chip}_*", f"session_{chip}_*", *TEMP_LOGS(chip)):
            for f in (Path(root).rglob(pat) if deep else Path(root).glob(pat)):
                if f.is_file():
                    plan.append((f, data / f.name))
    plan = [(src, dst) for src, dst in plan if src.resolve() != dst.resolve()]
    clash = [str(dst) for src, dst in plan if dst.exists() and not same(src, dst)]
    if clash:
        raise SystemExit("data/ 에 내용이 다른 같은 이름 파일이 있다 — 멈춘다:\n  " + "\n  ".join(clash))
    copied = 0
    for src, dst in plan:
        if not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1
    return copied


def checkpoints(sessions):
    rows = {}
    for s in sessions:
        p = Path(s) / "checkpoints.csv"
        if p.exists():
            rows.update({int(r["cycle"]): r for r in csv.DictReader(p.open(newline="", encoding="utf-8"))})
    if not rows:
        raise SystemExit("C 행이 없다 — 체크포인트를 하나도 재지 않은 세션들이다")
    return [rows[c] for c in sorted(rows)]


def month_of(sweep_csv):
    m = re.search(r"_(\d{4})(\d{2})\d{2}T\d{6}Z\.csv$", sweep_csv)
    return f"{m[1]}-{m[2]}"


def run(*args, out=None):
    """분석 스크립트를 같은 파이썬으로. 출력은 화면에 그대로 · out 이 있으면 stdout 을 파일로도."""
    p = subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True)
    sys.stdout.write(p.stdout)
    sys.stderr.write(p.stderr)
    if p.returncode:
        raise SystemExit(f"실패: {Path(str(args[0])).name} (종료 {p.returncode})")
    if out:
        Path(out).write_text(p.stdout, encoding="utf-8")
    return p


def cycle_weighted_mean(intervals_csv):
    for r in csv.DictReader(open(intervals_csv, newline="", encoding="utf-8")):
        if r["label"] == "마모 구간 전체 (사이클 가중)":
            return float(r["mean_c"])
    raise SystemExit(f"{intervals_csv} 에 사이클 가중 평균 행이 없다")


def stage(chip, temp=False, no_calib=False, drops=(), src=None, root=REPO):
    data, out = root / "data", root / "build" / "pe_end" / chip
    sess_roots = [Path(src)] if src else [root / "build" / "logs" / "wear"]
    file_roots = [Path(src)] if src else [root / "build" / "data"]
    found = {d.name: d for d in find_sessions(chip, [data / "wear"])}       # 이미 옮긴 것 + build·묶음에만 있는 것
    found.update({d.name: d for d in find_sessions(chip, sess_roots, deep=bool(src))})
    found = [found[k] for k in sorted(found, key=int)]
    if not found:
        raise SystemExit(f"{chip} 세션이 없다 — {', '.join(map(str, sess_roots))} · data/wear 의 plan.txt 를 확인")
    print(f"{chip} 세션 {len(found)}개: " + " · ".join(d.name for d in found))
    print(f"raw → data/: 새로 옮김 {copy_raw(chip, found, file_roots, data, deep=bool(src))}개")
    sessions = [data / "wear" / d.name for d in found]

    for s in wcc.session_logs(chip, data):                  # 예전 래퍼는 analysis.json 을 안 남겼다 — 같은 CSV 에서 다시 만든다
        if not (data / s["sweep"].replace(".csv", ".analysis.json")).exists():
            run(ANALYSIS / "bathtub_analysis.py", "--json", data / s["sweep"])
    temps = sorted(glob.glob(str(data / TEMP_LOGS(chip)[0])))
    if temp and not temps:
        raise SystemExit(f"--temp 인데 data/{TEMP_LOGS(chip)[0]} 가 없다")
    if not temp and temps:
        print(f"주의: data/ 에 {chip} 온도 로그 {len(temps)}개가 있다 — 온도 런이면 --temp", file=sys.stderr)

    if out.exists():
        shutil.rmtree(out)
    (out / "tmp").mkdir(parents=True)
    cps = checkpoints(sessions)
    last = cps[-1]
    ym = month_of(last["sweep_csv"])
    curves = out / "tmp" / "wear_curves.csv"
    run(ANALYSIS / "wear_curves.py", "--chip", chip, *sessions, *[f"--drop-cycles={d}" for d in drops], "-o", curves)

    files = {}                                              # 산출물 이름 → docs/results/ 아래 자리
    if temp:
        run(ANALYSIS / "temp_wear_summary.py", "--chip", chip, "--sessions", *sessions, "--temp", data / TEMP_LOGS(chip)[0],
            "--curves", curves, "--outdir", out / "tmp", "--plotdir", out / "tmp")
        tag = f"_{round(cycle_weighted_mean(out / 'tmp' / f'temp_{chip}_intervals.csv'))}C"
        for a, b, dest in ((f"wear_temp_{chip}.csv", f"wear_endurance_{chip}_{ym}.csv", "data/wear"),
                           (f"temp_{chip}_intervals.csv", f"temp_{chip}_intervals_{ym}.csv", "data"),
                           (f"temp_{chip}_hourly.csv", f"temp_{chip}_hourly_{ym}.csv", "data"),
                           (f"temp_{chip}_timeline.png", f"temp_{chip}_timeline_{ym}.png", "plots"),
                           (f"wear_temp_{chip}.png", f"wear_temp_{chip}_{ym}.png", "plots")):
            (out / "tmp" / a).rename(out / b)
            files[b] = dest
    else:
        tag = "_nocal" if no_calib else ""
        name = f"wear_endurance_{chip}_{ym}.csv"
        run(ANALYSIS / "wear_checkpoint_csv.py", "--chip", chip, *sessions, "--data", data, "-o", out / name)
        files[name] = "data/wear"
    name = f"wear_curves_{chip}{tag}_{ym}.csv"
    curves.rename(out / name)
    files[name] = "data/wear_curves"

    last_t = wcc.utc(re.search(r"_(\d{8}T\d{6}Z)\.csv$", last["sweep_csv"])[1])
    after = [s for s in wcc.session_logs(chip, data) if s["erase"] and s["t"] > last_t]
    if after:
        log = glob.glob(str(data / f"session_{chip}_*_{after[-1]['batch']}.log"))[0]
        run(ANALYSIS / "wear_inverse.py", log, out=out / "inverse.txt")
    for r in (cps[0], cps[-1]):                             # 마진 전후 한 쌍 — 첫 · 마지막 체크포인트의 욕조 그림
        png = root / "build" / "plots" / f"bathtub_{r['sweep_csv'][:-4]}.png"
        if not png.exists():                                # 보드 B 묶음 등 — 같은 CSV 에서 다시 그린다
            run(ANALYSIS / "bathtub_analysis.py", data / r["sweep_csv"])
        shutil.copy2(png, out / png.name)
        files[png.name] = "plots"
    shutil.rmtree(out / "tmp")

    calib = not temp and not no_calib
    man = {"chip": chip, "temp": temp, "no_calib": no_calib, "calib": calib, "drop_cycles": list(drops),
           "sessions": [d.name for d in found], "month": ym, "files": files}
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")

    sweeps = sorted(s["batch"] for s in wcc.session_logs(chip, data))
    print(f"\n── {out.relative_to(root)}/ ──")
    for name, dest in files.items():
        print(f"  {name}  → docs/results/{dest}/")
    print(f"  inverse.txt (현장 역산 — 승격하지 않음)" if after else "  마모 뒤 newchip 없음 — 현장 역산 생략")
    print(f"  교정: {'넣음' if calib else '뺌 (' + tag.lstrip('_') + ')'}")
    print(f"\ndata/README 보관 현황 제안: `sweep_{chip}_<UID>_{sweeps[0][:8]}-{sweeps[-1][:8]}` · `wear/` "
          + " · ".join(f"`{d.name}`" for d in found))
    print(f"\n훑어본 뒤: uv run python host/analysis/pe_end.py --chip {chip} --promote")


def text_same(a, b):
    return Path(a).read_bytes().replace(b"\r\n", b"\n") == Path(b).read_bytes().replace(b"\r\n", b"\n")


def put(src, dst):
    """스크립트가 낸 바이트 그대로. 줄끝만 다르고 내용이 같으면 쓰지 않는다 — 승격본의 줄끝은 스크립트마다 다르다(CRLF · LF)."""
    if dst.exists() and text_same(src, dst):
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return True


def promote(chip, overwrite=False, root=REPO):
    out, res = root / "build" / "pe_end" / chip, root / "docs" / "results"
    mp = out / "manifest.json"
    if not mp.exists():
        raise SystemExit(f"{mp} 가 없다 — 먼저 pe_end.py --chip {chip}")
    man = json.loads(mp.read_text(encoding="utf-8"))
    plan = [(out / name, res / dest / name) for name, dest in man["files"].items()]
    twins = [str(q.relative_to(root)) for name, dest in man["files"].items() if dest == "data/wear_curves"
             for q in (res / dest).glob(f"wear_curves_{chip}_*.csv") if q.name != name]
    if twins:                                               # 교정 glob 에 두 번 들거나 중복이 된다 — 덮기로 풀지 않는다
        raise SystemExit(f"{chip} 곡선이 다른 이름으로 이미 있다 — 하나만 남기고(git mv · rm) 다시:\n  " + "\n  ".join(twins))
    clash = [str(d.relative_to(root)) for s, d in plan if d.exists() and not text_same(s, d)]
    if clash and not overwrite:
        raise SystemExit("승격 자리에 내용이 다른 파일이 있다 (사람이 고친 note 일 수 있다) — 보고 --overwrite:\n  " + "\n  ".join(clash))
    for s, d in plan:
        print(f"  {'→' if put(s, d) else '='} {d.relative_to(root)}")

    if man["calib"]:                                        # y 축이 전 칩 공통이라 새 칩이 들면 다른 칩 그림도 바뀐다 — 전부 다시
        run(ANALYSIS / "plot_wear_curves.py", "--per-chip", out / "plots")
        for p in sorted((out / "plots").glob("wear_curves_*.png")):
            put(p, res / "plots" / p.name)
        run(ANALYSIS / "plot_wear_curves.py", "--ratio", "--mark", RATIO_MARK[0], "--mark-label", RATIO_MARK[1], "-o", out / RATIO_PNG)
        put(out / RATIO_PNG, res / "plots" / RATIO_PNG)       # 현행 교정 묶음 — wear_ratio_curves_2026-10.png 는 10/2 교정 5칩 기록으로 둔다
    run(ANALYSIS / "wear_checkpoint_table.py", "--plot", out / TABLE_PNG)
    put(out / TABLE_PNG, res / "plots" / TABLE_PNG)         # 표 md 는 plots/ 를 보고 그림 링크를 단다 — 그림 먼저
    run(ANALYSIS / "wear_checkpoint_table.py", "-o", out / TABLE_MD)
    put(out / TABLE_MD, res / "data" / "wear" / TABLE_MD)
    print("\n남은 것 (사람 — 워크플로 13 번호):")
    for h in HUMAN:
        print(f"  · {h}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="PE 종료 뒤 기계적 갱신 — 1단계 build/pe_end/<chip>/ · 2단계 --promote")
    ap.add_argument("--chip", required=True)
    ap.add_argument("--temp", action="store_true", help="온도 런 — 교정 밖, 곡선 이름에 마모 평균 온도")
    ap.add_argument("--no-calib", action="store_true", help="상온이지만 교정에서 뺀다 — 곡선 이름 _nocal")
    ap.add_argument("--drop-cycles", action="append", default=[], metavar="A-B", help="1k 곡선에서 뺄 사이클 (반복)")
    ap.add_argument("--from", dest="src", help="raw 묶음 폴더 (보드 B) — 기본은 build/logs/wear · build/data")
    ap.add_argument("--promote", action="store_true", help="2단계 — 산출물을 docs/results/ 로")
    ap.add_argument("--overwrite", action="store_true", help="--promote 에서 내용이 다른 파일을 덮는다")
    a = ap.parse_args(argv)
    if a.promote:
        promote(a.chip, a.overwrite)
    else:
        stage(a.chip, a.temp, a.no_calib, a.drop_cycles, a.src)


if __name__ == "__main__":
    main()
