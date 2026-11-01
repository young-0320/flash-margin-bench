// errorATE 최종 발표 PPT 초안 — docs/results/reports/final_ppt_prompt_2026-11.md 기준
const pptxgen = require("pptxgenjs");
const { applyTheme } = require("/root/.claude/skills/synced/a3e47dcc-66ef-466a-aa93-4600b27dd1f0_9af8ced5-1f5a-4342-b96f-007b042af1d6/pptx/scripts/apply_theme.js");

const BG = "F6F6F3", INK = "1A1A1A", MUTE = "8C8C8C", ACC = "B4E33D";
const THEME = {
  name: "errorATE",
  headFontFace: "Arial",
  bodyFontFace: "Calibri",
  colors: { dk1: INK, lt1: BG, dk2: MUTE, lt2: BG, accent1: ACC, accent2: MUTE, accent3: INK, accent4: ACC, accent5: MUTE, accent6: INK, hlink: INK, folHlink: MUTE },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
pres.author = "errorATE";
pres.title = "FPGA 기반 플래시 메모리 수명 예측 시스템";
const C = pres.SchemeColor;
const W = 13.333, H = 7.5, ML = 0.6, MR = 0.6;
const CW = W - ML - MR; // 12.13
const IMG = __dirname + "/img/";

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "COVER",
  background: { color: BG },
  objects: [],
});
pres.defineSlideMaster({
  title: "CONTENT",
  background: { color: BG },
  margin: [0.4, MR, 0.7, ML],
  objects: [
    { text: { text: "errorATE · FPGA 기반 플래시 메모리 수명 예측 시스템", options: { x: ML, y: 7.02, w: 7, h: 0.3, fontSize: 10, color: C.text2, margin: 0 } } },
    { placeholder: { options: { name: "title", type: "title", x: 1.35, y: 0.42, w: CW - 0.75, h: 0.72, fontSize: 25, bold: true, color: C.text1, margin: 0, valign: "middle", align: "left" } } },
  ],
  slideNumber: { x: W - MR - 0.6, y: 7.02, w: 0.6, h: 0.3, fontSize: 10, color: MUTE, align: "right" },
});

// ---------- helpers ----------
let n = 0;
function content(num, title, tag, section) {
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: section });
  s.addShape(pres.ShapeType.rect, { x: ML, y: 0.5, w: 0.55, h: 0.55, fill: { color: C.accent1 }, line: { color: C.accent1 } });
  s.addText(String(num), { x: ML, y: 0.5, w: 0.55, h: 0.55, fontSize: 18, bold: true, color: C.text1, align: "center", valign: "middle", margin: 0, isTextBox: true, fontFace: "Arial" });
  s.addText(title, { placeholder: "title" });
  s.addText(tag, { x: ML, y: 1.2, w: 4, h: 0.25, fontSize: 9.5, color: C.text2, margin: 0, isTextBox: true, charSpacing: 1 });
  return s;
}
const hl = (t) => ({ text: t, options: { highlight: ACC, bold: true } });
const tx = (t, o = {}) => ({ text: t, options: o });
function bullets(items, size = 14, after = 7) {
  // items: string | array of runs
  const out = [];
  items.forEach((it, i) => {
    const runs = Array.isArray(it) ? it : [tx(it)];
    runs.forEach((r, j) => {
      const o = Object.assign({}, r.options || {});
      if (j === 0) { o.bullet = { indent: 14 }; o.paraSpaceAfter = after; }
      if (j === runs.length - 1) { o.breakLine = i < items.length - 1; }
      out.push({ text: r.text, options: o });
    });
  });
  return out;
}
function body(s, runs, x, y, w, h, size = 14) {
  s.addText(runs, { x, y, w, h, fontSize: size, color: C.text1, valign: "top", margin: 0, isTextBox: true, paraSpaceAfter: 6 });
}
function ph(s, x, y, w, h, desc) {
  s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { color: BG }, line: { color: MUTE, width: 0.75, dashType: "dash" } });
  s.addText("[필요 이미지: " + desc + "]", { x: x + 0.2, y, w: w - 0.4, h, fontSize: 11, color: C.text2, align: "center", valign: "middle", margin: 0, isTextBox: true });
}
function img(s, file, x, y, w, h, cap) {
  s.addImage({ path: IMG + file, x, y, w, h, sizing: { type: "contain", w, h } });
  if (cap) s.addText(cap, { x, y: y + h + 0.03, w, h: 0.25, fontSize: 9.5, color: C.text2, margin: 0, isTextBox: true, align: "center" });
}
function card(s, x, y, w, h) {
  s.addShape(pres.ShapeType.rect, { x, y, w, h, fill: { color: BG }, line: { color: MUTE, width: 0.75 } });
}
function stat(s, x, y, w, big, label, sub, size = 36) {
  s.addText(big, { x, y, w, h: 0.8, fontSize: size, bold: true, color: C.text1, margin: 0, isTextBox: true, fontFace: "Arial" });
  s.addText(label, { x, y: y + 0.82, w, h: 0.3, fontSize: 12.5, bold: true, color: C.text1, margin: 0, isTextBox: true });
  if (sub) s.addText(sub, { x, y: y + 1.12, w, h: 0.55, fontSize: 10.5, color: C.text2, margin: 0, isTextBox: true, valign: "top" });
}
const TBL = { fontSize: 11, color: INK, border: { type: "solid", pt: 0.5, color: MUTE }, margin: 0.05, valign: "middle", fontFace: "Calibri" };
const TH = { bold: true, fill: { color: ACC }, color: INK };
const CH = { // common chart cosmetics
  catAxisLabelColor: MUTE, valAxisLabelColor: MUTE, catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
  catAxisLabelFontSize: 9, valAxisLabelFontSize: 9, valGridLine: { color: MUTE, size: 0.25, style: "dash" }, catGridLine: { style: "none" },
  catAxisLineShow: false, valAxisLineShow: false, dataLabelFontFace: "+mn-lt", dataLabelFontSize: 9, dataLabelColor: INK,
  legendFontFace: "+mn-lt", legendFontSize: 10, legendColor: INK, titleFontFace: "+mn-lt", titleFontSize: 11, titleColor: INK,
};

// ================= 0. 표지 =================
pres.addSection({ title: "표지" });
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: "표지" });
  s.addShape(pres.ShapeType.rect, { x: ML, y: 1.3, w: 1.1, h: 1.1, fill: { color: C.accent1 }, line: { color: C.accent1 } });
  s.addText("FPGA 기반 플래시 메모리\n수명 예측 시스템", { x: ML, y: 2.75, w: 8.6, h: 1.9, fontSize: 40, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "top", lineSpacingMultiple: 1.05 });
  s.addText([tx("불량인지 판정하는 대신, "), hl("여유가 얼마나 남았는지"), tx("를 측정한다")], { x: ML, y: 4.7, w: 8.6, h: 0.5, fontSize: 18, color: C.text1, margin: 0, isTextBox: true });
  s.addText([tx("팀 ", { bold: true }), tx("errorATE", { bold: true, fontFace: "Arial" }), tx("   한영웅 [학번] · 박지민 [학번] · 장세은 [학번]")], { x: ML, y: 5.75, w: 9, h: 0.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
  s.addText("W25Q64FV SPI NOR · Zybo Z7-20 · 2026-07 ~ 2026-10", { x: ML, y: 6.2, w: 9, h: 0.3, fontSize: 11, color: C.text2, margin: 0, isTextBox: true });
  s.addImage({ path: IMG + "system_block.png", x: 8.9, y: 1.9, w: 4.0, h: 1.76, transparency: 55 });
  s.addNotes("표지. 팀명 errorATE, 학번은 발표 전에 채운다.");
}

// ================= 1. 문제 제기 =================
pres.addSection({ title: "서론" });
{
  const s = content(1, "왜 NOR 플래시인가 — 튼튼하다고 알려져 연구가 드물고, 늙어도 PASS 로 통과한다", "창의성", "서론");
  body(s, bullets([
    [tx("NOR 의 자리: 자동차 ECU · 산업 제어기 · 의료 장비의 "), hl("부팅 코드 · 펌웨어"), tx(" — XIP, 비트 에러 거의 없음, 정격 10만 회 · 85°C")],
    [tx("선행 연구는 NAND 중심(Sakib 외, "), tx("Cryptography", { italic: true }), tx(" 2018). 저자들 스스로 「a very few works on the detection of recycled Flash memory」. 답은 썼다 / 안 썼다뿐")],
    [tx("정격 3배(30만 회)를 쓴 칩도 기능 검사는 "), hl("PASS")],
    [tx("선행 방식의 전제 「같은 품번이면 신품 소거 시간이 같다」 — 신품 31칩을 재니 "), hl("24.5 ~ 53.4ms, 두 배"), tx(". 신품 느린 칩(51.1ms)이 1,000회 쓴 빠른 칩(46.5ms)보다 느리다")],
    [tx("[출처 필요] 극한 환경 NOR 고장 보고 — 각주 하나를 달거나 이 줄을 뺀다", { color: MUTE, fontSize: 11 })],
  ], 14, 9), ML, 1.6, 5.6, 5.2);
  // chart: 31 chips erase medians sorted
  const chips = [["chip36",24.509],["chip24",24.866],["chip26",25.656],["chip06",25.674],["chip09",25.987],["chip37",26.313],["chip17",26.43],["chip31",26.543],["chip16",26.793],["chip02",27.151],["chip01",28.737],["chip18",29.448],["chip38",30.16],["chip10",33.003],["chip04",33.743],["chip34",34.398],["chip33",35.462],["chip14",36.239],["chip35",36.9],["chip07",47.01],["chip12",47.752],["chip21",48.862],["chip23",49.368],["chip22",49.527],["chip08",49.528],["chip15",49.794],["chip25",50.584],["chip03",51.129],["chip32",52.619],["chip30",53.166],["chip39",53.364]];
  const labels = chips.map(c => c[0].replace("chip", ""));
  const fast = chips.map(c => c[1] < 40 ? +c[1].toFixed(1) : 0);
  const slow = chips.map(c => c[1] >= 40 ? +c[1].toFixed(1) : 0);
  s.addChart(pres.ChartType.bar, [
    { name: "빠른 무리 (< 40ms) 19칩", labels, values: fast },
    { name: "느린 무리 (≥ 40ms) 12칩", labels, values: slow },
  ], Object.assign({}, CH, {
    x: 6.5, y: 1.55, w: 6.25, h: 4.6, barDir: "col", barGrouping: "stacked", barGapWidthPct: 25,
    chartColors: [MUTE, ACC], showLegend: true, legendPos: "t", showTitle: true, title: "신품 31칩 섹터 소거 시간 중앙값 (ms) — 같은 품번",
    valAxisMinVal: 0, valAxisMaxVal: 60, valAxisMajorUnit: 10, catAxisLabelFontSize: 7, showValue: false,
  }));
  s.addText("chip04 · 1,000회 사용 뒤 46.5ms → 신품 느린 무리 안에 들어간다", { x: 6.5, y: 6.2, w: 6.25, h: 0.3, fontSize: 10.5, color: C.text2, margin: 0, isTextBox: true, align: "center" });
  s.addNotes("1분. PASS/FAIL 표(전부 PASS) 한 장 + 신품 31칩 소거 시간 분포에 「1,000회 쓴 chip04」 점 하나. 「극한 환경 NOR 고장 보고」 는 리포에 출처가 없다 — 찾아서 각주로 달거나 뺀다.");
}

// ================= 2. 두괄식 결론 + 타임라인 =================
{
  const s = content(2, "결론부터 — 마진은 늙지 않았고, 소거 시간이 늙었고, 그것으로 「몇 번 썼나」 를 구간으로 역산했다", "발표", "서론");
  const cw = (CW - 0.9) / 4;
  [
    ["42ps 안", "타이밍 마진은 늙지 않았다", "정격 1 ~ 3배(30만 회)까지 재장착 3σ 안"],
    ["1.6 ~ 4.0배", "소거 시간이 늙는다", "10만 회, 빠른 무리 2.6 ~ 4.0 · 느린 1.6 ~ 1.75"],
    ["81.7 · 94.5%", "68% · 95% 구간 적중", "모의 블라인드 106점 (v4.3 등록 수치)", 30],
    ["12,000회", "봉인된 정답을 품었다", "chip06 · 68% 구간 3,001 ~ 19,000 · 49번째 백분위"],
  ].forEach((d, i) => stat(s, ML + i * (cw + 0.3), 1.55, cw, d[0], d[1], d[2], d[3]));
  // timeline
  const ty = 4.75, tx0 = ML + 0.2, tx1 = W - MR - 0.2;
  s.addShape(pres.ShapeType.line, { x: tx0, y: ty, w: tx1 - tx0, h: 0, line: { color: MUTE, width: 1.25 } });
  const ev = [
    ["07/08", "FPGA 루프백 ·\n실칩 첫 욕조 곡선", false],
    ["08/23", "몬테카를로 N=112\n사전 등록 · RTL 계획 동결", true],
    ["09/15 ~ 22", "마모 사양 · 블랙박스 TB\n동결 · 엔진 실칩 인수", true],
    ["09/26", "파일럿 chip01 300k\n(H1 을 29.6k 시점에 먼저)", true],
    ["09/30 ~ 10/01", "v1 등록 → 블라인드\nchip06 개봉", true],
    ["10/09 · 10/12", "v4 등록(잰 값) ·\nv4.2 폐기", false],
    ["10/14 ~ 23", "교정 6칩 200k 연장 ·\nv4.3 등록(chip08 개봉 전)", true],
    ["10/25", "신품 전수 31칩 종료 ·\n[TODO] chip08 개봉", false],
  ];
  const step = (tx1 - tx0) / (ev.length - 1);
  ev.forEach((e, i) => {
    const x = tx0 + i * step;
    s.addShape(pres.ShapeType.ellipse, { x: x - 0.09, y: ty - 0.09, w: 0.18, h: 0.18, fill: { color: e[2] ? ACC : MUTE }, line: { color: e[2] ? ACC : MUTE } });
    const up = i % 2 === 0;
    s.addText(e[0], { x: x - 0.75, y: up ? ty - 0.95 : ty + 0.2, w: 1.5, h: 0.25, fontSize: 10, bold: true, color: C.text1, align: "center", margin: 0, isTextBox: true, fontFace: "Arial" });
    s.addText(e[1], { x: x - 0.8, y: up ? ty - 0.72 : ty + 0.43, w: 1.6, h: 0.5, fontSize: 9, color: C.text1, align: "center", margin: 0, isTextBox: true, valign: up ? "bottom" : "top" });
  });
  s.addShape(pres.ShapeType.ellipse, { x: ML, y: 6.55, w: 0.14, h: 0.14, fill: { color: ACC }, line: { color: ACC } });
  s.addText("= 결과를 보기 전에 먼저 적은 사건", { x: ML + 0.2, y: 6.47, w: 4, h: 0.3, fontSize: 10, color: C.text2, margin: 0, isTextBox: true });
  s.addNotes("1분. (영웅) 「시연이 시간이 걸리는 관계로 지금 먼저 테스트 돌리는 것 보여드리겠습니다」 — 화면 공유로 터미널(시연 명령 [TODO])을 띄우고 돌려 둔 채 발표를 이어간다. 시연은 15장 뒤에 확인.");
}

// ================= 3. 발상 — 마진을 피코초로 =================
{
  const s = content(3, "발상 — 장비가 경계까지 다가가 여유를 잰다. 발상은 맞았고, 「마모가 여유를 줄인다」 는 가설은 기각됐다", "창의성 · 난이도", "서론");
  body(s, bullets([
    [tx("MMCM 미세 위상 제어로 읽기 샘플 클럭을 "), hl("Δφ = 15.873ps"), tx(" 씩 2,520스텝 밀며, 스텝마다 PRBS15 를 112회 × 2,048비트 읽어 BER → 욕조 곡선 → 양 벽 교점의 폭(θ = 10⁻²)")],
    [tx("자의 정밀도: 같은 칩 5회 ±0.61ps · 재장착 3회 σ = 13.86ps → "), hl("판정선 3σ = 42ps"), tx(" · 신품 폭 39,737ps(40ns 의 99.3%)")],
    [tx("가설: 셀이 닳으면 이 창이 에러 전부터 좁아진다 → 창 폭 = 남은 수명")],
    [tx("결과: "), hl("30만 회까지 +15.5ps, 10만 회 9칩 전부 42ps 안"), tx(" — 기각")],
    [tx("왜: 출력 핀의 엣지는 SCLK 에 맞춰 도는 출력 레지스터가 만든다. 셀은 센스 앰프에 「전류 있음/없음」 만 준다 — 셀이 늙어도 시계는 안 늙는다")],
    [tx("그래서 처음부터 보조로 같이 기록하던 "), hl("소거 · 프로그램 시간"), tx(" 으로 지표를 옮겼다 — 사전 등록 때 이중화해 둔 덕")],
  ], 13.5, 8), ML, 1.6, 6.1, 5.2, 13.5);
  img(s, "bathtub_chip01_repeat5.png", 6.95, 1.55, 5.8, 2.55, "실칩 욕조 곡선 — chip01 25MHz 5회 반복, 양 끝 벽만 남는다");
  img(s, "wear_checkpoint_width_program_2026-10.png", 6.95, 4.35, 5.8, 2.45, "체크포인트별 폭 변화 — 전부 ±42ps 띠 안 (위 칸)");
  s.addNotes("1분 30초. 「가설이 틀렸다는 것이 첫 결과」 를 숨기지 않는다. 파일럿 29,600회 시점에 「정격 안에서는 안 움직인다(H1)」 를 먼저 적었고 나머지 9칩이 그대로 나왔다.");
}

// ================= 4. 이진 → 연속 =================
{
  const s = content(4, "발상 — 「썼다 / 안 썼다」 가 아니라 「몇 번 썼고, 그 말을 얼마나 믿어도 되는가」", "창의성", "서론");
  card(s, ML, 1.6, 5.7, 4.9);
  s.addText("기존", { x: ML + 0.3, y: 1.75, w: 2, h: 0.4, fontSize: 16, bold: true, color: C.text2, margin: 0, isTextBox: true });
  body(s, bullets([
    "기능 검사 PASS / FAIL — 1비트짜리 답",
    "선행 연구 이진 판별 — 「썼다」 확신도. 몇 번인지는 모른다",
    [tx("같은 데이터(LOCO 94점)에서 선행식은 "), hl("64/94"), tx(" 만 「썼다」 — 빠른 칩은 2만 회 이하 20점 중 2점")],
  ], 14, 10), ML + 0.3, 2.3, 5.1, 3.9);
  card(s, 6.73, 1.6, 6.0, 4.9);
  s.addText("우리", { x: 7.03, y: 1.75, w: 2, h: 0.4, fontSize: 16, bold: true, color: C.text1, margin: 0, isTextBox: true });
  s.addText([hl("추정값 + 68% · 95% 구간 + 등급"), tx(" (신품 · 저마모 · 중마모 · 고마모)")], { x: 7.03, y: 2.25, w: 5.4, h: 0.4, fontSize: 14, color: C.text1, margin: 0, isTextBox: true });
  s.addText(
    "기준 섹터 32-127 : 소거 25.3ms → 빠른 무리\n마모 섹터 0-6    : 소거 41.2ms (1.63배)\n추정 12,001-13,000 회\n68% 4,001-19,000 · 95% 2,001-30,000\n판정 : 저마모 (정격의 1-20%) — 확률 79%",
    { x: 7.03, y: 2.85, w: 5.4, h: 2.3, fontSize: 13, fontFace: "Courier New", color: C.text1, margin: 0.1, isTextBox: true, valign: "top", lineSpacingMultiple: 1.2, line: { color: MUTE, width: 0.5 } });
  s.addText("chip06 — 현행 모델의 재판독 화면 (블라인드 성적이 아님)", { x: 7.03, y: 5.25, w: 5.4, h: 0.3, fontSize: 10, color: C.text2, margin: 0, isTextBox: true });
  s.addNotes("45초. 산업에서 쓰는 질문이 바뀐 것이 핵심 — 「불량인가」 에서 「여유가 얼마나 남았나」 로.");
}

// ================= 5. P/E 원리 =================
pres.addSection({ title: "본론 — 구현" });
{
  const s = content(5, "P/E 마모의 원리 — 소거 시간은 산화막 흠집의 계수기다", "구현", "본론 — 구현");
  body(s, bullets([
    [tx("소거 = FN 터널링. 칩 내부는 "), hl("펄스 → 검증 읽기 → 부족하면 다시 펄스"), tx(" 루프. 트랩에 박힌 전자가 전계를 깎아 펄스 수가 는다 → 첫 사이클부터 단조 증가")],
    [tx("프로그램 = 핫 일렉트론 주입. 벽을 넘기는 것이라 벽 안의 흠집에 덜 민감 → 계면 준위가 쌓인 "), hl("한참 뒤에야"), tx(" 는다")],
    [tx("벤치: 4KB 섹터 "), hl("0 ~ 6 (7섹터)"), tx(" 만 프로그램(0x00) · 소거 반복, "), hl("32 ~ 127 은 기준 섹터"), tx(". 사이클마다 섹터별 시간을 로그(칩당 70만 행), 체크포인트 13점마다 위상 스윕 + prep")],
    "데이터시트(W25Q64FV): 섹터 소거 typ 45 ~ 60ms · max 400ms · 정격 10만 회",
    [tx("기준 섹터는 10만 회 뒤에도 신품 대비 "), hl("0.98 ~ 1.00"), tx(" — 마모는 칩이 아니라 섹터에 쌓인다")],
  ], 13.5, 9), ML, 1.6, 6.2, 5.2, 13.5);
  ph(s, 7.1, 1.6, 5.65, 2.55, "FN 터널링 · 트랩 · 펄스-검증 루프 도식");
  // sector map drawn with shapes
  const mx = 7.1, my = 4.5, cellw = 5.65 / 16, cellh = 0.28;
  for (let r = 0; r < 8; r++) for (let c = 0; c < 16; c++) {
    const idx = r * 16 + c;
    const worn = idx <= 6, ref = idx >= 32;
    s.addShape(pres.ShapeType.rect, { x: mx + c * cellw, y: my + r * cellh, w: cellw - 0.02, h: cellh - 0.02, fill: { color: worn ? ACC : BG }, line: { color: ref ? INK : MUTE, width: ref ? 0.75 : 0.5 } });
  }
  s.addText("섹터 0 ~ 127 — 연두: 마모 0-6 · 굵은 테두리: 기준 32-127 · 7-31 은 근접 교란으로 기준에서 뺌", { x: mx, y: my + 8 * cellh + 0.05, w: 5.65, h: 0.3, fontSize: 9.5, color: C.text2, margin: 0, isTextBox: true });
  s.addNotes("1분. 「닳지 않은 섹터는 10만 회 뒤에도 신품 대비 0.98~1.00」 — 마모는 칩이 아니라 섹터에 쌓인다. 이것이 뒤의 역산에서 「칩이 자기 신품값을 몸에 지닌다」 는 근거.");
}

// ================= 6. 검증 =================
{
  const s = content(6, "엔진은 스펙을 보지 않은 블랙박스 TB 로, RTL 은 cocotb 회귀로 — 그 뒤에만 실칩에 P/E 를 냈다", "구현 · 난이도", "본론 — 구현");
  const colw = (CW - 0.4) / 2;
  card(s, ML, 1.6, colw, 5.15);
  s.addText("P/E 엔진 — Zynq PS, C (flash_wear.c)", { x: ML + 0.25, y: 1.72, w: colw - 0.5, h: 0.4, fontSize: 15, bold: true, color: C.text1, margin: 0, isTextBox: true });
  body(s, bullets([
    [tx("블랙박스 TB 사양 S-4 를 "), hl("엔진 스펙 확정 전에 동결"), tx("(09/21) — 채점표는 벤치 사양 S-1 과 인터페이스 경계 10개에서만")],
    [tx("mock 엔진 + 호스트 시뮬(가짜 NOR + 파이프) + 실행기 — "), hl("호스트 시험 163개 PASS")],
    "판정: 사이클 카운터 · A 로그 700행 · tally 봉인 · 전원 장애 복구(B) — 재개 뒤 채택 사이클로 5사이클 완주",
    "실칩 인수 09/22 → 실제 사고에서 복구 실증: chip07 PC 전원 상실 · chip23 USB 끊김 → resume 로 이어 감",
  ], 12.5, 7), ML + 0.25, 2.2, colw - 0.5, 4.4, 12.5);
  const x2 = ML + colw + 0.4;
  card(s, x2, 1.6, colw, 5.15);
  s.addText("측정 RTL — 위상 스윕 코어 · SPI 마스터 (Verilog)", { x: x2 + 0.25, y: 1.72, w: colw - 0.5, h: 0.4, fontSize: 15, bold: true, color: C.text1, margin: 0, isTextBox: true });
  body(s, bullets([
    "칩 없이 FPGA 루프백으로 메커니즘 검증(G0) → Verilog 스모크 4종",
    [hl("cocotb 회귀"), tx(" (Icarus · Winbond 행동 모델): 테스트 파일 22개 (C1~6 · F1~10 · I1~3 · W1~2). 09/18 기준 F1 · F2 · F3 · F4 · F6 · F8 · F9 PASS")],
    [tx("[확인 필요: 최종 PASS 수 — 박지민]", { color: MUTE })],
    [tx("측정 파라미터(N = 112 · θ = 10⁻²)는 몬테카를로로 "), hl("실측 전에 고정")],
  ], 12.5, 7), x2 + 0.25, 2.2, colw - 0.5, 2.6, 12.5);
  ph(s, x2 + 0.25, 4.85, colw - 0.5, 1.75, "cocotb 결과표(results.xml 상태표) 캡처 / 블랙박스 TB 구조도");
  s.addNotes("1분. 「만든 사람이 채점하지 않는다」 가 아니라 「순서로 가른다」 — TB 가 먼저 커밋되고 엔진이 뒤에 왔다. 전원 장애 복구는 설계에만 있던 것이 아니라 실제 사고 두 번에서 썼다.");
}

// ================= 7. P/E 결론 200k =================
{
  const s = content(7, "20만 회까지 — 빠른 무리는 계단(7/7), 느린 무리는 미끄럼(3/3). 계단의 유무가 두 무리를 가른다", "구현 · 난이도", "본론 — 구현");
  const rows = [
    ["무리", "칩", "범위", "100k 너머", "200k 소거 배율"].map(t => ({ text: t, options: TH })),
    ["빠른", "chip01", "0 → 300k", "계단 34~62k · 2차 계단 203~283k", "300k 5.2배"],
    ["빠른", "chip09", "100k → 200k", "계단 110~157k · 160k 뒤 평탄", "4.15"],
    ["빠른", "chip06", "100k → 200k", "계단 116~158k · 160k 뒤 평탄", "4.18"],
    ["빠른", "chip02", "100k → 200k", "계단 148~178k · 180k 뒤 평탄", "4.00"],
    ["느린", "chip03", "100k → 200k", "미끄럼", "2.10"],
    ["느린", "chip15", "100k → 200k", "미끄럼", "2.25"],
    ["느린", "chip07", "100k → 200k", "미끄럼 (가장 완만)", "1.91"],
  ].map((r, i) => i === 0 ? r : r.map((t, j) => ({ text: t, options: (i >= 5 && j === 3) ? { bold: true } : {} })));
  s.addTable(rows, { x: ML, y: 1.55, w: 6.3, colW: [0.7, 0.95, 1.35, 2.3, 1.0], fontSize: 10.5, color: INK, border: TBL.border, margin: 0.04, fontFace: "Calibri", rowH: 0.3 });
  body(s, bullets([
    [tx("계단: 섹터마다 따로, 약 85 → 103 ~ 111ms 로 한 구간에 "), hl("18 ~ 21ms"), tx(" 점프. 빠른 FV 7칩 모두 2.5만 ~ 17.8만 회 사이에")],
    [tx("미끄럼: 같은 85 ~ 93ms 에서 같은 105ms 를 지나는데 한 구간 4 ~ 12ms, "), hl("분포 폭(p10-p90)이 두 배"), tx("(20 ~ 25ms) 벌어진 채 10만 회에 걸쳐")],
    [tx("왜(추정): 소거 펄스 양자 약 21ms 는 같다. 빠른 칩은 섹터의 셀들이 "), hl("함께"), tx(" 한 펄스를 더 요구해 한 번에 뛰고, 느린 칩은 사이클마다 요구 펄스 수가 "), hl("흔들리며"), tx(" 비율이 천천히 바뀐다")],
    "예측을 먼저 걸었다: chip03 「계단」 → 틀림(미끄럼) · chip15 「미끄럼 · 약 2.1」 → 맞음(2.25) · chip21 「미끄럼 · 2.1~2.3」 → 미끄럼은 맞고 2.93",
  ], 11.5, 6), ML, 4.2, 6.3, 2.7, 11.5);
  img(s, "wear_curves_chip09_2026-10.png", 7.1, 1.55, 5.65, 2.5, "chip09 (빠른) — 계단");
  img(s, "wear_curves_chip03_2026-10.png", 7.1, 4.3, 5.65, 2.5, "chip03 (느린) — 미끄럼");
  s.addNotes("1분 30초. chip21 은 신품 48.9ms 로 느린 무리에 들어갔는데 빠른 속도로 늙었다 — 「신품 소거 느림 = 노화 느림」 이 깨진 두 번째 칩(첫째 chip12). 느린 무리 200k 는 「세 칩」, chip21 은 따로 뗀다. 양자의 정체(펄스 1회 ≈ 21ms)는 데이터시트에 없어 추정으로 말한다.");
}

// ================= 8. 소거 시간 곡선 =================
{
  const s = content(8, "소거 시간 곡선 — 신품값 대비 배율로 그리면 두 무리가 다른 띠를 그린다", "구현", "본론 — 구현");
  img(s, "wear_ratio_curves_2026-10-12.png", ML, 1.55, 8.3, 3.65, "닳은 섹터 소거 ÷ 그 칩의 신품 소거 — 교정 9칩 (빠른 01·02·04·06·09·18 · 느린 03·07·15)");
  body(s, bullets([
    [tx("10만 회: 빠른 "), hl("2.60 ~ 3.97배"), tx(" · 느린 "), hl("1.59 ~ 1.75배")],
    [tx("같은 빠른 무리 안 속도 비 chip04 : chip09 = "), hl("2.9배"), tx(" — 역산이 점이 아니라 구간으로 답하는 이유")],
    "기준 섹터 32~127 은 10만 회 뒤 0.98 ~ 1.00 — 곡선의 분모가 흔들리지 않는다",
    "절대값(ms)은 칩 간 지표가 못 된다(신품에서 이미 두 배) — 모든 곡선은 자기 t=0 대비",
  ], 12.5, 7), 9.15, 1.6, 3.6, 3.7, 12.5);
  img(s, "wear_checkpoint_width_program_2026-10.png", ML, 5.55, 4.6, 1.3);
  s.addText([tx("프로그램 시간(아래 칸): 빠른 무리 10만 회에 1.00 ~ 1.01(chip04 · 09 · 24) 또는 늦게 오름(chip06 1.9 · chip02 약 3) · 느린 무리는 "), hl("전부 오름 1.5 ~ 2.9배")], { x: 5.4, y: 5.6, w: 7.3, h: 1.2, fontSize: 12.5, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  s.addNotes("45초. 1장의 「신품 두 배 차이」 문제를 여기서 닫는다.");
}

// ================= 9. 모델 =================
pres.addSection({ title: "본론 — 모델" });
{
  const s = content(9, "역산 모델 — 네 번 바뀌었고 세 번은 결과를 보고 바꿨다. v4 부터는 재고, 먼저 적고, 떨어지면 떨어졌다고 적었다", "구현 · 난이도 · 발표의 중심", "본론 — 모델");
  // left: 4 steps
  const steps = [
    ["칩 안의 지우지 않은 섹터(32~127) 소거 시간 = 그 칩의 신품값", "현장 칩에 신품 기록이 없어도 된다"],
    ["신품값 40ms 경계로 빠른 / 느린 무리", ""],
    ["닳은 섹터의 배율을 같은 무리 교정 곡선(1k 구간 × 분위수 21)에 대어 베이즈 사후분포", "R(빠른 2.80 · 느린 1.59) · ρ = 0.00 · 0.78 · 0.21 — 교정 데이터에서 잰 값"],
    ["사후 평균 + 68% · 95% HPD 구간 + 등급", "입력은 소거 시간뿐, 계산 수 초"],
  ];
  steps.forEach((st, i) => {
    const y = 1.6 + i * 1.25;
    s.addShape(pres.ShapeType.ellipse, { x: ML, y: y + 0.05, w: 0.42, h: 0.42, fill: { color: ACC }, line: { color: ACC } });
    s.addText(String(i + 1), { x: ML, y: y + 0.05, w: 0.42, h: 0.42, fontSize: 13, bold: true, color: C.text1, align: "center", valign: "middle", margin: 0, isTextBox: true, fontFace: "Arial" });
    s.addText(st[0], { x: ML + 0.6, y, w: 5.0, h: 0.6, fontSize: 12.5, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
    if (st[1]) s.addText(st[1], { x: ML + 0.6, y: y + 0.62, w: 5.0, h: 0.5, fontSize: 10.5, color: C.text2, margin: 0, isTextBox: true, valign: "top" });
  });
  // right: version timeline
  const vx = 6.65, vw = W - MR - vx;
  const ver = [
    ["v1 → v2 → v3.2", "09/30 ~ 10/05", "상수(R · 증거량 · 셀 모양)를 성적 보고 골랐다 — 인정", false],
    ["v4", "10/09", "고른 값 다섯을 잰 값으로. LOCO 합격 띠를 돌리기 전에 적음. 68% 가 띠 위(과소신) — 손대지 않고 등록", true],
    ["v4.2", "10/12 폐기", "프로그램 축 추가 → 폭 34k → 29k 로 좁아지나 합성 복원 95% 96 → 84 로 과신 → 버림(수치는 남김)", false],
    ["v4.3", "10/23 등록 · chip08 개봉 전", "200k 곡선 6장. 통과 기준(50~100k 추정/정답 0.84 → 0.90)을 먼저 적었고 미충족(0.84)으로 보고", true],
  ];
  ver.forEach((v, i) => {
    const y = 1.6 + i * 1.12;
    s.addShape(pres.ShapeType.rect, { x: vx, y: y + 0.08, w: 0.16, h: 0.85, fill: { color: v[3] ? ACC : MUTE }, line: { color: v[3] ? ACC : MUTE } });
    s.addText([tx(v[0], { bold: true, fontFace: "Arial" }), tx("   " + v[1], { color: MUTE, fontSize: 10 })], { x: vx + 0.3, y, w: vw - 0.3, h: 0.32, fontSize: 13, color: C.text1, margin: 0, isTextBox: true });
    s.addText(v[2], { x: vx + 0.3, y: y + 0.33, w: vw - 0.3, h: 0.7, fontSize: 10.5, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  s.addText([tx("등록 수치 (LOCO rows P5 × 20, 106점): "), hl("68% 81.7% · 95% 94.5% · 68% 폭 34,000"), tx(" — 띠 68% 63~81 · 95% 97~105")], { x: vx, y: 6.15, w: vw, h: 0.6, fontSize: 11.5, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  s.addText("■ 먼저 고정한 것   ■ 결과를 보고 버린 것", { x: ML, y: 6.6, w: 5.6, h: 0.3, fontSize: 9.5, color: C.text2, margin: 0, isTextBox: true });
  s.addNotes("1분 30초. 「교정 곡선 = 훈련 데이터」 와 「LOCO = 채점표」 를 가른다. 모델이 교정 곡선에 맞춰지는 건 목적이고, 위험은 채점표를 보고 모수를 돌리는 것. ① 띠 사전 고정 ② 미충족 그대로 보고 ③ 봉인된 칩이 최종 심판. 순서는 커밋 시각(v4.3 등록 커밋 7c55df6, 10/23)으로 확인된다.");
}

// ================= 10. 블라인드 + 기준선 =================
{
  const s = content(10, "블라인드 — 봉인된 정답을 두 구간 모두 품었고, 미리 정한 기준 하나는 떨어졌으며 기준을 바꾸지 않았다", "구현 · 발표", "본론 — 모델");
  card(s, ML, 1.55, 5.5, 5.2);
  s.addText([tx("chip06", { bold: true, fontFace: "Arial" }), tx(" — 정답 12,000 (칩 안 tally 에 봉인, 추정 커밋 1시간 47분 뒤 개봉)")], { x: ML + 0.25, y: 1.65, w: 5.0, h: 0.5, fontSize: 12.5, color: C.text1, margin: 0, isTextBox: true });
  // interval bar drawing
  const bx = ML + 0.35, bw = 4.8, by = 2.35, scale = bw / 40000;
  s.addShape(pres.ShapeType.rect, { x: bx + 1001 * scale, y: by, w: (34000 - 1001) * scale, h: 0.32, fill: { color: BG }, line: { color: MUTE, width: 0.75 } });
  s.addShape(pres.ShapeType.rect, { x: bx + 3001 * scale, y: by, w: (19000 - 3001) * scale, h: 0.32, fill: { color: ACC }, line: { color: ACC } });
  s.addShape(pres.ShapeType.line, { x: bx + 12000 * scale, y: by - 0.12, w: 0, h: 0.56, line: { color: INK, width: 2 } });
  s.addText("정답 12,000", { x: bx + 12000 * scale - 0.7, y: by + 0.48, w: 1.4, h: 0.25, fontSize: 9.5, bold: true, color: C.text1, align: "center", margin: 0, isTextBox: true });
  s.addText("95%  1,001 ~ 34,000", { x: bx, y: by + 0.48, w: 1.6, h: 0.25, fontSize: 9, color: C.text2, margin: 0, isTextBox: true });
  s.addText("68%  3,001 ~ 19,000", { x: bx + bw - 1.6, y: by + 0.48, w: 1.6, h: 0.25, fontSize: 9, color: C.text2, margin: 0, isTextBox: true, align: "right" });
  body(s, bullets([
    [tx("판정용 v2 — 정답은 사후분포 "), hl("49번째 백분위")],
    [tx("기준 ① 95% 안 통과 · ② 폭 ≤ 60,000 통과 · ③ 폭/추정 "), hl("불통과(16,000 > 10,000)"), tx(" → 그대로 보고")],
    "교정 4칩이던 v1 은 정답을 68% 밖(79번째)에 뒀다 — 넓어진 구간이 정직한 불확실성",
    [tx("chip08", { bold: true }), tx(" (느린 무리, 정답 봉인) — v4.3 을 10/23 개봉 전 등록(기준 ③ = 1.33 포함) → "), tx("[TODO: 개봉일 · 정답 · 68% / 95% 구간 · ①②③ 판정]", { color: MUTE })],
  ], 11.5, 6), ML + 0.25, 3.2, 5.0, 3.5, 11.5);
  // right: baseline table
  s.addText("같은 LOCO 94점에 세 방법 — 방법을 결과 전에 커밋(7ce25fc)", { x: 6.4, y: 1.55, w: 6.35, h: 0.35, fontSize: 12, bold: true, color: C.text1, margin: 0, isTextBox: true });
  const brows = [
    ["방법", "답", "결과"].map(t => ({ text: t, options: TH })),
    ["선행식 이진 판별 (데이터시트 기준)", "썼다 / 안 썼다", "64/94 검출 — 빠른 칩 2만 회 이하 2/20"],
    ["같은 판별 + 우리 정규화", "썼다 / 안 썼다", "74/94 — 신품 15칩 오경보 0"],
    ["단순 회귀 (평균 곡선 거꾸로)", "숫자 하나", "오차 중앙값 10,000 · 구간 없음"],
    [{ text: "우리 모델 (v3.2 당시)", options: { bold: true } }, { text: "숫자 + 구간 + 등급", options: { bold: true } }, { text: "오차 중앙값 7,500 · 68% 67/94 · 95% 93/94", options: { bold: true } }],
  ];
  s.addTable(brows, { x: 6.4, y: 1.95, w: 6.35, colW: [2.3, 1.45, 2.6], fontSize: 10.5, color: INK, border: TBL.border, margin: 0.05, fontFace: "Calibri", rowH: 0.42 });
  img(s, "baseline_compare_estimate_2026-10.png", 6.4, 4.2, 6.35, 2.55, "지점마다 정답 · 우리 모델의 추정과 68% 구간 · 단순 회귀 — 칩 8개");
  s.addNotes("1분 15초. 「느린 무리만은 회귀가 낫다(4,106 대 6,500)」 — 우리가 더하는 것의 본체는 점이 아니라 구간. 3인 팀이라 완전 블라인드가 아님(정답은 칩이 쥐고, 추정 커밋 뒤 읽음)을 한 문장으로.");
}

// ================= 11. 열화 환경 =================
pres.addSection({ title: "본론 — 온도" });
{
  const s = content(11, "열화 환경 — 상온 교정 모델이 데이터시트 상한 85°C 이력 칩에도 서는지 보려고 저가 히터 벤치를 만들었다", "구현 · 난이도", "본론 — 온도");
  body(s, bullets([
    [tx("동기: 현장 NOR 은 고온에서 산다(차량 · 산업). 온도가 노화 "), hl("속도"), tx(" 를 바꾸면 상온 교정이 틀린다 — 그것을 재야 「범위 답」 의 유효 범위를 말할 수 있다")],
    [tx("구현(장세은): "), hl("TMP117"), tx(" 디지털 온도 센서(±0.1°C, I²C) + "), hl("DFR0457"), tx(" MOSFET 모듈 + 5V 필름 히터 + 구리판, Arduino PI 제어(Kp 12 · Ki 0.4 PWM/°C)")],
    [tx("안전: 설정 25 ~ 88°C · PWM 상한 86% · "), hl("95°C 절대 컷오프 래치"), tx(" · 센서 FAULT 시 히터 차단 · 온도 로그 1분 간격")],
    "운용: 보드 B 에서 설정 65°C(chip16 · 17) · 85°C(chip22 · 23 · 24), 0 → 10만 회 무인 세션 24 ~ 56시간",
  ], 13, 9), ML, 1.6, 6.0, 5.2, 13);
  ph(s, 6.9, 1.6, 5.85, 2.6, "히터 벤치 사진 — 구리판 · 센서 · 칩 모듈 배치");
  img(s, "temp_chip24_timeline_2026-10.png", 6.9, 4.4, 5.85, 2.3, "chip24 온도 로그 — 설정 85°C, 센서 83.5°C (79.6 ~ 85.9)");
  s.addNotes("45초. 소프트웨어 컷오프가 못 막는 것(MOSFET 단락 · MCU 정지 · 떨어진 센서)을 스케치 머리에 적어 두었다 — 그것이 한계 3 의 원인과 이어진다.");
}

// ================= 12. 온도 결과 =================
{
  const s = content(12, "온도 결과 — 65 ~ 85°C 이력 네 칩의 노화는 상온 개체 산포 안. 95% 구간 47/48 — 다만 무리당 1 ~ 2칩이라 「가르지 못함」 이다", "구현", "본론 — 온도");
  const trows = [
    ["칩", "온도", "무리", "소거 100k", "계단", "프로그램 100k", "상온 모델 68% · 95%"].map(t => ({ text: t, options: TH })),
    ["chip24", "83.5°C", "빠른", "3.47배", "3섹터 78~100k", "1.00", "12/12 · 12/12"],
    ["chip17", "65.2°C", "빠른", "2.44배", "없음", "1.20", "1/12 · 11/12"],
    ["chip16", "65°C 설정 (칩 온도 미확인)", "빠른", "4.34배", "7/7", "1.00", "6/12 · 12/12"],
    ["chip22", "85.0°C", "느린", "1.90배", "없음", "1.64", "3/12 · 12/12"],
    ["chip23", "85°C", "느린", "26.5k 중단 (USB 끊김 · 센서 FAULT)", "—", "—", "—"],
    [{ text: "상온 빠른 6 / 느린 3", options: { color: MUTE } }, { text: "25°C", options: { color: MUTE } }, { text: "", options: {} }, { text: "2.60~3.97 / 1.59~1.75", options: { color: MUTE } }, { text: "6/6 / 없음", options: { color: MUTE } }, { text: "1.00~2.09 / 1.21~2.15", options: { color: MUTE } }, { text: "약 80% · 95%", options: { color: MUTE } }],
  ];
  s.addTable(trows, { x: ML, y: 1.55, w: 7.3, colW: [0.85, 1.65, 0.6, 1.3, 1.05, 0.85, 1.0], fontSize: 9.5, color: INK, border: TBL.border, margin: 0.04, fontFace: "Calibri", rowH: 0.32 });
  body(s, bullets([
    "빠른 무리: 온도 칩 셋의 100k 배율 순위가 상온 6칩 사이 1 · 5 · 9 / 9 — 가를 근거 없음",
    "느린 무리: chip22 가 상온 느린 세 칩 위(1.90 대 1.59~1.75)이나 상온 느린 신품의 개체 산포 안 — n = 1",
    [tx("「고온이면 더 닳는다」 는 소거 시간에는 거꾸로 갈 수 있다 — 갇힌 전하가 열로 빠져 소거가 덜 늦어진다(chip17). 프로그램은 빠른 무리 불변 · 느린 무리 상승 — 5장의 원리 그대로")],
    [hl("표본 부족을 먼저 말한다"), tx(": 무리당 1 ~ 2칩, 칩 온도는 센서 자리 온도. 모델에 온도 축을 넣지 않고 고온 이력 칩에는 범위(95%)로 답한다")],
  ], 11, 6), ML, 4.3, 7.3, 2.6, 11);
  img(s, "wear_temp_chip24_2026-10.png", 8.15, 1.55, 4.6, 2.4, "chip24 (빠른 · 83.5°C)");
  img(s, "wear_temp_chip22_2026-10.png", 8.15, 4.3, 4.6, 2.45, "chip22 (느린 · 85.0°C)");
  s.addNotes("1분. chip16 은 온도 로그가 히터 상태와 맞지 않아(꺼진 채 3시간 67°C) 「65°C 이력」 이라 쓰지 않는다 — 한계 3 의 실제 사례.");
}

// ================= 13. 한계 =================
pres.addSection({ title: "한계와 극복" });
{
  const s = content(13, "한계 세 가지 — 셋 다 「어디까지 모르는지」 를 숫자로 말할 수 있다", "난이도 · 구현", "한계와 극복");
  const cw = (CW - 0.6) / 3;
  const lim = [
    ["적용 범위가 한 품번", "W25Q64FV", [
      "교정 9칩 전부 FV. JV 는 신품 12칩을 쟀지만 교정 곡선이 없다",
      [tx("마모시킨 JV 두 칩(chip10 · 14)은 어느 무리 곡선과도 안 맞아 "), hl("「판정 보류」")],
      "FV 안에서도 느린 신품 5칩 중 2칩(chip12 · 21)은 빠른 속도로 늙어 상온 모델이 68% 0/12 — 개봉 전 한 점으로는 못 가른다",
    ]],
    ["욕조 곡선을 수명 지표로 못 썼다", "Δφ = 15.87ps", [
      [tx("1차는 물리 — 마진이 30만 회까지 안 움직였다(출력 레지스터가 엣지를 정함)")],
      [tx("2차는 장비 — 벽 천이가 위상 해상도보다 가팔라 한 스텝에 BER 10⁻⁴ → 5×10⁻². "), hl("욕조 바닥(10⁻⁴ 아래)과 10⁻¹² 외삽을 못 본다")],
      "MMCM VCO 고정 — 어느 클럭으로 올려도 같다",
    ]],
    ["칩 내부 온도를 모른다", "구리판 → 패키지", [
      "센서가 구리판 위 — 판 → 모듈 PCB(FR4) → 패키지 사이 온도 차를 재지 않았다(배치 기록도 없음)",
      [tx("다이 ↔ 패키지 표면은 자기 발열 약 65mW 로 1°C 미만(계산) — 문제는 "), hl("판 ↔ 패키지"), tx(" 쪽")],
      "85°C 근처 10°C 오차 = Arrhenius 가속 배율 약 2배",
    ]],
  ];
  lim.forEach((L, i) => {
    const x = ML + i * (cw + 0.3);
    card(s, x, 1.55, cw, 4.75);
    s.addShape(pres.ShapeType.rect, { x: x + 0.25, y: 1.75, w: 0.45, h: 0.45, fill: { color: ACC }, line: { color: ACC } });
    s.addText(String(i + 1), { x: x + 0.25, y: 1.75, w: 0.45, h: 0.45, fontSize: 15, bold: true, color: C.text1, align: "center", valign: "middle", margin: 0, isTextBox: true, fontFace: "Arial" });
    s.addText(L[0], { x: x + 0.85, y: 1.72, w: cw - 1.1, h: 0.55, fontSize: 14, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "middle" });
    s.addText(L[1], { x: x + 0.25, y: 2.4, w: cw - 0.5, h: 0.5, fontSize: 22, bold: true, color: C.text1, margin: 0, isTextBox: true, fontFace: "Arial" });
    body(s, bullets(L[2], 12.5, 9), x + 0.25, 3.05, cw - 0.5, 3.1, 12.5);
  });
  s.addNotes("1분. 1 은 「모르는 칩에 답하지 않는다」 가 기능으로 들어 있다는 것과 같이. 2 는 「보드가 나빠서」 가 아니라 「물리가 그렇고, 자의 눈금도 거기까지」 두 층으로. 3 은 정직하게 「이만큼 모른다」 로. 3 의 열저항 계산 근거(데이터시트 ICC · SOIC-8 ψ_JT)는 확인 필요.");
}

// ================= 14. 극복 =================
{
  const s = content(14, "극복 — 두 한계는 측정으로 닫을 수 있고, 얼마나 더 재면 되는지도 안다", "난이도 · 발표", "한계와 극복");
  const colw = (CW - 0.4) / 2;
  s.addText([tx("① 다른 IC 로 교정 곡선 만들기", { bold: true }), tx("  (한계 1)", { color: MUTE, fontSize: 11 })], { x: ML, y: 1.55, w: colw, h: 0.35, fontSize: 14.5, color: C.text1, margin: 0, isTextBox: true });
  s.addChart(pres.ChartType.line, [
    { name: "68% 적중", labels: ["1칩", "2칩", "3칩", "4칩", "5칩"], values: [27.2, 64.2, 73.3, 78.3, 81.4] },
    { name: "95% 적중", labels: ["1칩", "2칩", "3칩", "4칩", "5칩"], values: [46.3, 79.3, 89.5, 91.9, 91.4] },
  ], Object.assign({}, CH, {
    x: ML, y: 1.95, w: colw, h: 2.55, chartColors: [INK, MUTE], lineSize: 2, lineDataSymbol: "circle", lineDataSymbolSize: 7,
    showLegend: true, legendPos: "b", showValue: false, valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 25,
    showTitle: true, title: "학습 곡선 — 빠른 무리, 교정 칩 k 개 모든 조합 (%)",
  }));
  body(s, bullets([
    [hl("교정 3칩에서 포화"), tx(" — 1 → 3칩: 68% 27 → 73 · 95% 46 → 90 · 배율 오차 0.51 → 0.37, 3 → 5칩은 표준오차 안. 즉 품번 하나 = 무리당 3칩 × 10만 회(칩당 1 ~ 2일 무인)")],
    "첫 대상은 이미 신품 12칩을 쟀고 DF · D16x · CA 세 UID 꼴로 갈리는 W25Q64JV — FV 교정 절차 그대로",
    "느린 신품의 두 종류(chip12 · 21 형)는 개봉 때 짧은 추가 마모 Δx 로 노화 기울기(첫 1k 에 1.22 대 1.04~1.09)를 재서 가른다 — v4.4",
  ], 11.5, 6), ML, 4.6, colw, 2.3, 11.5);
  const x2 = ML + colw + 0.4;
  s.addText([tx("② 다른 지표 더하기", { bold: true }), tx("  (한계 2 · 고마모 상한)", { color: MUTE, fontSize: 11 })], { x: x2, y: 1.55, w: colw, h: 0.35, fontSize: 14.5, color: C.text1, margin: 0, isTextBox: true });
  body(s, bullets([
    [tx("소거 시간 한 지표의 정보 한계: 빠른 무리는 160k 뒤 평탄 · 정답 80k 이상에서 0.84 과소추정 — 통계 처리 후보 7개로 안 풀렸고 "), hl("측정으로만"), tx(" 풀린다")],
    [tx("후보 ① "), hl("Δx(짧은 추가 마모)"), tx(": 5천 회 추가 시 68% 폭 23,500 → 13,000(약 45%↓, 저마모) — 비파괴성은 조금 잃는다")],
    [tx("후보 ② "), hl("프로그램 시간"), tx(": v4.2 로 시험 — 폭 34k → 29k 이나 칩마다 오르는 양이 달라 과신(합성 95% 96 → 84). 프로그램의 칩 효과를 따로 재면 다시 쓸 수 있다")],
    "후보 ③ 섹터 간 산포 · 계단 유무 자체를 특징으로 — 느린 무리의 분포 폭 두 배가 이미 표지",
    [tx("한계 3 은 단열 상자 + 패키지 위 두 번째 TMP117(주소 ADD0) + 배치 사진을 시작 조건으로 — 이미 사양에 규칙으로", { color: MUTE })],
  ], 11.5, 7), x2, 1.95, colw, 4.9, 11.5);
  s.addNotes("1분. 「표본이 부족해서 모른다」 가 아니라 「무리당 3칩이면 된다는 것을 쟀다」 가 메시지. 두 번째 지표는 이미 한 번 시도해 왜 실패했는지까지 안다.");
}

// ================= 15. 칭찬 · 발전 =================
pres.addSection({ title: "맺음" });
{
  const s = content(15, "20만 원대 벤치로, 비파괴 측정 1 ~ 5분에, 「몇 번 썼나」 를 믿을 수 있는 구간으로 — 그 길은 NAND 로 이어진다", "발표 · 창의성", "맺음");
  const cw = (CW - 0.9) / 4;
  [
    ["59초", "위상 스윕 1회", "N = 112 · 5.78억 비트"],
    ["40초", "역산 입력 prep 1회", "계산 수 초 · 칩을 떼지 않는다"],
    ["3칩", "교정 포화점 (빠른 무리)", "남는 오차는 칩 수가 아니라 개체 속도 차"],
    ["31 · 18 · 8", "신품 · 마모 · 200k 이상 칩", "300k 1 · 블라인드 2 · 온도 5 — 4개월"],
  ].forEach((d, i) => stat(s, ML + i * (cw + 0.3), 1.55, cw, d[0], d[1], d[2]));
  s.addText("[확인 필요: 총 부품비 — Zybo Z7-20 + 소켓 보드 + 히터 벤치]", { x: ML, y: 3.3, w: 6, h: 0.3, fontSize: 10, color: C.text2, margin: 0, isTextBox: true });
  s.addText("발전 가능성", { x: ML, y: 3.8, w: 4, h: 0.4, fontSize: 15, bold: true, color: C.text1, margin: 0, isTextBox: true });
  const dev = [
    ["SPI NAND (W25N)", "비트 에러 · ECC · Fail Map 이 등장하는 일반화 단계 — 같은 벤치의 RTL 로 간다"],
    ["품번별 교정 곡선 라이브러리", "무리당 3칩 규칙으로 품번 하나씩"],
    ["「모른다」 고 말하는 판정", "개체 지문(UID 꼴 · 신품 폭)으로 교정 밖 칩을 보류"],
    ["온도 축 · 전압 축", "레벨 시프터 보드 — 온도 계수(ps/°C) · 전압 민감도"],
  ];
  const dw = (CW - 0.9) / 4;
  dev.forEach((d, i) => {
    const x = ML + i * (dw + 0.3);
    card(s, x, 4.3, dw, 2.4);
    s.addShape(pres.ShapeType.rect, { x: x + 0.2, y: 4.5, w: 0.3, h: 0.3, fill: { color: ACC }, line: { color: ACC } });
    s.addText(d[0], { x: x + 0.2, y: 4.9, w: dw - 0.4, h: 0.55, fontSize: 13, bold: true, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
    s.addText(d[1], { x: x + 0.2, y: 5.5, w: dw - 0.4, h: 1.1, fontSize: 11, color: C.text1, margin: 0, isTextBox: true, valign: "top" });
  });
  s.addNotes("45초 + 시연 확인 1분. (영웅) 「시연 확인하시겠습니다」 — 2장에서 돌려 둔 터미널로 돌아가 결과 줄(칩 · 무리 · 배율 · 추정 · 68% / 95% · 판정)을 읽는다. [TODO: 시연 칩 · 기대 출력]. v4.3 은 6장 → 7장 곡선에서 판정 불변 — 교정 곡선이 쌓일수록 모델 식을 안 바꾸고 정확해지는 구조.");
}

(async () => {
  const out = __dirname + "/errorATE_final_draft.pptx";
  await pres.writeFile({ fileName: out });
  await applyTheme(out, THEME);
  // pptxgenjs writes one <a:pPr> per run inside a paragraph; keep only the first (the one carrying the bullet)
  const fs = require("fs"); const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(out));
  for (const name of Object.keys(zip.files).filter(f => /^ppt\/slides\/slide\d+\.xml$/.test(f))) {
    let xml = await zip.file(name).async("string");
    xml = xml.replace(/<a:p>([\s\S]*?)<\/a:p>/g, (m, inner) => {
      let seen = false;
      const cleaned = inner.replace(/<a:pPr\b[^>]*\/>|<a:pPr\b[^>]*>[\s\S]*?<\/a:pPr>/g, pp => { if (seen) return ""; seen = true; return pp; });
      return "<a:p>" + cleaned + "</a:p>";
    });
    zip.file(name, xml);
  }
  fs.writeFileSync(out, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log("wrote", out);
})();
