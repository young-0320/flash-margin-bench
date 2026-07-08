# sweep_loopback_20260708T131310Z — 유래와 재현

동명 CSV는 **게재 수치의 근거가 된 실측 요약본**(스텝당 집계 — 접미어 없는 쪽이 요약, `_reads`가 읽기별 원본; 계약 §6 명명)이다. 실측은 재실행하면 비슷한 값이 나올 뿐 같은 데이터가 나오지 않으므로 요약본은 커밋해 보존하고, 무거운 원본은 커밋하지 않는다 — 소재와 재생 방법만 아래에 남긴다. 게재 데이터셋마다 이런 동명 `.md`를 하나씩 둔다.

| 항목 | 값 |
| --- | --- |
| 대상 | G0 루프백 (JE1↔JE2 점퍼, Zybo Z7) |
| 측정 시각 | 2026-07-08T13:13:10Z |
| 측정 시점 rev | 9930994 (+ 미커밋 g0_sweep.c `!low_seen` 게이트 = eaa0fa1과 동일 내용) |
| 조건 | 25MHz, 2,520스텝 × 100읽기 × 2,048비트, Δφ=15.873ps |
| 결과 | 폭 34,693ps @θ=10⁻², σⱼ=29.1/29.2ps, valid=1 완주 |
| 게재 그림 | `../plots/bathtub_sweep_loopback_20260708T131310Z.png` |

- **읽기별 원본** `*_reads.csv`(2.4MB, 버스트성 F검정·R8 교차검증용): git 미추적, `build/data/`에 잔존. 유실 시 재측정으로만 재생.
- **그림 재생** (짝 파일이 있는 곳에서 — R8 검사가 동반 원본을 요구):
  `.venv/bin/python host/analysis/bathtub_analysis.py build/data/sweep_loopback_20260708T131310Z.csv`
- **재측정** (새 스탬프의 새 데이터가 됨): 런북 `docs/workflow/3.realchip_day_runbook.md` C절차.
