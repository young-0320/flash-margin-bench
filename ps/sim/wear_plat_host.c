/*
 * wear_plat_host.c — wear_plat.h 의 호스트 구현 (stdin/stdout 파이프 · CLOCK_MONOTONIC).
 *
 * host/run/wear_link.py 가 이 프로세스를 파이프로 띄워 UART 대신 쓴다. stdin 이 닫히면 끝낸다.
 */

#define _POSIX_C_SOURCE 200809L
#include "wear_plat.h"

#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

static struct timespec t0;

void plat_init(void)
{
    clock_gettime(CLOCK_MONOTONIC, &t0);
    setvbuf(stdout, NULL, _IOLBF, 0);
}

void plat_puts(const char *s)
{
    fputs(s, stdout);
    fflush(stdout);
}

int plat_getc(void)
{
    struct pollfd p = { .fd = STDIN_FILENO, .events = POLLIN };
    if (poll(&p, 1, 1) <= 0)                       /* 1ms — 유휴 루프가 CPU 를 다 먹지 않게 */
        return -1;
    unsigned char c;
    ssize_t n = read(STDIN_FILENO, &c, 1);
    if (n == 0)
        exit(0);                                    /* 호스트가 파이프를 닫았다 */
    if (n < 0)
        return -1;
    return c;
}

uint64_t plat_now_us(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (uint64_t)(t.tv_sec - t0.tv_sec) * 1000000ULL
         + (uint64_t)((t.tv_nsec - t0.tv_nsec) / 1000);
}
