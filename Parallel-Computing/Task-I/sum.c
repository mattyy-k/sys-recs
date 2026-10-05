#define _POSIX_C_SOURCE 200809L
#include <inttypes.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#define WORKERS 4
struct job {
  const uint64_t *a;
  size_t begin, end, stride;
  uint64_t sum;
};
static void *sum_range(void *p) {
  struct job *j = p;
  uint64_t s = 0;
  for (size_t i = j->begin; i < j->end; i += j->stride)
    s += j->a[i];
  j->sum = s;
  return NULL;
}
static uint64_t run(const uint64_t *a, size_t n, int mode, double *seconds) {
  struct timespec t0, t1;
  clock_gettime(CLOCK_MONOTONIC, &t0);
  uint64_t total = 0;
  if (mode == 0) {
    for (size_t i = 0; i < n; i++)
      total += a[i];
  } else {
    pthread_t th[WORKERS];
    struct job j[WORKERS];
    for (size_t k = 0; k < WORKERS; k++) {
      j[k] = (struct job){a, mode == 1 ? k : k * n / WORKERS,
                          mode == 1 ? n : (k + 1) * n / WORKERS,
                          mode == 1 ? WORKERS : 1, 0};
      if (pthread_create(&th[k], NULL, sum_range, &j[k])) {
        perror("pthread_create");
        exit(1);
      }
    }
    for (int k = 0; k < WORKERS; k++) {
      pthread_join(th[k], NULL);
      total += j[k].sum;
    }
  }
  clock_gettime(CLOCK_MONOTONIC, &t1);
  *seconds = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) * 1e-9;
  return total;
}
static uint64_t rng_state = 0x6a09e667f3bcc909ULL;
static uint64_t next_random(void) {
  rng_state ^= rng_state << 13;
  rng_state ^= rng_state >> 7;
  rng_state ^= rng_state << 17;
  return rng_state;
}
int main(int argc, char **argv) {
  size_t n = argc > 1 ? strtoull(argv[1], NULL, 10) : 10000000;
  int trials = argc > 2 ? atoi(argv[2]) : 7;
  if (n < 1024 || trials < 1) {
    fprintf(stderr, "usage: %s N(>=1024) [trials(>=1)]\n", argv[0]);
    return 2;
  }
  uint64_t *a = malloc(n * sizeof(*a));
  if (!a) {
    perror("malloc");
    return 1;
  }
  for (size_t i = 0; i < n; i++)
    a[i] = next_random();
  const char *name[] = {"single", "strided", "contiguous"};
  double sumtime[3] = {0};
  uint64_t expected = 0;
  for (int t = 0; t < trials; t++)
    for (int m = 0; m < 3; m++) {
      double sec;
      uint64_t v = run(a, n, m, &sec);
      if (m == 0 && t == 0)
        expected = v;
      if (v != expected) {
        fprintf(stderr, "sum mismatch\n");
        free(a);
        return 1;
      }
      sumtime[m] += sec;
    }
  printf("N=%zu trials=%d values=deterministic xorshift64 sequence (seed "
         "0x6a09e667f3bcc909)\n",
         n, trials);
  printf("sum=%" PRIu64 "\n", expected);
  for (int m = 0; m < 3; m++)
    printf("%-11s mean_seconds=%.9f\n", name[m], sumtime[m] / trials);
  printf("speedup vs single: strided=%.3fx contiguous=%.3fx\n",
         sumtime[0] / sumtime[1], sumtime[0] / sumtime[2]);
  free(a);
  return 0;
}
