import unittest
from kirkpiler.lexer import lex
from kirkpiler.parser import parse
from kirkpiler.semantic import analyze
from kirkpiler.errors import CompileError
from kirkpiler import ast

class FrontendTests(unittest.TestCase):
    def test_tokens_and_positions(self):
        ts=lex('fn main() { let x = 1 + 2; // ok\n}')
        self.assertEqual(ts[0].line,1); self.assertEqual(ts[-2].line,2)
    def test_precedence_and_ast(self):
        p=parse(lex('fn main() { let x = 1 + 2 * 3; }'))
        expr=p.declarations[0].body[0].value
        self.assertIsInstance(expr,ast.Binary); self.assertEqual(expr.op,'+')
        self.assertEqual(expr.right.op,'*')
    def test_semantics_and_scopes(self):
        p=parse(lex('fn f(a: int) -> int { if true { let b = a; return b; } else { return 0; } } fn main() {}'))
        analyze(p)
    def test_invalid_integer_and_string(self):
        for source in ('4294967296','"unterminated'):
            with self.assertRaises(CompileError): lex(source)
    def test_missing_return(self):
        p=parse(lex('fn f() -> int { while true { return 1; } } fn main() {}'))
        with self.assertRaisesRegex(CompileError,'reach its end'): analyze(p)
    def test_pin_reuse(self):
        p=parse(lex('pin X = P0 output; uart UART0 { tx = P0; rx = P1; baud = 9600; } fn main() {}'))
        with self.assertRaisesRegex(CompileError,'already used'): analyze(p)
    def test_method_receiver_validation(self):
        p=parse(lex('pin X = P0 output; fn main() { X.read(); }'))
        with self.assertRaisesRegex(CompileError,'not valid'): analyze(p)
    def test_uart_signal_and_baud_checks(self):
        bad_pin=parse(lex('uart UART0 { tx = P2; rx = P1; baud = 9600; } fn main() {}'))
        with self.assertRaisesRegex(CompileError,'valid pins: P0, P4'): analyze(bad_pin)
        bad_baud=parse(lex('uart UART0 { tx = P0; rx = P1; baud = 1234; } fn main() {}'))
        with self.assertRaisesRegex(CompileError,'unsupported baud'): analyze(bad_baud)
    def test_comparison_chain_and_type_errors(self):
        with self.assertRaisesRegex(CompileError,'cannot be chained'): parse(lex('fn main() { let x = 1 < 2 < 3; }'))
        p=parse(lex('fn main() { let x = 1 + true; }'))
        with self.assertRaises(CompileError): analyze(p)
    def test_ascii_and_escape_rules(self):
        with self.assertRaisesRegex(CompileError,'ASCII'): lex('fn main() { let é = 0; }')
        with self.assertRaisesRegex(CompileError,'escape'): lex(r'"bad\t"')

if __name__=='__main__': unittest.main()
