# KirkPiler

KirkPiler is a small ASCII-only language for programming the KIRK-8 microcontroller. This project implements a handwritten lexer and recursive-descent parser, positioned AST, semantic and hardware checks, LLVM IR generation with `llvmlite`, and a Python `ctypes` runtime for JIT execution.

## Structure and design

- `kirkpiler/lexer.py`, `ast.py`, `parser.py`: tokens, source positions, and syntax tree construction.
- `semantic.py`: scopes, types, return analysis, pin/UART validation, and device method checks.
- `codegen.py`: LLVM functions, stack slots, structured control flow, short-circuit booleans, and guarded unsigned division/remainder.
- `runtime.py`: runtime callbacks, deterministic pin reads, UART state, and execution logs.
- `cli.py`: token, AST, IR, and run commands.
- `tests/`: lexer, parser, semantic, and hardware checks.

The front end and backend are separate so semantic failures are reported before LLVM emission. Locals use stack slots for a simple mutable-variable model. Runtime functions are registered as `ctypes` callbacks for MCJIT. Optional CFG UART analysis, SSA, and optimization passes are not implemented.

## Install and use

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
python3 -m unittest discover -s tests
```

Save source as `.kp`, then run:

```sh
.venv/bin/kirkpiler examples/blink.kp --tokens --ast --ir --run
```

Flags can be used individually. `--no-opt` is accepted for CLI compatibility; no optimization passes are currently enabled.

## Example

```kp
pin LED = P2 output;
fn main() {
    LED.high();
    wait(10);
    LED.low();
}
```

The IR contains calls such as `call void @kp_pin_write(i32 2, i32 1)`. Running the program logs:

```text
pin_mode 2 1
pin_write 2 1
wait 10
pin_write 2 0
```
