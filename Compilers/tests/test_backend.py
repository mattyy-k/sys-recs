import unittest

try:
    from kirkpiler.codegen import generate
    from kirkpiler.runtime import execute
except ImportError as exc:
    if exc.name != "llvmlite": raise
    generate = execute = None

@unittest.skipIf(generate is None, "llvmlite is required for backend tests")
class BackendTests(unittest.TestCase):
    def compile(self,source):
        from kirkpiler.lexer import lex
        from kirkpiler.parser import parse
        from kirkpiler.semantic import analyze
        p=parse(lex(source)); sem=analyze(p); return generate(p,sem)
    def test_ir_has_short_circuit_and_division_guard(self):
        ir=str(self.compile('fn f(a: bool, x: int, y: int) -> int { if a && (x > 0) { return x / y; } else { return 0; } } fn main() {}'))
        self.assertIn('logic.rhs',ir); self.assertRegex(ir,r'phi\s+i1'); self.assertIn('udiv',ir); self.assertIn('kp_init',ir)
    def test_or_phi_uses_short_path_and_rhs_predecessor(self):
        module=self.compile('fn either(a: bool, b: bool) -> bool { return a || b; } fn main() {}')
        from llvmlite import binding
        verified=binding.parse_assembly(str(module)); verified.verify()
        body=str(module).split('define i1 @"f_either"',1)[1].split('\ndefine void',1)[0]
        self.assertRegex(body,r'phi\s+i1\s+\[1, %"entry"\], \[%".*", %"logic.rhs"\]')
    def test_and_or_skip_device_reads(self):
        logs=execute(self.compile('pin BTN = P3 input; fn main() { let a = false && (BTN.read() == 1); let b = true || (BTN.read() == 1); }'))
        self.assertEqual(logs,['pin_mode 3 0'])
    def test_runtime_order_and_uart_print(self):
        source='uart UART0 { tx = P0; rx = P1; baud = 9600; } pin LED = P2 output; fn main() { UART0.start(); LED.high(); UART0.print("A"); }'
        logs=execute(self.compile(source))
        self.assertEqual(logs,['uart_init 0 0 1 9600','pin_mode 2 1','uart_start 0','pin_write 2 1','uart_putc 0 65'])
    def test_uart_print_fault_reports_and_stops_runtime(self):
        from kirkpiler.runtime import RuntimeFault
        module=self.compile('uart UART0 { tx = P0; rx = P1; baud = 9600; } pin LED = P2 output; fn main() { UART0.print(1); LED.high(); }')
        with self.assertRaises(RuntimeFault) as raised: execute(module)
        self.assertEqual(raised.exception.logs,['uart_init 0 0 1 9600','pin_mode 2 1','FAULT uart 0 not started'])

if __name__=='__main__': unittest.main()
