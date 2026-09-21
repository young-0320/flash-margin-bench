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
| 6 | [G1 착수와 기준 정밀화](6.g1_launch_and_spec_hardening.md) | 2026-08-23 | cocotb 회귀 트랙 W6-H·R·C | 진행 (지민) |
| 7 | [실칩 검증일 — UID 확보 + 재장착 σ](7.realchip_uid_verification_day.md) | 2026-09-14 | 새 래퍼로 chip01 UID·재장착 | 닫힘. 명령은 commands §2 |
| 8 | [Vivado 2025.2 통일](8.vivado_2025_2_migration_and_rebaseline.md) | 2026-09-14 | 설치·재빌드·재기준선·조원 PC 전개 W8-I~D | 닫힘 — 조원 PC 절차는 `build_reproduction.md` §1·§2 |
| 9 | [9/15 회의 — 역할 배분](9.sept_meeting_role_split.md) | 2026-09-14 | 마모 국면 역할과 선결 셋 | 닫힘 (로그 29·44) |
| 10 | [신품 전수 측정 완주와 G5](10.newchip_survey_completion.md) | 2026-09-16 (갱신 09-20) | 측정 8/10, 판정 보류 | 진행 |
| 11 | [로그 전수조사](11.log_convention_migration.md) | 2026-09-17 | 로그 규약 이행 W11-A~E | 닫힘 (로그 40) |
| 12 | [P/E 엔진 실칩 인수 런북](12.pe_engine_acceptance_runbook.md) | 2026-09-21 | A(100사이클)·B(전원 차단) 돌리는 법과 읽는 법 | **현행** — 실칩 미실시. 명령은 commands §3 |

「지금」 열은 색인용 한 줄이다 — 정확한 상태는 각 문서의 머리말이 정본이다.
