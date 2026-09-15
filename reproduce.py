#!/usr/bin/env python3
"""reproduce.py — docs/build_reproduction.md §3(빌드)·§5(검증)를 순서대로 돌리고 채점한다.

실행:  python3 reproduce.py                 # 전체: g0 g2 prep g3-25 g3-45 g3-75 sim selftest
       python3 reproduce.py --only g3-25 sim
       python3 reproduce.py --vitis-only     # §6 빠른 재빌드 — Vivado 생략, ELF만 (g0e prep g3e-*)
       python3 reproduce.py --list

채점(§3.5): 단계마다 ① 명령 종료 코드 ② 로그의 완료 문구 ③ 산출물이 단계 시작 이후에 생겼는지
④ (Vivado) 타이밍 리포트 "constraints are met" ⑤ (Vivado) WNS/WHS·LUT/FF 기준표 대조 — ⑤ 불일치는 WARN.
① 만으로는 판정하지 않는다 — vitis -s 는 실패해도 0 을 돌려줄 수 있다.

백업: 단계 시작 전에 그 단계의 산출물(ELF·XSA·bit)만 build/_prev/<단계>/ 로 복사한다 (직전 1세대).
Vitis 빌드 스크립트가 워크스페이스를 통째로 지우고 시작하므로, 컴파일이 깨지면 이전 ELF 를 잃는다.
복원은 사람이 한다 — 실패 요약에 경로만 찍는다.

로그: build/logs/reproduce_<UTC>/<단계>.log + summary.txt.  보드 굽기(§4)는 하지 않는다.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
B = REPO / "build"
PREV = B / "_prev"

# §3.5 기준값 (영웅 PC, 2026-09-14 23:06). 다르면 실패가 아니라 WARN + 기록.
BASELINE = {                       # step: (WNS, WHS, LUTs, Registers)
    "g0":    (29.811, 0.096, 900, 1013),
    "g3-25": (5.366, 0.111, 912, 1035),
    "g3-45": (6.201, 0.105, 913, 1035),
    "g3-75": (2.957, 0.082, 913, 1035),
}


def vivado(tcl, *args):
    return ["vivado", "-mode", "batch", "-source", str(REPO / "fpga/scripts" / tcl)] + \
           (["-tclargs", *args] if args else [])


def vitis(py):
    return ["vitis", "-s", str(REPO / "ps/scripts" / py)]


def sim(tb, *rtl):
    out = "{log_dir}/" + tb + ".vvp"
    srcs = [tb + ".v", "unisim_stub.v"] + [f"../../fpga/rtl/{d}/*.v" for d in rtl]
    return f"iverilog -g2005 -o {out} {' '.join(srcs)} && vvp {out}"


# name → dict(cmd, cwd, env, artifacts, done(로그 완료 문구), rpt(Vivado 리포트 접두), default, tools)
# cmd 가 str 이면 셸로 돈다 (sim 의 glob·&&). artifacts 는 REPO 기준 상대경로.
STEPS = {
    "g0": dict(cmd=vivado("build_g0_loopback.tcl"), done="== all done:",
               artifacts=["build/vivado/g0_loopback.runs/impl_1/g0_wrapper.bit", "build/vivado/g0_loopback.xsa",
                          "build/vitis/g0_sweep/build/g0_sweep.elf", "build/vitis/g0_sweep/_ide/psinit/ps7_init.tcl"],
               rpt="build/vivado/g0_loopback.runs/impl_1/g0_wrapper", tools=["vivado", "vitis"]),
    "g2": dict(cmd=vivado("build_g2_jedec.tcl"), done="== done:",
               artifacts=["build/vivado_g2/g2_jedec.xsa", "build/vivado_g2/g2_jedec.runs/impl_1/g2_wrapper.bit"],
               rpt="build/vivado_g2/g2_jedec.runs/impl_1/g2_wrapper", tools=["vivado"]),
    "prep": dict(cmd=vitis("build_flash_prep.py"), done="== done:",
                 artifacts=["build/vitis_prep/flash_prep/build/flash_prep.elf"], tools=["vitis"]),
    "sim": dict(cmd=" && ".join([sim("tb_core_smoke", "core"), sim("tb_flash_smoke", "flash"),
                                 sim("tb_flash_spi_smoke", "flash"), sim("tb_g0_smoke", "core", "flash")]),
                cwd=REPO / "sim/smoke", done="PASS: all checks passed", done_count=4, tools=["iverilog", "vvp"]),
    "selftest": dict(cmd=" && ".join(["uv run python host/analysis/bathtub_analysis.py --selftest",
                                      "uv run python host/capture/chip_registry.py --selftest",
                                      "uv run python host/run/chip_pe.py --selftest"]),
                     done="selftest PASS", done_count=2,
                     artifacts=["build/plots/bathtub_selftest_sweep.png", "build/plots/bathtub_selftest_sweep_wrap.png"],
                     tools=["uv"]),
    # §7 "(선택)" 앱 — 기본 실행에는 없음. --only 로 지정
    "jedec": dict(cmd=vitis("build_flash_jedec.py"), done="== done:", default=False,
                  artifacts=["build/vitis_jedec/flash_jedec/build/flash_jedec.elf"], tools=["vitis"]),
    "smoke": dict(cmd=vitis("build_core_smoke.py"), done="== done:", default=False,
                  artifacts=["build/vitis_smoke/core_smoke/build/core_smoke.elf"], tools=["vitis"]),
    # §6 빠른 재빌드 — ELF 만 (XSA 는 있는 것을 쓴다). --vitis-only 가 고른다
    "g0e": dict(cmd=vitis("build_g0_sweep.py"), done="== done:", default=False,
                artifacts=["build/vitis/g0_sweep/build/g0_sweep.elf"], tools=["vitis"]),
}
for m in ("25", "45", "75"):
    STEPS[f"g3-{m}"] = dict(cmd=vivado("build_g3_chip.tcl", "all", m), done="== all done:",
                            artifacts=[f"build/vivado_g3_{m}/g3_chip_{m}.runs/impl_1/g3_wrapper.bit",
                                       f"build/vivado_g3_{m}/g3_chip_{m}.xsa",
                                       f"build/vitis_g3_{m}/g3_sweep/build/g3_sweep.elf"],
                            rpt=f"build/vivado_g3_{m}/g3_chip_{m}.runs/impl_1/g3_wrapper", tools=["vivado", "vitis"])
    STEPS[f"g3e-{m}"] = dict(cmd=vitis("build_g3_sweep.py"), env={"G3_MHZ": m}, done="== done", default=False,
                             artifacts=[f"build/vitis_g3_{m}/g3_sweep/build/g3_sweep.elf"], tools=["vitis"])

FULL = ["g0", "g2", "prep", "g3-25", "g3-45", "g3-75", "sim", "selftest"]
VITIS_ONLY = ["g0e", "prep", "g3e-25", "g3e-45", "g3e-75", "sim", "selftest"]


def backup(name, st):
    """빌드 산출물(ELF·XSA·bit)만 build/_prev/<name>/ 로. 직전 1세대만 남긴다."""
    srcs = [REPO / a for a in st.get("artifacts", []) if (REPO / a).exists()]
    if not srcs or not {"vivado", "vitis"} & set(st["tools"]):
        return None
    d = PREV / name
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    for s in srcs:
        shutil.copy2(s, d / s.name)
    rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                         capture_output=True, text=True).stdout.strip() or "?"
    (d / "manifest.txt").write_text(f"backed_up_utc={datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ}\n"
                                    f"git_rev_at_backup={rev}\n" +
                                    "".join(f"{s.relative_to(REPO)}  mtime={datetime.fromtimestamp(s.stat().st_mtime):%Y-%m-%d %H:%M:%S}\n"
                                            for s in srcs))
    return d


def grade_vivado(name, rpt):
    """§3.5: 타이밍 충족(실패) + 수치 기준표(경고). 반환 (fail_msgs, warn_msgs, note)."""
    t = REPO / f"{rpt}_timing_summary_routed.rpt"
    u = REPO / f"{rpt}_utilization_placed.rpt"
    if not t.exists():
        return [f"타이밍 리포트 없음: {t.relative_to(REPO)}"], [], ""
    txt = t.read_text(errors="replace")
    fails = [] if "All user specified timing constraints are met" in txt else ["타이밍 위반 — 이 비트로 측정 금지"]
    m = re.search(r"Design Timing Summary.*?\n\s+(-?[\d.]+)\s+(-?[\d.]+)\s+\d+\s+\d+\s+(-?[\d.]+)", txt, re.S)
    wns, whs = (float(m.group(1)), float(m.group(3))) if m else (None, None)
    luts = regs = None
    if u.exists():
        for line in u.read_text(errors="replace").splitlines():
            if line.startswith("| Slice LUTs"):
                luts = int(line.split("|")[2])
            elif line.startswith("| Slice Registers"):
                regs = int(line.split("|")[2])
    note = f"WNS={wns} WHS={whs} LUT={luts} FF={regs}" if wns is not None else "(PL 로직 없음)"
    warns = []
    if name in BASELINE and (wns, whs, luts, regs) != BASELINE[name]:
        warns.append(f"기준표와 다름 (기준 WNS={BASELINE[name][0]} WHS={BASELINE[name][1]} "
                     f"LUT={BASELINE[name][2]} FF={BASELINE[name][3]}) — 실패 아님, 로그에 적을 것")
    return fails, warns, note


def run_step(name, log_dir):
    st = STEPS[name]
    log = log_dir / f"{name}.log"
    prev = backup(name, st)
    t0 = time.time()
    cmd = st["cmd"]
    if isinstance(cmd, str):
        cmd = cmd.replace("{log_dir}", str(log_dir))
    env = {**os.environ, **st.get("env", {})}
    with log.open("w") as f:
        f.write(f"# {cmd if isinstance(cmd, str) else ' '.join(cmd)}\n# cwd={st.get('cwd', REPO)}\n\n")
        f.flush()
        rc = subprocess.run(cmd, cwd=st.get("cwd", REPO), env=env, shell=isinstance(cmd, str),
                            stdout=f, stderr=subprocess.STDOUT).returncode
    dt = time.time() - t0
    out = log.read_text(errors="replace")

    fails, warns, note = [], [], ""
    if rc != 0:
        fails.append(f"종료 코드 {rc}")
    n_done = out.count(st["done"])
    if n_done < st.get("done_count", 1):
        fails.append(f"완료 문구 '{st['done']}' {n_done}/{st.get('done_count', 1)}")
    if name in ("sim", "selftest") and re.search(r"^\s*(FAIL\b|.*: FAIL\b)", out, re.M):
        fails.append("출력에 FAIL 행")
    for a in st.get("artifacts", []):
        p = REPO / a
        if not p.exists():
            fails.append(f"산출물 없음: {a}")
        elif p.stat().st_mtime < t0:
            fails.append(f"산출물이 이번 실행 전 것: {a}")
    if "rpt" in st and not fails:
        f2, w2, note = grade_vivado(name, st["rpt"])
        fails += f2
        warns += w2
    status = "FAIL" if fails else "WARN" if warns else "PASS"
    return dict(name=name, status=status, secs=dt, msgs=fails + warns, note=note, log=log, prev=prev)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="+", metavar="STEP", help="지정한 단계만 (순서대로)")
    ap.add_argument("--vitis-only", action="store_true", help="§6 빠른 재빌드 — Vivado 생략, ELF 만")
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--no-selftest", action="store_true")
    ap.add_argument("--keep-going", action="store_true", help="실패해도 다음 단계 계속 (기본: 첫 실패에서 중단)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, v in STEPS.items():
            c = v["cmd"] if isinstance(v["cmd"], str) else " ".join(v["cmd"])
            print(f"{k:9s} {'' if v.get('default', True) else '(선택) '}{c}")
        return 0

    steps = args.only or (VITIS_ONLY if args.vitis_only else FULL)
    bad = [s for s in steps if s not in STEPS]
    if bad:
        sys.exit(f"모르는 단계: {bad} — --list 참고")
    if args.no_sim:
        steps = [s for s in steps if s != "sim"]
    if args.no_selftest:
        steps = [s for s in steps if s != "selftest"]

    # 도구 선검사 — 없으면 시작 전에 죽는다 (조용한 건너뛰기 없음)
    need = sorted({t for s in steps for t in STEPS[s]["tools"]})
    missing = [t for t in need if shutil.which(t) is None]
    if missing:
        sys.exit(f"PATH 에 없음: {missing}  (Vivado/Vitis 는 settings64.sh, iverilog 는 apt, uv 는 §1)")
    if any(STEPS[s]["cmd"][0] == "vivado" for s in steps if not isinstance(STEPS[s]["cmd"], str)) \
            and not os.environ.get("XILINX_VIVADO"):
        print("경고: XILINX_VIVADO 미설정 — tcl 이 PATH 의 vitis 로 대체한다", file=sys.stderr)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = B / "logs" / f"reproduce_{stamp}"
    log_dir.mkdir(parents=True)
    print(f"== reproduce {stamp}: {' '.join(steps)}\n== logs: {log_dir.relative_to(REPO)}")

    results = []
    for i, s in enumerate(steps):
        print(f"[{i + 1}/{len(steps)}] {s} ...", end=" ", flush=True)
        r = run_step(s, log_dir)
        results.append(r)
        print(f"{r['status']} ({r['secs']:.0f}s) {r['note']}")
        for m in r["msgs"]:
            print(f"      - {m}")
        if r["status"] == "FAIL":
            print(f"      로그: {r['log'].relative_to(REPO)}  (마지막 15줄)")
            for line in r["log"].read_text(errors="replace").splitlines()[-15:]:
                print(f"      | {line}")
            if r["prev"]:
                print(f"      이전 산출물: {r['prev'].relative_to(REPO)}/  (복원은 cp 로 직접)")
            if not args.keep_going:
                print(f"      중단 — 남은 단계: {' '.join(steps[i + 1:]) or '없음'}  (--keep-going 으로 계속)")
                break

    lines = [f"reproduce {stamp}", ""]
    for r in results:
        lines.append(f"{r['status']:4s} {r['name']:9s} {r['secs']:6.0f}s  {r['note']}" +
                     "".join(f"\n       - {m}" for m in r["msgs"]))
    n_fail = sum(r["status"] == "FAIL" for r in results)
    lines += ["", f"{len(results)}/{len(steps)} 단계 실행, FAIL {n_fail}, WARN {sum(r['status'] == 'WARN' for r in results)}"]
    (log_dir / "summary.txt").write_text("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    return 1 if n_fail or len(results) < len(steps) else 0


if __name__ == "__main__":
    sys.exit(main())
