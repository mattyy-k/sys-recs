import argparse, json, sys
from dataclasses import fields, is_dataclass
from pathlib import Path
from .lexer import lex
from .parser import parse
from .semantic import analyze
from .codegen import generate
from .runtime import execute, RuntimeFault
from .errors import CompileError

def plain(x):
    if is_dataclass(x): return {f.name:plain(getattr(x,f.name)) for f in fields(x)}
    if isinstance(x,list): return [plain(v) for v in x]
    return x

def main(argv=None):
    p=argparse.ArgumentParser(prog="kirkpiler"); p.add_argument("source",type=Path); p.add_argument("--tokens",action="store_true"); p.add_argument("--ast",action="store_true"); p.add_argument("--ir",action="store_true"); p.add_argument("--run",action="store_true"); p.add_argument("--no-opt",action="store_true",help="disable optimization passes (none are enabled by default)")
    a=p.parse_args(argv)
    if a.source.suffix!=".kp": p.error("source file must use .kp extension")
    try:
        toks=lex(a.source.read_text(encoding="ascii"))
        if a.tokens: print("\n".join(map(str,toks)))
        tree=parse(toks)
        if a.ast: print(json.dumps(plain(tree),indent=2))
        sem=analyze(tree); module=generate(tree,sem)
        if a.ir: print(module)
        if a.run:
            for line in execute(module): print(line)
    except RuntimeFault as exc:
        for line in exc.logs: print(line)
        return 1
    except (CompileError,UnicodeError,RuntimeError) as exc:
        print(exc,file=sys.stderr); return 1
    return 0

if __name__=="__main__": raise SystemExit(main())
