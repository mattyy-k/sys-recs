from llvmlite import ir
from . import ast

I32=ir.IntType(32); I1=ir.IntType(1); VOID=ir.VoidType()
RUNTIME={"kp_uart_init":([I32]*4,VOID),"kp_pin_mode":([I32]*2,VOID),"kp_uart_start":([I32],VOID),"kp_uart_stop":([I32],VOID),"kp_uart_putc":([I32]*2,VOID),"kp_uart_print_int":([I32]*2,VOID),"kp_pin_write":([I32]*2,VOID),"kp_pin_toggle":([I32],VOID),"kp_pin_read":([I32],I32),"kp_wait":([I32],VOID)}

class Generator:
    def __init__(self,program,analysis):
        self.p,self.sem=program,analysis; self.m=ir.Module(name="kirkpiler"); self.funcs={}; self.vars={}; self.loop_id=0
        for name,(args,ret) in RUNTIME.items(): self.m.globals[name]=ir.Function(self.m,ir.FunctionType(ret,args),name=name)
        for f in analysis.funcs.values():
            ret=I32 if f.return_type=="int" else I1 if f.return_type=="bool" else VOID
            self.funcs[f.name]=ir.Function(self.m,ir.FunctionType(ret,[I32 if x.type=="int" else I1 for x in f.params]),"f_"+f.name)
        self.init=ir.Function(self.m,ir.FunctionType(VOID,[]),"kp_init")
        self.strings=[]
    def run(self):
        self.declarations();
        for f in self.sem.funcs.values(): self.function(f)
        return self.m
    @staticmethod
    def runtime_arg(value):
        return ir.Constant(I32,value) if isinstance(value,int) else value
    def callrt(self,name,args):
        return self.b.call(self.m.globals[name],[self.runtime_arg(value) for value in args])
    def declarations(self):
        b=ir.IRBuilder(self.init.append_basic_block("entry"))
        self.b=b
        for d in self.p.declarations:
            if isinstance(d,ast.UARTDecl):
                args=[int(d.name[-1]),int(d.tx[1:]),int(d.rx[1:]),d.baud]
                b.call(self.m.globals["kp_uart_init"],[self.runtime_arg(value) for value in args])
            elif isinstance(d,ast.PinDecl):
                args=[int(d.pin[1:]),int(d.mode=="output")]
                b.call(self.m.globals["kp_pin_mode"],[self.runtime_arg(value) for value in args])
        b.ret_void()
    def function(self,f):
        fn=self.funcs[f.name]; self.b=ir.IRBuilder(fn.append_basic_block("entry")); self.vars=[{}]
        for a,p in zip(fn.args,f.params):
            a.name=p.name; ptr=self.b.alloca(a.type,name=p.name+".addr"); self.b.store(a,ptr); self.vars[-1][p.name]=(ptr,a.type)
        for s in f.body:
            if self.b.block.is_terminated: break
            self.statement(s)
        if not self.b.block.is_terminated: self.b.ret_void() if fn.function_type.return_type==VOID else self.b.unreachable()
    def statement(self,s):
        if isinstance(s,ast.Let):
            v=self.expr(s.value); ptr=self.b.alloca(v.type,name=s.name); self.b.store(v,ptr); self.vars[-1][s.name]=(ptr,v.type)
        elif isinstance(s,ast.Assign): self.b.store(self.expr(s.value),self.lookup(s.name)[0])
        elif isinstance(s,ast.ExprStmt): self.expr(s.value)
        elif isinstance(s,ast.Return): self.b.ret_void() if s.value is None else self.b.ret(self.expr(s.value))
        elif isinstance(s,ast.If):
            cond=self.expr(s.condition); fn=self.b.function; tb=fn.append_basic_block("if.then"); eb=fn.append_basic_block("if.else") if s.otherwise else None; end=fn.append_basic_block("if.end")
            self.b.cbranch(cond,tb,eb or end); self.b.position_at_end(tb); self.block(s.then.statements)
            if not self.b.block.is_terminated: self.b.branch(end)
            if eb:
                self.b.position_at_end(eb); self.block(s.otherwise.statements)
                if not self.b.block.is_terminated: self.b.branch(end)
            self.b.position_at_end(end)
        elif isinstance(s,ast.While):
            fn=self.b.function; self.loop_id+=1; i=self.loop_id
            cond=fn.append_basic_block(f"while.cond.{i}"); body=fn.append_basic_block(f"while.body.{i}"); end=fn.append_basic_block(f"while.end.{i}")
            self.b.branch(cond); self.b.position_at_end(cond); self.b.cbranch(self.expr(s.condition),body,end); self.b.position_at_end(body); self.block(s.body.statements)
            if not self.b.block.is_terminated: self.b.branch(cond)
            self.b.position_at_end(end)
    def block(self,ss):
        self.vars.append({})
        for s in ss:
            if self.b.block.is_terminated: break
            self.statement(s)
        self.vars.pop()
    def lookup(self,n):
        for x in reversed(self.vars):
            if n in x: return x[n]
        raise KeyError(n)
    def expr(self,e):
        b=self.b
        if isinstance(e,ast.Literal):
            if e.type=="string": return self.string_ptr(e.value)
            return ir.Constant(I1 if e.type=="bool" else I32,int(e.value))
        if isinstance(e,ast.Name):
            p,t=self.lookup(e.value); return b.load(p)
        if isinstance(e,ast.Unary): return b.not_(self.expr(e.operand))
        if isinstance(e,ast.Binary):
            if e.op in ("&&","||"): return self.short_circuit(e)
            a=self.expr(e.left); c=self.expr(e.right)
            if e.op in ("+","-","*"): return {"+":b.add,"-":b.sub,"*":b.mul}[e.op](a,c)
            if e.op in ("/","%"):
                zero=b.icmp_unsigned("==",c,ir.Constant(I32,0)); safe=b.select(zero,ir.Constant(I32,1),c); val=(b.udiv(a,safe) if e.op=="/" else b.urem(a,safe)); return b.select(zero,ir.Constant(I32,0),val)
            return b.icmp_unsigned({"==":"==","!=":"!=","<":"<","<=":"<=",">":">",">=":">="}[e.op],a,c)
        if isinstance(e,ast.Call):
            vals=[self.expr(x) for x in e.args]
            if e.name=="wait": return self.callrt("kp_wait",vals)
            fn=self.funcs[e.name]; return b.call(fn,vals)
        if isinstance(e,ast.Method):
            if e.receiver in self.sem.pins:
                pin,mode=self.sem.pins[e.receiver]; n=int(pin[1:])
                if e.method=="read": return self.callrt("kp_pin_read",[n])
                if e.method in ("high","low"): return self.callrt("kp_pin_write",[n,int(e.method=="high")])
                return self.callrt("kp_pin_toggle",[n])
            uid=int(e.receiver[-1])
            if e.method=="start": return self.callrt("kp_uart_start",[uid])
            if e.method=="stop": return self.callrt("kp_uart_stop",[uid])
            arg=e.args[0]
            if isinstance(arg,ast.Literal) and arg.type=="string":
                for c in arg.value: self.callrt("kp_uart_putc",[uid,ord(c)])
            else: self.callrt("kp_uart_print_int",[uid,self.expr(arg)])
            return None
    def short_circuit(self,e):
        b=self.b; fn=b.function; left=self.expr(e.left); start=b.block
        rhs=fn.append_basic_block("logic.rhs"); end=fn.append_basic_block("logic.end")
        if e.op=="&&": b.cbranch(left,rhs,end); short=ir.Constant(I1,0)
        else: b.cbranch(left,end,rhs); short=ir.Constant(I1,1)
        b.position_at_end(rhs); rv=self.expr(e.right); rhs_end=b.block
        if not rhs_end.is_terminated: b.branch(end)
        b.position_at_end(end)
        result=b.phi(I1)
        result.add_incoming(short,start)
        result.add_incoming(rv,rhs_end)
        return result
    def string_ptr(self,s):
        raw=s.encode()+b"\0"; data=bytearray(raw); arr=ir.ArrayType(ir.IntType(8),len(data)); glob=ir.GlobalVariable(self.m,arr,name=f".str.{len(self.strings)}"); glob.global_constant=True; glob.initializer=ir.Constant(arr,data); self.strings.append(glob)
        return self.b.gep(glob,[ir.Constant(I32,0),ir.Constant(I32,0)],inbounds=True)

def generate(program,analysis): return Generator(program,analysis).run()
