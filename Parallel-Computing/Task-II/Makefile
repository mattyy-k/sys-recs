CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic
ring: ring.c
	$(CC) $(CFLAGS) -pthread -o $@ $<
clean:
	rm -f ring
.PHONY: clean
