import ctypes
from llvmlite import binding

class RuntimeFault(RuntimeError):
    def __init__(self,message,logs): self.logs=logs; super().__init__(message)

class Runtime:
    def __init__(self): self.logs=[]; self.reads={}; self.started=set(); self.fault=None
    def log(self,name,*args): self.logs.append(f"{name} {' '.join(str(int(x)) for x in args)}".rstrip())
    def active(self): return self.fault is None
    def callbacks(self):
        C=ctypes.CFUNCTYPE
        def wrap(name,n,ret=None):
            def inner(fn): return C(ret or None,*([ctypes.c_int32]*n))(fn)
            return inner
        @wrap("",4)
        def uart_init(u,tx,rx,baud):
            if self.active(): self.log("uart_init",u,tx,rx,baud)
        @wrap("",2)
        def pin_mode(p,m):
            if self.active(): self.log("pin_mode",p,m)
        @wrap("",1)
        def uart_start(u):
            if self.active(): self.started.add(u); self.log("uart_start",u)
        @wrap("",1)
        def uart_stop(u):
            if self.active(): self.started.discard(u); self.log("uart_stop",u)
        @wrap("",2)
        def uart_putc(u,ch):
            if self.active():
                self.uart_check(u)
                if self.active(): self.log("uart_putc",u,ch)
        @wrap("",2)
        def uart_print_int(u,v):
            if self.active():
                self.uart_check(u)
                if self.active(): self.log("uart_print_int",u,v)
        @wrap("",2)
        def pin_write(p,l):
            if self.active(): self.log("pin_write",p,l)
        @wrap("",1)
        def pin_toggle(p):
            if self.active(): self.log("pin_toggle",p)
        @wrap("",1,ctypes.c_int32)
        def pin_read(p):
            if not self.active(): return 0
            n=self.reads.get(p,0); self.reads[p]=n+1; v=n%2; self.logs.append(f"pin_read {p} -> {v}"); return v
        @wrap("",1)
        def wait(ms):
            if self.active(): self.log("wait",ms)
        funcs={"kp_uart_init":uart_init,"kp_pin_mode":pin_mode,"kp_uart_start":uart_start,"kp_uart_stop":uart_stop,"kp_uart_putc":uart_putc,"kp_uart_print_int":uart_print_int,"kp_pin_write":pin_write,"kp_pin_toggle":pin_toggle,"kp_pin_read":pin_read,"kp_wait":wait}
        for name,fn in funcs.items(): binding.add_symbol(name,ctypes.cast(fn,ctypes.c_void_p).value)
        self._keepalive=list(funcs.values())
    def uart_check(self,u):
        if u not in self.started:
            self.fault=f"FAULT uart {u} not started"
            self.logs.append(self.fault)

def execute(module):
    binding.initialize_native_target(); binding.initialize_native_asmprinter()
    rt=Runtime(); rt.callbacks()
    mod=binding.parse_assembly(str(module)); mod.verify()
    target=binding.Target.from_default_triple(); machine=target.create_target_machine()
    engine=binding.create_mcjit_compiler(binding.parse_assembly(""),machine); engine.add_module(mod); engine.finalize_object(); engine.run_static_constructors()
    engine.get_function_address("kp_init") and ctypes.CFUNCTYPE(None)(engine.get_function_address("kp_init"))()
    ctypes.CFUNCTYPE(None)(engine.get_function_address("f_main"))()
    if rt.fault: raise RuntimeFault(rt.fault,rt.logs)
    return rt.logs
