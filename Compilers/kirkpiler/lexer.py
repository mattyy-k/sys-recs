from dataclasses import dataclass
from .errors import CompileError

KEYWORDS = set("pin uart fn let if else while return true false int bool input output".split())
TWO = ("->", "==", "!=", "<=", ">=", "&&", "||")
SINGLE = set("{}();,. :=+-*/%<>!".replace(" ", ""))

@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int
    def __str__(self): return f"{self.kind}({self.value!r})@{self.line}:{self.column}"

class Lexer:
    def __init__(self, source):
        self.source, self.i, self.line, self.col = source, 0, 1, 1
    def peek(self, n=0):
        j = self.i+n
        return self.source[j] if j < len(self.source) else ""
    def take(self):
        c = self.peek()
        if c:
            self.i += 1
            if c == "\n": self.line, self.col = self.line+1, 1
            else: self.col += 1
        return c
    def tokens(self):
        out=[]
        while self.peek():
            c=self.peek()
            if ord(c)>127: raise CompileError(self.line,self.col,"source must contain ASCII characters only")
            if c.isspace(): self.take(); continue
            line,col=self.line,self.col
            if c=="/" and self.peek(1)=="/":
                while self.peek() and self.peek()!="\n":
                    if ord(self.peek())>127: raise CompileError(self.line,self.col,"source must contain ASCII characters only")
                    self.take()
                continue
            if c=='"':
                self.take(); value=""
                while self.peek() and self.peek()!='"':
                    ch=self.take()
                    if ch=="\n" or ord(ch)<32 or ord(ch)>126: raise CompileError(line,col,"string must contain printable ASCII on one line")
                    if ch=="\\":
                        if self.peek()!="n": raise CompileError(self.line,self.col,"only \\n is a valid string escape")
                        self.take(); value+="\n"
                    else: value+=ch
                if not self.peek(): raise CompileError(line,col,"unterminated string")
                self.take(); out.append(Token("STRING",value,line,col)); continue
            if c.isdigit():
                value=""; number=0
                while self.peek().isdigit() and ord(self.peek())<128:
                    digit=self.take(); value+=digit; number=number*10+ord(digit)-48
                    if number>0xffffffff: raise CompileError(line,col,"integer literal exceeds uint32")
                out.append(Token("NUMBER",value,line,col)); continue
            if c.isalpha() or c=="_":
                value=""
                while self.peek().isalnum() or self.peek()=="_": value+=self.take()
                if any(ord(ch)>127 for ch in value): raise CompileError(line,col,"source must contain ASCII characters only")
                if value.startswith("P") and value[1:].isdigit(): kind="PIN"
                elif value in KEYWORDS: kind=value.upper()
                else: kind="IDENT"
                out.append(Token(kind,value,line,col)); continue
            pair=c+self.peek(1)
            if pair in TWO: self.take(); self.take(); out.append(Token(pair,pair,line,col)); continue
            if c in SINGLE: self.take(); out.append(Token(c,c,line,col)); continue
            raise CompileError(line,col,f"unexpected character {c!r}")
        out.append(Token("EOF","",self.line,self.col)); return out

def lex(source): return Lexer(source).tokens()
