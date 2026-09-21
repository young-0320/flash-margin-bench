# 작업 로그 

## 이 폴더의 기준

> **로그는 "왜 이렇게 만들었나"에 대한 답이지 일지가 아니다.**
> 수치·현황은 `results/`·`spec/`·등록부에, **결정 근거와 의도, 그리고 경위는 로그에.**
> — 커밋 `1535ad8` (2026-09-17). `docs/CONTRIBUTING.md` §1 「폴더별 역할 상세」와 같은 규정.

그래서 아래 한 줄 요약은 "무엇을 했나"가 아니라 **그 로그에만 있는 판단**을 가리킨다.
수치를 찾는다면 로그가 아니라 `docs/results/` · `docs/spec/` · `docs/chip_registry.md` 다.

---

## 서식 규약

**[FORMAT.md](FORMAT.md)** — 무엇을 담고 무엇을 담지 않나, 골격·머리말·절별 규칙.
한영웅 로그에 강제, `jimin/`·`seeun/` 는 제안이다.

---

# 한영웅

## 1기 — 계약과 시뮬레이션 (7/06 ~ 7/07)

| # | 로그                                                                 | 여기에만 있는 것                                   |
| - | -------------------------------------------------------------------- | -------------------------------------------------- |
| 1 | [몬테카를로·산출물 정책](young/1.monte_carlo_and_artifact_policy.md) | 산출물 정책의 출발점                               |
| 2 | [중간보고서 스프린트](young/2.midterm_sprint_mode.md)                 | 게재 목록 확정                                     |
| 3 | [인터페이스 계약 v1](young/3.interface_contract_v1.md)                | 결정 21건의**후보·장단점·탈락 이유**,`core`=계측제어 / `flash`=경로 분리 |
| 5 | [욕조 곡선 스크립트 v1](young/5.bathtub_script_contract_upgrade.md)   | 게재 1번 소프트웨어 완성                           |

## 2기 — RTL 구현과 G0 루프백 (7/07 ~ 7/09)

| #  | 로그                                                                                | 여기에만 있는 것                                                                |
| -- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 6  | [core RTL](young/6.core_rtl_implementation.md)                                       | MMCM 위상 제어 + AXI-Lite 레지스터 파일                                         |
| 7  | [flash RTL](young/7.flash_loopback_rtl.md)                                           | G0 루프백 프런트엔드, 프레이밍 재정렬                                           |
| 8  | [Vivado 통합 + 스윕 SW](young/8.vivado_integration_and_sweep_sw.md)                  | 비트스트림·XSA·베어메탈·수신기 첫 관통                                       |
| 9  | [G2 JEDEC 브링업 준비](young/9.g2_jedec_bringup_prep.md)                             | **앱 소유권 배분** (`flash_jedec`=장세은, 별다른 이유 없으면 수정 지양) |
| 10 | [실칩 앞 의사결정 라운드](young/10.realchip_sweep_decisions.md)                      | 5건 확정·1건 대기 — 실칩 정책의 원점                                          |
| 11 | [SPI 마스터 RTL](young/11.spi_master_rtl.md)                                         | `0x0B` 40클럭 프레임 고정 — 뒤에 UID 를 막는 제약                            |
| 12 | [실칩 준비 일괄](young/12.realchip_prep_batch.md)                                    | 테스트 계획 ·`flash_prep` · 클럭 사다리 3벌                                 |
| 13 | [첫 욕조 곡선 + line_dead 수정](young/13.first_loopback_bathtub_and_linedead_fix.md) | 자가진단 오발의 원인                                                            |
| 14 | [세은 브링업 코드 리뷰](young/14.seeun_bringup_code_review.md)                       | 2벌 리뷰 + 실기 검증                                                            |
| 15 | [G3 25·45MHz 완주](young/15.g3_25mhz_wall_too_narrow.md)                            | **벽 천이가 Δφ보다 가팔라 체크1 구조적 SKIP**                           |

## 3기 — 마모 벤치 사양 확정 (8/20 ~ 8/23)

| #  | 로그                                                        | 여기에만 있는 것                                   |
| -- | ----------------------------------------------------------- | -------------------------------------------------- |
| 16 | [마모 벤치 사양 결정](young/16.wear_bench_spec_decisions.md) | 역할 재정의, 워크플로 5 신설                       |
| 17 | [S-1 사양 확정](young/17.wear_bench_spec_finalization.md)    | **모든 수치의 채택 근거** (최장 로그, 597줄) |
| 18 | [docs 구조 감사](young/18.docs_structure_audit.md)           | `spec/` 신설, 문서-리포 정합 복구                |
| 19 | [S-3 G1 기준 동결과 개정 2](young/19.g1_acceptance_freeze.md) | 오라클 출처·판정 3단 · 미비점 8건 해소           |
| 21 | [S-2 전수 측정 프로토콜](young/21.newchip_protocol.md)       | **되돌릴 수 없는 측정의 사전 등록**          |

## 4기 — 실칩 스윕 파이프라인 (9/07 ~ 9/08)

| #  | 로그                                                                 | 여기에만 있는 것                                                                   |
| -- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| 22 | [D 트랙 1차 실측](young/22.d_track_drift_sweep.md)                    | 스윕 2건 사후 기록, 판정 보류                                                      |
| 23 | [래퍼·UID 파이프라인 설계](young/23.sweep_wrapper_and_uid_design.md) | **라벨을 사람이 입력하지 않는다** · 부록 A(오배치 위험) — 가장 많이 참조됨 |
| 24 | [같은 것의 구현과 검토](young/24.sweep_wrapper_uid_pipeline_impl.md)  | 로그 23 설계의 코드화 · §8 「중요 1」 —`#PREP ERROR` 를 종료 신호로 읽는 규약    |

## 5기 — 재개와 신품 전수 측정 (9/14 ~ 9/17)

| #  | 로그                                                                          | 여기에만 있는 것                                                                                          |
| -- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| 26 | [재개 + 9/15 절차](young/26.resume_after_papers_and_day_plan.md)               | 팀원 논문 조사 반영                                                                                       |
| 27 | [Vivado 2025.2 통일 계획](young/27.vivado_2025_2_migration_plan.md)            | 워크플로 8, A/B 재기준선 생략 결정                                                                        |
| 28 | [9/15 실칩 검증일](young/28.realchip_day_chip02_chip03.md)                     | chip02·chip03 신품 측정과 그날의 결정                                                                    |
| 29 | [P/E 엔진 구현 층위](young/29.pe_engine_layer_decisions.md)                    | `N_READS` 112 치환 근거                                                                                 |
| 30 | [`flash_prep` 신품 조사 확장](young/30.flash_prep_newchip_survey.md)         | G-b·G-d 구현 명세 · §10.3 보 레이트                                                                    |
| 32 | [`reproduce.py`](young/32.reproduce_script.md)                               | 빌드·검증 원샷 재현 + 채점                                                                               |
| 33 | [Windows 대응 — 다섯 벽](young/33.reproduce_windows_support.md)                | 셸 의존 제거 ·`.bat` 런처 · `PYTHONUTF8=1` 강제 · §4 빌드 신원 관리(보류)                               |
| 36 | [`flash_id` + sweep UID 대조](young/36.flash_id_and_sweep_uid_check.md)      | **P/E 없는 신원 확인** · §2-7 리팩터 동등성 증거 · §2-10 **재장착 70ps** · §5 설계 결정 |
| 38 | [로그 서식 규약](young/38.log_format_convention.md)                          | **로그가 담을 것과 담지 않을 것의 판별선** · 골격 다섯 · 전 34편 계측 |
| 39 | [규약 집행 — 스킬과 검사기](young/39.log_convention_enforcement.md)         | 규범은 README, 집행은 스킬 · **산문 주의사항은 체크리스트가 아니다** |
| 40 | [로그 전수조사](young/40.log_audit_and_its_byproducts.md)                     | **자를 못 맞췄다** — 줄이는 힘은 병합·결번에서만 나온다 · 「3인 추인」은 합의된 적 없는 표기였다 |
| 41 | [블랙박스 TB · 엔진 인터페이스](young/41.blackbox_tb_and_engine_interface.md)  | **구현자가 짜는 채점표를 어떻게 믿나** · 경계 7개는 S-1 §13 이 요구하는 것에서 나온다 |
| 42 | [블랙박스 TB 미비점 보완](young/42.blackbox_tb_gaps_and_jimin_reply.md)  | **표에 적힌 것과 실제로 재는 것이 갈라진 자리** · 집행 장치가 없는 인수 조건은 비어도 초록이 난다 |
| 43 | [전수 측정 — 앵커가 고장났다](young/43.newchip_survey_anchor_failure.md)  | **유효한 런과 해석 가능한 런은 다르다** · 기준 개체가 자기 열화를 보고 있으면 게이트가 자기 참조가 된다 · 재장착 σ 13.86 vs 137.33 |
| 44 | [P/E 엔진 구현 전 검토](young/44.pe_engine_prebuild_review.md)  | **경계에 「이어 돌릴」 명령이 없다** · mux 의 전제(체크포인트 무리셋)는 스윕이 부팅 1회 1회라 성립하지 않는다 · 파일럿은 리셋 수용을 권고 |
| 45 | [P/E 엔진 구현 — 실칩 앞에서 멈췄다](young/45.pe_engine_build_to_sim.md)  | **정본이 비워 둔 디테일 10건의 채택값** · 잔류 없는 섹터를 지우는 것은 마모다 · C 엔진은 리셋=프로세스 재시작인 호스트 시뮬레이션이 같은 TB 로 잰다 |
| 46 | [실칩 전 마지막 두 자물쇠 — probe 와 tally 소거](young/46.probe_tally_erase_and_reproduce_wear.md)  | **0 은 「제대로 재고 0」과 「세는 경로가 죽어서 0」이 같아 보인다** · tally 를 지우는 열쇠는 UID 타이핑 + 장부 먼저 · reproduce 는 재현물만 덮으니 자유 실행 |
| 48 | [파일럿 마모 실행기 — 승인은 계획 화면에서](young/48.pilot_wear_handler_and_plan_approval.md)  | **tally 는 영역을 세지 않는다 — 안 지우면 x축이 통째로 밀린다** · 플래그는 읽지 않고도 칠 수 있다 · 누적으로 채점하면 이어 돌리기가 영원히 FAIL · 계측기 교체는 칩 경계에서 |
| 47 | [문서 3층 — 명령은 commands.md 한 곳](young/47.docs_three_tiers_commands_single_source.md)  | **같은 명령 문장이 세 곳에 있으면 하나를 고칠 때 둘이 낡는다** · 런북은 날짜순이라 정본이 될 수 없다 · README 는 본질과 포인터만 |

## 결번 — 4 · 20 · 25 · 31 · 34 · 35 · 37 

---

# 장세은 

| # | 로그                                                               | 여기에만 있는 것                         |
| - | ------------------------------------------------------------------ | ---------------------------------------- |
| 1 | [Windows 빌드 트러블슈팅](seeun/1.windows_build_troubleshooting.md) | FPGA/Vitis Windows 환경 수동 빌드 가이드 |

---

# 박지민 

| # | 로그                                                                 | 여기에만 있는 것                   |
| - | -------------------------------------------------------------------- | ---------------------------------- |
| 1 | [P/E 노화 실험 아이디어](jimin/1.pe_wear_bench_idea.md)               | 마모 벤치의 최초 착상 (9/14)       |
| 2 | [P/E 스트레스 벤치 AI 프롬프트](jimin/2.pe_stress_bench_ai_prompt.md) | 구현 의뢰용 프롬프트 (9/15)        |
| 3 | [cocotb 검증 환경 계획](jimin/3.cocotb_verification_plan.md)          | G1 회귀 계획 (9/15)                |
| 4 | [Vivado/Vitis 빌드 명령어](jimin/4.vivado_vitis_build_commands.md)    | 전체 빌드 명령 정리                |
| 5 | [WSL USB 포트 연결](jimin/5.wsl_usbipd_jtag_uart_connection.md)       | usbipd 로 JTAG·UART 붙이기 (9/16) |
