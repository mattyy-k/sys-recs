from . import ast
from .errors import CompileError

ALLOWED={"UART0":{"tx":{"P0","P4"},"rx":{"P1","P5"}},"UART1":{"tx":{"P2","P6"},"rx":{"P3","P7"}}}
BAUD={9600,19200,57600,115200}

def fail(n,msg): raise CompileError(n.line,n.column,msg)

class Analyzer:
    def __init__(self,p): self.p=p; self.pins={}; self.uarts={}; self.funcs={}
    def analyze(self):
        mains=[]
        for d in self.p.declarations:
            if isinstance(d,ast.Function):
                if d.name in self.funcs: fail(d,f"name '{d.name}' is already declared")
                self.funcs[d.name]=d
                if d.name=="main": mains.append(d)
        if len(mains)!=1 or mains[0].params or mains[0].return_type is not None: 
            n=self.p
            fail(n,"program must define exactly one fn main() with no parameters or return type")
        occupied={}
        for d in self.p.declarations:
            if isinstance(d,ast.PinDecl):
                if d.name in self.pins or d.name in self.uarts: fail(d,f"name '{d.name}' is already declared")
                if d.name in self.funcs: fail(d,f"name '{d.name}' is already declared")
                self.check_pin(d.pin,d); self.use_pin(d.pin,d.name,d,occupied)
                self.pins[d.name]=(d.pin,d.mode)
            elif isinstance(d,ast.UARTDecl):
                if d.name not in ALLOWED: fail(d,f"unknown UART '{d.name}'")
                if d.name in self.uarts or d.name in self.pins: fail(d,f"name '{d.name}' is already declared")
                if d.name in self.funcs: fail(d,f"name '{d.name}' is already declared")
                for sig,pin in (("tx",d.tx),("rx",d.rx)):
                    self.check_pin(pin,d)
                    allowed=ALLOWED[d.name][sig]
                    if pin not in allowed: fail(d,f"{pin} cannot be used as {d.name}.{sig} (valid pins: {', '.join(sorted(allowed))})")
                    self.use_pin(pin,f"{d.name}.{sig}",d,occupied)
                if d.baud not in BAUD: fail(d,f"unsupported baud rate {d.baud}")
                self.uarts[d.name]=d
        for f in self.funcs.values(): self.check_function(f)
        return self
    def check_pin(self,p,n):
        try: num=int(p[1:])
        except: num=-1
        if num<0 or num>7: fail(n,f"unknown pin '{p}'")
    def use_pin(self,p,owner,n,occupied):
        if p in occupied: fail(n,f"pin {p} is already used by {occupied[p]}")
        occupied[p]=owner
    def check_function(self,f):
        self.return_type=f.return_type; scopes=[{}]
        for p in f.params:
            if p.name in scopes[-1]: fail(p,f"name '{p.name}' is already declared")
            scopes[-1][p.name]=p.type
        returns=self.block(f.body,scopes)
        if f.return_type and not returns: fail(f,f"function '{f.name}' can reach its end without returning")
    def block(self,stmts,scopes):
        scopes.append({}); always=False
        for s in stmts:
            r=self.stmt(s,scopes)
            if not always and r: always=True
        scopes.pop(); return always
    def lookup(self,n,scopes):
        for scope in reversed(scopes):
            if n in scope: return scope[n]
        return None
    def expect(self,n,got,want):
        if got!=want: fail(n,f"expected {want}, found {got}")
    def stmt(self,s,scopes):
        if isinstance(s,ast.Let):
            typ=self.expr(s.value,scopes)
            if typ=="string" or typ=="void": fail(s,"initializer must have type int or bool")
            if s.name in scopes[-1] or self.lookup(s.name,scopes[:-1]) is not None: fail(s,f"name '{s.name}' is already visible")
            scopes[-1][s.name]=typ
        elif isinstance(s,ast.Assign):
            typ=self.lookup(s.name,scopes)
            if typ is None: fail(s,f"undeclared name '{s.name}'")
            self.expect(s,self.expr(s.value,scopes),typ)
        elif isinstance(s,ast.If):
            self.expect(s,self.expr(s.condition,scopes),"bool")
            a=self.block(s.then.statements,scopes); b=self.block(s.otherwise.statements,scopes) if s.otherwise else False
            return a and b
        elif isinstance(s,ast.While):
            self.expect(s,self.expr(s.condition,scopes),"bool"); self.block(s.body.statements,scopes)
        elif isinstance(s,ast.Return):
            if self.return_type is None:
                if s.value is not None: fail(s,"return value in function with no return type")
            elif s.value is None: fail(s,"missing return value")
            else: self.expect(s,self.expr(s.value,scopes),self.return_type)
            return True
        elif isinstance(s,ast.ExprStmt):
            if not isinstance(s.value,(ast.Call,ast.Method)): fail(s,"only calls may be used as expression statements")
            self.expr(s.value,scopes)
        return False
    def expr(self,e,scopes):
        if isinstance(e,ast.Literal): return e.type
        if isinstance(e,ast.Name):
            typ=self.lookup(e.value,scopes)
            if typ is None: fail(e,f"undeclared name '{e.value}'")
            return typ
        if isinstance(e,ast.Unary):
            self.expect(e,self.expr(e.operand,scopes),"bool"); return "bool"
        if isinstance(e,ast.Binary):
            a=self.expr(e.left,scopes); b=self.expr(e.right,scopes)
            if a=="string" or b=="string" or a=="void" or b=="void": fail(e,"operator operands must be int or bool")
            if e.op in ("+","-","*","/","%"):
                self.expect(e,a,"int"); self.expect(e,b,"int"); return "int"
            if e.op in ("&&","||"):
                self.expect(e,a,"bool"); self.expect(e,b,"bool"); return "bool"
            self.expect(e,a,b)
            if e.op in ("<","<=",">",">="): self.expect(e,a,"int")
            return "bool"
        if isinstance(e,ast.Call):
            if e.name=="wait":
                if len(e.args)!=1: fail(e,"wait expects 1 argument")
                self.expect(e,self.expr(e.args[0],scopes),"int"); return "void"
            f=self.funcs.get(e.name)
            if f is None: fail(e,f"undeclared function '{e.name}'")
            if len(e.args)!=len(f.params): fail(e,f"function '{e.name}' expects {len(f.params)} arguments, got {len(e.args)}")
            for arg,p in zip(e.args,f.params): self.expect(arg,self.expr(arg,scopes),p.type)
            return f.return_type or "void"
        if isinstance(e,ast.Method):
            if e.receiver in self.pins:
                pin,mode=self.pins[e.receiver]
                methods={"input":{"read"},"output":{"high","low","toggle"}}[mode]
                if e.method not in methods: fail(e,f"{e.method}() is not valid on {mode} pin {e.receiver}")
                if e.args: fail(e,f"{e.method}() expects no arguments")
                return "int" if mode=="input" else "void"
            if e.receiver in self.uarts:
                if e.method not in ("start","stop","print"): fail(e,f"{e.method}() is not valid on UART {e.receiver}")
                if e.method in ("start","stop") and e.args: fail(e,f"{e.method}() expects no arguments")
                if e.method=="print":
                    if len(e.args)!=1: fail(e,"print() expects 1 argument")
                    t=self.expr(e.args[0],scopes)
                    if t not in ("int","string") or (t=="string" and not isinstance(e.args[0],ast.Literal)): fail(e,"print() expects int or a string literal")
                return "void"
            fail(e,f"undeclared device '{e.receiver}'")
        fail(e,"invalid expression")

def analyze(program): return Analyzer(program).analyze()
