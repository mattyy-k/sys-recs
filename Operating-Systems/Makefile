CXX ?= c++
CXXFLAGS ?= -std=c++17 -O2 -Wall -Wextra -Wpedantic

.PHONY: all clean
all: ext2

ext2: ext2.cpp
	$(CXX) $(CXXFLAGS) $< -o $@

clean:
	rm -f ext2
