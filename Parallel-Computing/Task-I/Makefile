CC ?= cc
CFLAGS ?= -O2 -std=c11 -Wall -Wextra -Wpedantic
sum: sum.c
	$(CC) $(CFLAGS) -pthread -o $@ $<
clean:
	rm -f sum
.PHONY: clean
