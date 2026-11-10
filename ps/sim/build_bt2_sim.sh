#!/bin/bash
# build_bt2_sim.sh — 욕조 v2 펌웨어 호스트 시뮬레이션 빌드: build/sim/bathtub_v2_sim_<mhz>
#
# 같은 bathtub_v2.c 를 (bathtub_v2_gen.py 로 클럭 묶음을 치환한 사본으로) 가짜 core(bt2_core_fake.c) 위에 올린다.
# Xilinx 헤더는 ps/sim/ 의 심(xil_io.h · xil_printf.h · xparameters.h · xuartps.h)이 대신한다.
# host/tests/test_bathtub2.py 가 이것을 부르고 stdout(UART 대신)을 캡처에 흘린다.
#   사용: ps/sim/build_bt2_sim.sh [25|75]   (기본 25)
set -e
REPO=$(cd "$(dirname "$0")/../.." && pwd)
MHZ=${1:-25}
OUT=$REPO/build/sim
mkdir -p "$OUT/bt2_gen_$MHZ"
python3 "$REPO/ps/scripts/bathtub_v2_gen.py" "$MHZ" "$OUT/bt2_gen_$MHZ/bathtub_v2.c"
${CC:-gcc} -std=c11 -O2 -Wall -Wextra -Werror \
    -I"$REPO/ps/sim" \
    "$OUT/bt2_gen_$MHZ/bathtub_v2.c" "$REPO/ps/sim/bt2_core_fake.c" -lm \
    -o "$OUT/bathtub_v2_sim_$MHZ"
echo "== done: $OUT/bathtub_v2_sim_$MHZ"
