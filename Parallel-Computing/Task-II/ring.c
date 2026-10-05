#include <assert.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <threads.h>
#define CAP 8u
#define COUNT 100000u
typedef struct {
  int data[CAP];
  _Atomic size_t head, tail;
} ring_t;
static bool push(ring_t *q, int v) {
  size_t h = atomic_load_explicit(&q->head, memory_order_relaxed);
  size_t t = atomic_load_explicit(&q->tail, memory_order_acquire);
  if (h - t == CAP)
    return false;
  q->data[h & (CAP - 1)] = v;
  atomic_store_explicit(&q->head, h + 1, memory_order_release);
  return true;
}
static bool pop(ring_t *q, int *v) {
  size_t t = atomic_load_explicit(&q->tail, memory_order_relaxed);
  size_t h = atomic_load_explicit(&q->head, memory_order_acquire);
  if (t == h)
    return false;
  *v = q->data[t & (CAP - 1)];
  atomic_store_explicit(&q->tail, t + 1, memory_order_release);
  return true;
}
typedef struct {
  ring_t *q;
} arg_t;
static int producer(void *p) {
  ring_t *q = ((arg_t *)p)->q;
  for (int i = 0; i < (int)COUNT; i++) {
    while (!push(q, i))
      thrd_yield();
    printf("added %d\n", i);
  }
  return 0;
}
static int consumer(void *p) {
  ring_t *q = ((arg_t *)p)->q;
  for (int i = 0; i < (int)COUNT; i++) {
    int v;
    while (!pop(q, &v))
      thrd_yield();
    assert(v == i);
    printf("removed %d\n", v);
  }
  return 0;
}
int main(void) {
  ring_t q = {.head = ATOMIC_VAR_INIT(0), .tail = ATOMIC_VAR_INIT(0)};
  int v;
  assert(!pop(&q, &v));
  for (size_t i = 0; i < CAP; i++)
    assert(push(&q, (int)i));
  assert(!push(&q, 99));
  for (size_t i = 0; i < CAP; i++) {
    assert(pop(&q, &v) && v == (int)i);
  }
  assert(!pop(&q, &v));
  for (size_t i = 0; i < 3 * CAP; i++) {
    assert(push(&q, (int)i));
    assert(pop(&q, &v) && v == (int)i);
  }
  puts("empty/full/wraparound checks passed");
  thrd_t prod, cons;
  arg_t a = {&q};
  assert(thrd_create(&prod, producer, &a) == thrd_success);
  assert(thrd_create(&cons, consumer, &a) == thrd_success);
  int r;
  thrd_join(prod, &r);
  thrd_join(cons, &r);
  assert(atomic_load(&q.head) == atomic_load(&q.tail));
  puts("concurrent FIFO check passed");
}
