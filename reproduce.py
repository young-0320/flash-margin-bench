#!/usr/bin/env python3
"""reproduce.py — docs/build_reproduction.md §3(빌드)·§5(검증)를 순서대로 돌리고 채점한다.

실행:  python3 reproduce.py                 # 전체: sim selftest g0 g2 prep id g3-25 g3-45 g3-75
       python3 reproduce.py --only g3-25 sim
       python3 reproduce.py --vitis-only     # §6 빠른 재빌드 — Vivado 생략, 검증 + ELF만
       python3 reproduce.py --list
       (Windows 는 `python reproduce.py` — 셸에 기대지 않으므로 cmd/PowerShell 어디서든 같다.
        Vivado/Vitis 는 settings64.bat 를 먼저 돌려 PATH·XILINX_VIVADO 를 잡아둘 것)

채점(§3.5): 단계마다 ① 명령 종료 코드 ② 로그의 완료 문구 ③ 산출물이 단계 시작 이후에 생겼는지
④ (Vivado) 타이밍 리포트 "constraints are met" ⑤ (Vivado) WNS/WHS·LUT/FF 기준표 대조 — ⑤ 불일치는 WARN.
여기에 ⑥ 빌드 파라미터(g3 의 steps·n_reads)가 로그에 찍힌 값과 맞는지 — ③ mtime 은 "다시 구웠다"만 말한다.
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


def tool(name):
    """실행 파일의 argv 앞부분. Windows 의 vivado/vitis 는 .bat 인데 CreateProcess 는 .bat 를
    직접 못 띄운다 → cmd /c 로 감싼다. shutil.which 는 PATHEXT 를 보고 .bat 를 찾아내므로
    선검사(§도구 선검사)만 통과하고 정작 실행에서 WinError 2 로 죽던 자리다."""
    p = shutil.which(name)
    if p and os.name == "nt" and p.lower().endswith((".bat", ".cmd")):
        return ["cmd", "/c", p]
    return [p or name]


def vivado(tcl, *args):
    # Tcl 은 Windows 에서도 '/' 를 받는다. 백슬래시는 Tcl 이스케이프와 섞이므로 as_posix 로 넘긴다
    return tool("vivado") + ["-mode", "batch", "-source", (REPO / "fpga/scripts" / tcl).as_posix()] + \
           (["-tclargs", *args] if args else [])


def vitis(py):
    return tool("vitis") + ["-s", (REPO / "ps/scripts" / py).as_posix()]


def sim(tb, *rtl):
    """iverilog → vvp 두 argv. 셸을 안 쓰므로 glob 을 여기서 편다 — cmd.exe 는 *.v 를 안 펴준다."""
    out = "{log_dir}/" + tb + ".vvp"
    srcs = [tb + ".v", "unisim_stub.v"] + \
           [p.as_posix() for d in rtl for p in sorted((REPO / "fpga/rtl" / d).glob("*.v"))]
    return [["iverilog", "-g2005", "-o", out, *srcs], ["vvp", out]]


# name → dict(cmd, cwd, env, artifacts, done(로그 완료 문구), rpt(Vivado 리포트 접두), default, tools)
# cmd 는 argv 리스트, 또는 순서대로 도는 argv 리스트의 리스트 (앞이 실패하면 멈춘다 = 셸의 &&).
# 셸은 쓰지 않는다 — cmd.exe/bash 의 glob·따옴표 차이가 그대로 버그가 된다. artifacts 는 REPO 기준 상대경로.
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
    "sim": dict(cmd=[c for tb in (("tb_core_smoke", "core"), ("tb_flash_smoke", "flash"),
                                  ("tb_flash_spi_smoke", "flash"), ("tb_g0_smoke", "core", "flash"))
                     for c in sim(*tb)],
                cwd=REPO / "sim/smoke", done="PASS: all checks passed", done_count=4, tools=["iverilog", "vvp"]),
    "selftest": dict(cmd=[["uv", "run", "python", p, "--selftest"]
                          for p in ("host/analysis/bathtub_analysis.py", "host/capture/chip_registry.py",
                                    "host/run/chip_pe.py")],
                     done="selftest PASS", done_count=2,
                     artifacts=["build/plots/bathtub_selftest_sweep.png", "build/plots/bathtub_selftest_sweep_wrap.png"],
                     tools=["uv"]),
    # §7 "(선택)" 앱 — 기본 실행에는 없음. --only 로 지정
    "jedec": dict(cmd=vitis("build_flash_jedec.py"), done="== done:", default=False,
                  artifacts=["build/vitis_jedec/flash_jedec/build/flash_jedec.elf"], tools=["vitis"]),
    "smoke": dict(cmd=vitis("build_core_smoke.py"), done="== done:", default=False,
                  artifacts=["build/vitis_smoke/core_smoke/build/core_smoke.elf"], tools=["vitis"]),
    "id": dict(cmd=vitis("build_flash_id.py"), done="== done:",
               artifacts=["build/vitis_id/flash_id/build/flash_id.elf"], tools=["vitis"]),
    # §6 빠른 재빌드 — ELF 만 (XSA 는 있는 것을 쓴다). --vitis-only 가 고른다
    "g0e": dict(cmd=vitis("build_g0_sweep.py"), done="== done:", default=False,
                artifacts=["build/vitis/g0_sweep/build/g0_sweep.elf",
                           "build/vitis/g0_sweep/_ide/psinit/ps7_init.tcl"],   # program_g0.tcl 이 쓴다
                tools=["vitis"]),
}
for m in ("25", "45", "75"):
    # build_g3_sweep.py 가 찍는 파라미터 줄. tcl 이 vitis 를 체인 호출하므로 g3-* 로그에도 남는다.
    # 2026-09-15 에 45·75 ELF 가 N=100 인 채 남아 세대가 섞였던 것을 mtime 은 못 잡는다 (로그 30 §9-3)
    _par = f"== done ({m}MHz, steps={56 * (1125 // int(m))}, n_reads=112)"
    STEPS[f"g3-{m}"] = dict(cmd=vivado("build_g3_chip.tcl", "all", m), done="== all done:", expect=[_par],
                            artifacts=[f"build/vivado_g3_{m}/g3_chip_{m}.runs/impl_1/g3_wrapper.bit",
                                       f"build/vivado_g3_{m}/g3_chip_{m}.xsa",
                                       f"build/vitis_g3_{m}/g3_sweep/build/g3_sweep.elf"],
                            rpt=f"build/vivado_g3_{m}/g3_chip_{m}.runs/impl_1/g3_wrapper", tools=["vivado", "vitis"])
    STEPS[f"g3e-{m}"] = dict(cmd=vitis("build_g3_sweep.py"), env={"G3_MHZ": m}, done="== done",
                             expect=[_par], default=False,
                             artifacts=[f"build/vitis_g3_{m}/g3_sweep/build/g3_sweep.elf"], tools=["vitis"])

# 검증(sim·selftest, 합쳐 10초 미만)이 앞이다 — 빌드는 20분이고, RTL 이 깨져 있으면
# 스모크 5초로 알 수 있는 것을 Vivado 16분 태우고 알게 된다 (문서 "RTL을 바꾸면 검증 루프부터")
# id 는 g2 XSA 를 쓰므로 g2 뒤, prep 옆이다. --mode sweep 이 이 ELF 를 요구하므로 선택이 아니다 —
# 빠뜨리면 "빌드는 8/8 PASS 인데 보드 앞에서 측정을 못 하는" 상태가 된다 (17초)
FULL = ["sim", "selftest", "g0", "g2", "prep", "id", "g3-25", "g3-45", "g3-75"]
VITIS_ONLY = ["sim", "selftest", "g0e", "prep", "id", "g3e-25", "g3e-45", "g3e-75"]


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
    warns = []
    if wns is not None:
        note = f"WNS={wns} WHS={whs} LUT={luts} FF={regs}"
    elif name in BASELINE:
        # 기준표가 있는 설계는 타이밍 경로가 반드시 있다 → 파싱 실패다. "PL 로직 없음" 과 섞지 않는다
        note = "수치 파싱 실패"
        warns.append(f"타이밍 리포트에서 WNS/WHS 를 못 읽었다 — 리포트 서식 변경 의심. "
                     f"{t.relative_to(REPO)} 를 직접 볼 것 (기준표 대조 건너뜀)")
    else:
        note = "(PL 로직 없음)"
    if name in BASELINE and wns is not None and (wns, whs, luts, regs) != BASELINE[name]:
        warns.append(f"기준표와 다름 (기준 WNS={BASELINE[name][0]} WHS={BASELINE[name][1]} "
                     f"LUT={BASELINE[name][2]} FF={BASELINE[name][3]}) — 실패 아님, 로그에 적을 것")
    return fails, warns, note


# 진행 표시에 쓸 이정표 줄: 우리 마커(== ) · Vivado 임플 단계(Phase n) · Vitis 컴파일([2/3])
MILESTONE = re.compile(r"^(== |Phase \d|\[\d+/\d+\]|Starting )")


def watch(proc, log, prefix):
    """자식이 도는 동안 같은 줄을 5초마다 다시 그린다 — 터미널 하나로 "도는 중인지"를 본다.
    자식 출력은 로그 파일로 가 있으므로 그 꼬리에서 이정표 줄을 주워 온다 (tail -f 를 대신한다).
    파이프로 빨아들이지 않는 이유: 그러면 인코딩·버퍼를 우리가 떠안는다. 반환값은 종료 코드."""
    t0 = time.time()
    while True:
        try:
            return proc.wait(timeout=5)     # 끝나면 즉시 빠져나온다 (sleep 과 달리 지연 없음)
        except subprocess.TimeoutExpired:
            pass
        if not sys.stdout.isatty():         # 리다이렉트·CI 면 \r 도배를 하지 않는다
            continue
        line = ""
        for ln in reversed(log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]):
            if MILESTONE.match(ln):
                line = ln[:58]
                break
        d = int(time.time() - t0)
        print(f"\r{prefix} {d // 60}:{d % 60:02d}  {line}".ljust(100)[:100], end="", flush=True)


def run_step(name, log_dir, prefix=""):
    st = STEPS[name]
    log = log_dir / f"{name}.log"
    prev = backup(name, st)
    t0 = time.time()
    cmds = st["cmd"]
    cmds = [[a.replace("{log_dir}", log_dir.as_posix()) for a in c]
            for c in (cmds if isinstance(cmds[0], list) else [cmds])]
    # PYTHONUTF8 은 부모 셸에 맡기지 않고 여기서 강제한다 — Windows 기본 로케일(cp949)이면
    # selftest 는 한글 출력을 인코딩하다, Vitis 내장 파이썬은 ps/src/*.c 의 한글 주석을 읽다 죽는다
    # (vivado.bat → vitis.bat 까지 그대로 상속된다). 리눅스는 이미 UTF-8 이라 무영향
    env = {**os.environ, "PYTHONUTF8": "1", **st.get("env", {})}
    # 로그는 utf-8 로 고정한다 — Windows 기본(cp949)에 맡기면 요약의 한글이 깨진다.
    # 자식 출력은 바이트 그대로 들어오므로 채점 문구(전부 ASCII)는 어느 쪽이든 안전하다.
    with log.open("w", encoding="utf-8") as f:
        f.write("".join(f"# {' '.join(c)}\n" for c in cmds) + f"# cwd={st.get('cwd', REPO)}\n\n")
        f.flush()
        rc = 0
        for c in cmds:
            proc = subprocess.Popen(c, cwd=st.get("cwd", REPO), env=env,
                                    stdout=f, stderr=subprocess.STDOUT)
            rc = watch(proc, log, prefix)
            if rc:                      # 셸의 && 와 같다 — 첫 실패에서 멈춘다
                break
    dt = time.time() - t0
    out = log.read_text(encoding="utf-8", errors="replace")

    fails, warns, note = [], [], ""
    if rc != 0:
        fails.append(f"종료 코드 {rc}")
    n_done = out.count(st["done"])
    if n_done < st.get("done_count", 1):
        fails.append(f"완료 문구 '{st['done']}' {n_done}/{st.get('done_count', 1)}")
    for e in st.get("expect", []):          # 내용 검증 — 산출물이 "무엇으로" 구워졌는지
        if e not in out:                    # (③ mtime 은 "다시 구웠다"만 말한다)
            fails.append(f"기대 문구 없음: {e!r} — 빌드 파라미터가 의도와 다르다")
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
    g = ap.add_mutually_exclusive_group()          # 함께 주면 --only 가 조용히 이겨 의도와 반대로 돈다
    g.add_argument("--only", nargs="+", metavar="STEP", help="지정한 단계만 (순서대로)")
    g.add_argument("--vitis-only", action="store_true", help="§6 빠른 재빌드 — Vivado 생략, ELF 만")
    ap.add_argument("--no-sim", action="store_true")
    ap.add_argument("--no-selftest", action="store_true")
    ap.add_argument("--keep-going", action="store_true", help="실패해도 다음 단계 계속 (기본: 첫 실패에서 중단)")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    if args.list:
        for k, v in STEPS.items():
            cs = v["cmd"] if isinstance(v["cmd"][0], list) else [v["cmd"]]
            c = " && ".join(" ".join(x) for x in cs)
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
    if not steps:                                 # 빈 목록을 성공으로 끝내지 않는다 — 아무것도 안 돌고
        sys.exit("실행할 단계가 없다 — --only 와 --no-* 가 서로를 지웠다")   # 초록이 뜨는 것이 최악이다

    # 도구 선검사 — 없으면 시작 전에 죽는다 (조용한 건너뛰기 없음)
    need = sorted({t for s in steps for t in STEPS[s]["tools"]})
    missing = [t for t in need if shutil.which(t) is None]
    if missing:
        sys.exit(f"PATH 에 없음: {missing}  (Vivado/Vitis 는 settings64.sh — Windows 는 settings64.bat, "
                 f"iverilog 는 apt, uv 는 §1)")
    if any("vivado" in STEPS[s]["tools"] for s in steps) and not os.environ.get("XILINX_VIVADO"):
        print("경고: XILINX_VIVADO 미설정 — tcl 이 PATH 의 vitis 로 대체한다", file=sys.stderr)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_dir = B / "logs" / f"reproduce_{stamp}"
    log_dir.mkdir(parents=True)
    print(f"== reproduce {stamp}: {' '.join(steps)}\n== logs: {log_dir.relative_to(REPO)}")

    results = []
    for i, s in enumerate(steps):
        prefix = f"[{i + 1}/{len(steps)}] {s}"
        tty = sys.stdout.isatty()
        if tty:
            print(f"{prefix} ...", end="", flush=True)
        r = run_step(s, log_dir, prefix)
        results.append(r)
        line = f"{prefix} {r['status']} ({r['secs']:.0f}s) {r['note']}"
        print(f"\r{line}".ljust(100) if tty else line)   # 진행 줄을 같은 자리에서 덮어쓴다
        for m in r["msgs"]:
            print(f"      - {m}")
        if r["status"] == "FAIL":
            print(f"      로그: {r['log'].relative_to(REPO)}  (마지막 15줄)")
            for line in r["log"].read_text(encoding="utf-8", errors="replace").splitlines()[-15:]:
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
    (log_dir / "summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n" + "\n".join(lines))
    return 1 if n_fail or len(results) < len(steps) else 0


if __name__ == "__main__":
    sys.exit(main())
