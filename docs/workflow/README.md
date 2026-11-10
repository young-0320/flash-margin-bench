# 워크플로 목록

워크플로는 **그날(국면)의 순서**다. 명령의 정본은 `../commands.md`, 흐름·상태·이유는
`../project_pipeline.md` — 날이 끝나면 통한 명령은 commands 로, 알게 된 흐름·함정은 파이프라인으로
올라가고 워크플로는 날짜 붙은 기록으로 남는다. **새 워크플로를 쓰면 아래 표에 한 줄 등재한다**
(`../log/README.md` 와 같은 규칙). 번호는 재사용하지 않는다.

**지금 진입점** — 빌드·검증 `commands.md` §1 · 실칩 측정 §2 · P/E 엔진 §3 (절차·판독은 12) ·
게이트별 기대 출력은 4.

| # | 문서 | 작성일 | 무엇 | 지금 |
| - | ---- | ------ | ---- | ---- |
| 1 | [중간보고서 게재 항목 작업](1.midterm_report_workflow.md) | 2026-07-06 | 7/10 보고서용 게재물 작업 순서 | 닫힘 |
| 2 | [G0 Vivado 통합 및 XDC](2.g0_vivado_integration_and_xdc.md) | 2026-07-07 | 루프백 RTL 통합·제약 | 닫힘 — 빌드는 `build_reproduction.md` |
| 3 | [실칩의 날 런북](3.realchip_day_runbook.md) | 2026-07-08 | 추인·통지·루프백·실칩 곡선. 표 E 고장 판독 | 7 → 12 로 이어짐. 명령은 commands §2·§4 |
| 4 | [게이트 지도 G0~G5](4.gate_map.md) | 2026-07-09 | 게이트가 무엇을 증명하나·설계·산출물·기대 출력 | **현행** (파이프라인의 게이트 정의 원전) |
| 5 | [재개 워크플로 — 신품 기준선과 마모 벤치](5.newchip_baseline_and_wear_bench.md) | 2026-08-20 (갱신 09-18) | G5 개시 준비 트랙 W5-S~G | 10 으로 이어짐 |
| 6 | [G1 착수와 기준 정밀화](6.g1_launch_and_spec_hardening.md) | 2026-08-23 | cocotb 회귀 트랙 W6-H·R·C | 닫음 (2026-11-11, 공모전 종료) — 남은 것은 G1 게이트 개방 기록(`../spec/s3.g1_review.md`, 개방일 미기입)과 F11·F12(BASE_SECTOR 수정안 #1 미반영이라 제외 2). G1 현황: 회귀 21항목 PASS(9/23, 작성자 실행) · ① 판정 3블록 미판정 · F11 · F12 제외 · 게이트 미개방 (`../log/jimin/7.cocotb_g1_progress.md`) |
| 7 | [실칩 검증일 — UID 확보 + 재장착 σ](7.realchip_uid_verification_day.md) | 2026-09-14 | 새 래퍼로 chip01 UID·재장착 | 닫힘. 명령은 commands §2 |
| 8 | [Vivado 2025.2 통일](8.vivado_2025_2_migration_and_rebaseline.md) | 2026-09-14 | 설치·재빌드·재기준선·조원 PC 전개 W8-I~D | 닫힘 — 조원 PC 절차는 `build_reproduction.md` §1·§2 |
| 9 | [9/15 회의 — 역할 배분](9.sept_meeting_role_split.md) | 2026-09-14 | 마모 국면 역할과 선결 셋 | 닫힘 (로그 29·44) |
| 10 | [신품 전수 측정 완주와 G5](10.newchip_survey_completion.md) | 2026-09-16 (갱신 09-20) | 측정 8/10, 판정 보류 | 닫음 (2026-11-11, 공모전 종료) — 신품 전수 31칩 완주 (2026-10-25), 집계는 `../results/data/newchip_survey_2026-09.md` |
| 11 | [로그 전수조사](11.log_convention_migration.md) | 2026-09-17 | 로그 규약 이행 W11-A~E | 닫힘 (로그 40) |
| 12 | [P/E 엔진 실칩 인수 런북](12.pe_engine_acceptance_runbook.md) | 2026-09-21 | A(100사이클)·B(전원 차단) 돌리는 법과 읽는 법 | **현행** — 실칩 인수 완료 (2026-09-22). 명령은 commands §3 |
| 13 | [PE 종료 뒤 문서 갱신 체크리스트](13.pe_end_doc_update_checklist.md) | 2026-10-03 | 상온·온도 PE 가 끝났을 때 고칠 문서 · 원천 raw · 순서 | **현행** — 일괄 명령 `pe_end.py` (§4) · 사람 체크리스트 §6 |
| 14 | [공모전 · 졸업논문 · 학회 — 범위와 마일스톤](14.contest_thesis_paper_milestones.md) | 2026-10-05 | 세 결과물의 넣는 것 · 넣지 않는 것 · 데이터 마감 · 할 일 | **현행** — M1 공모전 끝 (11/6 발표) · 지금은 M2 졸업논문 |

「지금」 열은 색인용 한 줄이다 — 정확한 상태는 각 문서의 머리말이 정본이다.
