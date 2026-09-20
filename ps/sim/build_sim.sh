#!/bin/bash
# build_sim.sh — 마모 엔진 호스트 시뮬레이션 빌드: build/sim/flash_wear_sim
#
# 같은 flash_wear.c 를 fake NOR(flash_io_fake.c) + stdin/stdout 플랫폼(wear_plat_host.c) 위에 올린다.
# host/tests/test_sim.py 의 fixture 가 이것을 부르고, host/run/wear_link.py 가 파이프로 띄운다.
# git_rev 는 여기서 wear_build.h 로 넣는다 (하드코딩 금지).
set -e
REPO=$(cd "$(dirname "$0")/../.." && pwd)
OUT=$REPO/build/sim
mkdir -p "$OUT"
REV=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)
echo "#define WEAR_GIT_REV \"$REV\"" > "$OUT/wear_build.h"
${CC:-gcc} -std=c11 -O1 -Wall -Wextra -Werror \
    -I"$REPO/ps/sim" -I"$REPO/ps/src" -I"$OUT" \
    "$REPO/ps/src/flash_wear.c" "$REPO/ps/sim/flash_io_fake.c" "$REPO/ps/sim/wear_plat_host.c" \
    -o "$OUT/flash_wear_sim"
echo "== done: $OUT/flash_wear_sim (git_rev $REV)"
