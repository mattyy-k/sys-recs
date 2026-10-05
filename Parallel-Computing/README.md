# Parallel Computing recruitment tasks

The implementation is split by assignment task. Task I and II build and run on Linux with a C11 compiler and pthread support. Task III targets Android NDK and an Android device with OpenGL ES 3.1 compute-shader support.

## Task I: array summation

`Task-I/sum.c` creates a deterministic pseudorandom `uint64_t` array, then times a serial pass, four pthread workers using `i, i+4, ...`, and four workers using contiguous quarter ranges. Thread creation and joins are inside each timed parallel run, so measurements represent total caller-visible completion cost. It verifies every result, takes multiple trials, and prints means and speedups. The fixed xorshift seed makes arrays reproducible. Sums use standard unsigned 64-bit arithmetic (modulo 2^64). On this x86_64 WSL2 Linux host, `Task-I/sum 10000000 7` produced sum `5012459533974274444`; means were 0.004904 s serial, 0.004491 s strided, and 0.002344 s contiguous (2.092x contiguous speedup). This is one machine/run and should not be generalized. Example: `make -C Task-I && Task-I/sum 10000000 9`.

The strided strategy jumps between cache lines as each worker walks the array, while contiguous workers traverse sequential memory. Contiguous ranges should therefore make better use of spatial locality and hardware prefetching; the actual outcome depends on machine, N, scheduling, and thread startup overhead. Use the output from the target Linux/Termux device for observations; no measurements are embedded here.

## Task II: SPSC ring

`Task-II/ring.c` is an array-backed queue of eight integers. Monotonically increasing atomic head/tail counters disambiguate full from empty; masking by seven maps a sequence number to a slot. Only producer writes head and only consumer writes tail. Each side loads its own counter relaxed and observes the other side with acquire. Publishing an inserted slot uses a release store to head; releasing a consumed slot uses release to tail. This ensures slot writes happen before consumer reads and consumer reads finish before producer reuses slots. The queue is safe only for exactly one producer and one consumer; it spins while full/empty and does not use queue mutexes. Adjacent atomics may share a cache line; padding is omitted for simplicity and can matter under high contention.

The executable checks empty/full, FIFO, and repeated wraparound before running actual producer and consumer threads for 100,000 elements. It prints every enqueue/dequeue as requested. Run with `make -C Task-II && Task-II/ring`.

## Task III: Android GPU forest fire

`Task-III/main.c` creates an EGL OpenGL ES context, compiles an ESSL 3.10 compute shader, and dispatches 8x8 workgroups over an MxM grid. The shader reads a prior-state SSBO and writes a separate output SSBO, checks the eight in-bounds neighbors, changes burning to nothing, and hashes cell/epoch values to make the 0.15 spread decision. The host inserts an SSBO/buffer-update memory barrier between epochs, maps each completed output buffer back to the host to detect termination, and prints each epoch for M <= 20. Cells use H=0, B=1, N=2. Seed is optionally supplied. Build with an Android NDK: `ndk-build NDK_PROJECT_PATH=Task-III APP_BUILD_SCRIPT=Task-III/Android.mk NDK_APPLICATION_MK=Task-III/Application.mk`; run the produced executable on an Android device as `forest_fire M [seed]`.

This host requests a surfaceless EGL context; devices without support report a diagnostic. A GPU, Android EGL stack, and GLES 3.1 are required. This environment is x86_64 WSL2 Linux without `ndk-build`; the C host source compiles against the installed EGL/GLES headers, but Android NDK linking and device GPU execution remain unverified.

## Verification status

On the available Linux host, both CPU programs built with `-Wall -Wextra -Wpedantic` and ran successfully. Task I sums matched at N=1,024 and N=10,000,000 over 3 and 7 trials respectively. Task II passed empty/full, wraparound, and 100,000-item concurrent FIFO checks. The Task I benchmark above is an observed WSL2 result, not a Termux or Android result. Task III passed a host C compile against installed EGL/GLES headers; Android NDK linking, shader compilation by a device driver, and GPU execution still need verification on Android.
