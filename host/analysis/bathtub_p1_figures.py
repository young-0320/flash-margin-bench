# bathtub_p1_figures.py — v1 25MHz 욕조를 끊긴 축(P1)으로 다시 그린다 (로그 55 [D55-3] · 피드백 1 · 2 · 4)
#
# 사용: uv run python host/analysis/bathtub_p1_figures.py
#
# 입력: data/sweep_<chip>[_<UID>]_<UTC>.csv — 25MHz(2520 스텝) 런만. 고르기 · 덩어리 찾기는 bathtub_stats.analyze 그대로
# 출력: build/bathtub/v1/
#   p1_chip_<chip>.png          칩마다 한 장 — 전 런(옅은 선) + 칩 평균(진한 선)
#   p1_run_<chip>_<UTC>.png     게재 런 한 장 (chip01 7/8)
#   p1_walls_<chip>_<UTC>.png   같은 런의 좌우 벽 겹침 (오른쪽 벽을 뒤집어 포갬)
#
# 방향 = bathtub_analysis.py 와 같다 — 바닥이 가운데, 오류 덩어리가 양 끝으로 갈린다. 덩어리 중점(첫 · 끝 스텝의 중점)을
#   0ps(= 40,000ps, 위상축은 원형)에 둔다. x축은 끊는다: 왼쪽 패널 0 - W, 오른쪽 패널 40,000-W - 40,000ps, W = 1,000ps.
#   가운데 바닥은 안 그리고 길이를 화살표와 수치로 적는다
#   주의 — 이 방향에서 욕조 왼쪽 벽은 덩어리의 오른쪽 벽(통계표 · 로그 55 의 R)이고 욕조 오른쪽 벽이 덩어리의 왼쪽 벽(L)이다.
#   패널 제목에 둘 다 적는다
# 오류 0 스텝 = 측정 한계(1/n_bits) 높이에 × 로 찍는다 — 로그 축에 0 을 못 찍어서다
# 칩 평균 = 스텝별 BER 의 런 평균. 오류 0 인 런도 0 으로 넣는다(빼면 평균이 위로 쏠린다). 평균이 0 인 스텝은 1/Σn_bits 에 ×
#   덩어리 길이가 짝 · 홀이냐에 따라 런의 중점이 반 스텝(약 8ps) 어긋난다 — 평균의 x 는 런 x 의 평균이다
# 반 덩어리가 W 를 넘는 런이 있으면 그림에 「잘림」 경고를 적는다

import argparse
import glob
from collections import defaultdict
from pathlib import Path

import numpy as np

from bathtub_stats import DATA, NAME, N_STEPS, REPO, SAMPLE, analyze
from monte_carlo_sweep_params import BASELINE, INK, INK2, MUTED, RAMP, SURFACE, _style_axes

OUT = REPO / "build" / "bathtub" / "v1"
W_PS = 1000.0             # 한쪽 패널 폭 (로그 55 §5)
ARROW_UP = 3.0            # 바닥 길이 화살표의 높이 = 런의 0 오류 높이(1/n_bits) × 이 값
WARN = "#c0392b"          # 「잘림」 경고 테두리


def curve(r):
    """런 → (x, ber, 0 오류 높이). x = 덩어리 중점 기준 ps, 양수 = 덩어리 오른쪽 절반(욕조 왼쪽 패널)."""
    mid = (r["n_block"] - 1) / 2
    h = int(W_PS / r["dphi"]) + 1
    k = np.arange(int(np.floor(mid)) - h, int(np.floor(mid)) + h + 1)
    return (k - mid) * r["dphi"], r["e"][(r["first_nz_step"] + k) % N_STEPS] / r["n_bits_per_step"], 1 / r["n_bits_per_step"]


def half_ps(r):
    return r["n_block"] * r["dphi"] / 2


def floor_ps(r):
    return (N_STEPS - r["n_block"]) * r["dphi"]


def panels(plt, title):
    """끊긴 축 두 패널. 반환 (fig, 왼쪽, 오른쪽, UI ps)."""
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    fig, (al, ar) = plt.subplots(1, 2, sharey=True, figsize=(10.5, 4.8))
    fig.subplots_adjust(left=0.08, right=0.98, top=0.84, bottom=0.21, wspace=0.07)
    for ax in (al, ar):
        _style_axes(fig, ax)
        ax.set_yscale("log")
        ax.spines["top"].set_visible(False)
    ar.spines["left"].set_visible(False)
    ar.tick_params(left=False, which="both")
    al.set_ylabel("BER", color=INK2)
    brk = dict(marker=[(-1, -2), (1, 2)], markersize=10, linestyle="none", color=INK2, mec=INK2, mew=1.2, clip_on=False)
    for x in (-0.012, 0.012):                            # // 끊김 표시 — 두 패널 사이 x축 위
        al.plot([1.035 + x], [0], transform=al.transAxes, **brk)
    al.set_title("욕조 왼쪽 벽 = 덩어리의 오른쪽 벽 (표의 R)", color=INK2, fontsize=9)
    ar.set_title("욕조 오른쪽 벽 = 덩어리의 왼쪽 벽 (표의 L)", color=INK2, fontsize=9)
    fig.suptitle(title, color=INK, fontsize=11)
    fig.supxlabel("위상 (ps) — 덩어리 중점 = 0 = 40,000 · 가운데 바닥은 생략", color=INK2, fontsize=9, y=0.085)
    return fig, al, ar


def split(x, y, ui):
    """덩어리 중점 기준 (x, y) → 왼쪽 패널 (x ≥ 0), 오른쪽 패널 (x ≤ 0 을 ui + x 로). x = 0 은 양쪽에 다 찍힌다."""
    lo, hi = x >= 0, x <= 0
    return (x[lo], y[lo]), (ui + x[hi], y[hi])


def draw(al, ar, x, ber, zero_y, ui, **kw):
    """한 곡선 — 오류 있는 스텝은 선, 오류 0 스텝은 zero_y 높이에 ×."""
    zkw = dict(marker="x", ls="none", color=kw.pop("zcolor", MUTED), ms=kw.pop("zms", 4), alpha=kw.get("alpha", 1))
    y = np.where(ber > 0, ber, np.nan)
    z = np.where(ber > 0, np.nan, zero_y)
    for ax, (px, py), (_, pz) in zip((al, ar), split(x, y, ui), split(x, z, ui)):
        ax.plot(px, py, **kw)
        ax.plot(px, pz, **zkw)


def finish(plt, fig, al, ar, ui, ymin, y_arrow, xa, xb, text, trunc, out_png):
    """축 범위 · 범례(그림 아래) · 바닥 화살표(왼쪽 패널 xa → 오른쪽 패널 xb, 높이 y_arrow) · 「잘림」 경고 · 저장."""
    from matplotlib.patches import ConnectionPatch
    al.set_xlim(0, W_PS)
    ar.set_xlim(ui - W_PS, ui)
    al.set_ylim(ymin / 2, 1)
    leg = fig.legend(*al.get_legend_handles_labels(), frameon=False, fontsize=8.5, loc="lower center", ncol=4)
    for t in leg.get_texts():
        t.set_color(INK2)
    xa, xb = min(xa, W_PS), max(xb, ui - W_PS)
    fig.add_artist(ConnectionPatch(xyA=(xa, y_arrow), coordsA=al.transData, xyB=(xb, y_arrow), coordsB=ar.transData,
                                   arrowstyle="<->", color=INK2, lw=1.2))
    pa = fig.transFigure.inverted().transform(al.transData.transform((xa, y_arrow)))
    pb = fig.transFigure.inverted().transform(ar.transData.transform((xb, y_arrow)))
    fig.text((pa[0] + pb[0]) / 2, pa[1] + 0.015, text, ha="center", va="bottom", color=INK, fontsize=9,
             bbox=dict(boxstyle="round,pad=0.25", fc=SURFACE, ec=BASELINE, lw=0.8))
    if trunc:
        fig.text(0.53, 0.5, trunc, ha="center", va="center", color=INK, fontsize=9,
                 bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=WARN, lw=1.5))
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def trunc_note(rs):
    t = [r for r in rs if half_ps(r) > W_PS]
    if not t:
        return ""
    return (f"잘림 — {len(t)}런의 반 덩어리가 W = {W_PS:,.0f}ps 를 넘는다 (최대 {max(half_ps(r) for r in t):,.0f}ps): "
            + " · ".join(r["utc"] for r in t[:3]) + (" …" if len(t) > 3 else ""))


def plot_chip(plt, chip, rs, out_png):
    ui = N_STEPS * rs[0]["dphi"]
    fig, al, ar = panels(plt, f"{chip} — 25MHz 욕조 {len(rs)}런과 칩 평균 (끊긴 축, 한쪽 {W_PS:,.0f}ps)")
    cs = [curve(r) for r in rs]
    for x, ber, fl in cs:
        draw(al, ar, x, ber, fl, ui, ls="-", marker=".", ms=2, color=RAMP[0], lw=0.6, alpha=0.35)
    xm = np.mean([c[0] for c in cs], axis=0)
    ym = np.mean([c[1] for c in cs], axis=0)               # 오류 0 런도 0 으로 들어간 평균
    flm = 1 / sum(r["n_bits_per_step"] for r in rs)
    draw(al, ar, xm, ym, flm, ui, ls="-", marker="o", ms=3, color=RAMP[3], lw=2, zcolor=INK2, zms=5)
    al.plot([], [], "-", color=RAMP[0], lw=1, label=f"런 ({len(rs)}개)")
    al.plot([], [], "-o", color=RAMP[3], lw=2, ms=3, label="칩 평균 (오류 0 런 포함)")
    al.plot([], [], "x", color=MUTED, ms=4, label="0 errors — 런 (1/n_bits)")
    al.plot([], [], "x", color=INK2, ms=5, label="0 errors — 평균 (1/Σn_bits)")
    nzx = xm[ym > 0]
    fls = [floor_ps(r) for r in rs]
    text = (f"바닥(오류 0) {fls[0]:,.0f}ps" if len(rs) == 1 else
            f"바닥(오류 0) 런별 {min(fls):,.0f} - {max(fls):,.0f}ps · 평균 {np.mean(fls):,.0f}ps")
    finish(plt, fig, al, ar, ui, flm, ARROW_UP * max(c[2] for c in cs), nzx.max(), ui + nzx.min(), text, trunc_note(rs), out_png)


def plot_run(plt, r, out_png):
    ui = N_STEPS * r["dphi"]
    x, ber, fl = curve(r)
    fig, al, ar = panels(plt, f"{r['chip']} {r['utc']} — 25MHz 욕조 (끊긴 축, 한쪽 {W_PS:,.0f}ps)")
    draw(al, ar, x, ber, fl, ui, ls="-", marker="o", ms=4, color=RAMP[1], lw=2, zms=5)
    al.plot([], [], "-o", color=RAMP[1], lw=2, ms=4, label="BER")
    al.plot([], [], "x", color=MUTED, ms=5, label=f"0 errors (1/n_bits = 1/{r['n_bits_per_step']:,})")
    nzx = x[ber > 0]
    finish(plt, fig, al, ar, ui, fl, ARROW_UP * fl, nzx.max(), ui + nzx.min(), f"바닥(오류 0) {floor_ps(r):,.0f}ps",
           trunc_note([r]), out_png)


def plot_walls(plt, r, out_png):
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
    x, ber, fl = curve(r)
    fig, ax = plt.subplots(figsize=(7, 4.6))
    _style_axes(fig, ax)
    for sel, sgn, col, mk, mfc, lab in ((x >= 0, 1, RAMP[1], "o", RAMP[1], "욕조 왼쪽 벽 = 덩어리의 오른쪽 벽 (표의 R)"),
                                        (x <= 0, -1, INK2, "s", "none", "욕조 오른쪽 벽 = 덩어리의 왼쪽 벽 (표의 L), 좌우 뒤집음")):
        xs, bs = sgn * x[sel], ber[sel]
        nz = bs > 0
        ax.plot(xs[nz], bs[nz], "-" + mk, color=col, lw=2, ms=4, mfc=mfc, label=lab)
        ax.plot(xs[~nz], np.full((~nz).sum(), fl), "x", color=col, ms=5)
    ax.plot([], [], "x", color=MUTED, ms=5, label=f"0 errors (1/n_bits = 1/{r['n_bits_per_step']:,})")
    ax.set_yscale("log")
    ax.set_ylim(fl / 2, 1)
    ax.set_xlim(0, W_PS)
    ax.set_xlabel("덩어리 중점에서의 거리 (ps)", color=INK2)
    ax.set_ylabel("BER", color=INK2)
    ax.set_title(f"{r['chip']} {r['utc']} — 좌우 벽 겹침 (25MHz)", color=INK, fontsize=10)
    leg = ax.legend(frameon=False, fontsize=8.5, loc="upper right")
    for t in leg.get_texts():
        t.set_color(INK2)
    if trunc_note([r]):
        ax.text(0.5, 0.2, trunc_note([r]), transform=ax.transAxes, ha="center", color=INK, fontsize=9,
                bbox=dict(boxstyle="round,pad=0.3", fc=SURFACE, ec=WARN, lw=1.5))
    fig.tight_layout()
    fig.savefig(out_png, dpi=150, facecolor=SURFACE)
    plt.close(fig)


def main():
    argparse.ArgumentParser(description="v1 25MHz 욕조를 끊긴 축(P1)으로 — 칩별 전 런 + 평균 · 게재 런 · 좌우 벽 겹침 (build/bathtub/v1/)").parse_args()
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    OUT.mkdir(parents=True, exist_ok=True)
    by_chip = defaultdict(list)
    for p in sorted(glob.glob(str(DATA / "sweep_*.csv"))):
        m = NAME.match(Path(p).name)
        if not m:
            continue
        st, f = analyze(p)
        if st != "ok":
            if not st.startswith("skip: f_sclk"):
                print(f"  [{st}] {Path(p).name}")
            continue
        f.update(chip=m[1], utc=m[3], file=Path(p).name)
        by_chip[m[1]].append(f)

    for chip in sorted(by_chip):
        rs = by_chip[chip]
        plot_chip(plt, chip, rs, OUT / f"p1_chip_{chip}.png")
        fls = [floor_ps(r) for r in rs]
        t = sum(half_ps(r) > W_PS for r in rs)
        print(f"  {chip} {len(rs):>3}런 · 바닥 {min(fls):>9,.0f} - {max(fls):>9,.0f}ps · 반 덩어리 최대 {max(half_ps(r) for r in rs):>6,.0f}ps"
              + (f" · 잘림 {t}런" if t else ""))
    for r in (r for rs in by_chip.values() for r in rs if r["file"] == SAMPLE):
        tag = f"{r['chip']}_{r['utc']}"
        plot_run(plt, r, OUT / f"p1_run_{tag}.png")
        plot_walls(plt, r, OUT / f"p1_walls_{tag}.png")
        print(f"게재 런 {tag}: 덩어리 스텝 {r['first_nz_step']}-{r['last_nz_step']} · 천장 {r['ceil_bit_errors']:,} · 바닥 {floor_ps(r):,.0f}ps")
    print(f"출력: {OUT.relative_to(REPO)}/ — 칩 {len(by_chip)} · 런 {sum(len(v) for v in by_chip.values())}")


if __name__ == "__main__":
    main()
