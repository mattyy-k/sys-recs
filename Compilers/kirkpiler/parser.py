from . import ast
from .errors import CompileError

class Parser:
    def __init__(self,tokens): self.t=tokens; self.i=0
    def cur(self): return self.t[self.i]
    def at(self,k): return self.cur().kind==k
    def take(self): x=self.cur(); self.i+=1; return x
    def expect(self,k,msg=None):
        if not self.at(k):
            x=self.cur(); raise CompileError(x.line,x.column,msg or f"expected {k}, found {x.value or 'end of file'}")
        return self.take()
    def node(self,cls,*args,tok=None): tok=tok or self.cur(); return cls(tok.line,tok.column,*args)
    def parse(self):
        ds=[]
        while not self.at("EOF"):
            if self.at("PIN"): ds.append(self.pin_decl())
            elif self.at("UART"): ds.append(self.uart_decl())
            elif self.at("FN"): ds.append(self.function())
            else: self.expect("FN","expected pin, uart, or function declaration")
        return self.node(ast.Program,ds,tok=self.t[0])
    def pin_decl(self):
        start=self.take(); name=self.expect("IDENT","expected pin name"); self.expect("="); pin=self.expect("PIN","expected physical pin P0-P7")
        mode=self.take()
        if mode.kind not in ("INPUT","OUTPUT"): raise CompileError(mode.line,mode.column,"expected input or output")
        self.expect(";","expected ';' after pin declaration")
        return self.node(ast.PinDecl,name.value,pin.value,mode.value,tok=start)
    def uart_decl(self):
        start=self.take(); name=self.expect("IDENT","expected UART name"); self.expect("{"); props={}
        while not self.at("}"):
            key=self.expect("IDENT","expected UART property")
            if key.value in props: raise CompileError(key.line,key.column,f"duplicate UART property '{key.value}'")
            self.expect("="); v=self.take()
            if key.value in ("tx","rx") and v.kind!="PIN": raise CompileError(v.line,v.column,"expected pin token")
            if key.value=="baud" and v.kind!="NUMBER": raise CompileError(v.line,v.column,"expected baud rate")
            if key.value not in ("tx","rx","baud"): raise CompileError(key.line,key.column,f"unknown UART property '{key.value}'")
            props[key.value]=v.value; self.expect(";","expected ';' after UART property")
        self.take()
        for prop in ("tx","rx","baud"):
            if prop not in props: raise CompileError(start.line,start.column,f"missing UART property '{prop}'")
        return self.node(ast.UARTDecl,name.value,props['tx'],props['rx'],int(props['baud']),tok=start)
    def function(self):
        start=self.take(); name=self.expect("IDENT","expected function name"); self.expect("("); ps=[]
        if not self.at(")"):
            while True:
                p=self.expect("IDENT","expected parameter name"); self.expect(":"); typ=self.take()
                if typ.kind not in ("INT","BOOL"): raise CompileError(typ.line,typ.column,"expected int or bool")
                ps.append(self.node(ast.Param,p.value,typ.value,tok=p))
                if not self.at(","): break
                self.take()
        self.expect(")"); ret=None
        if self.at("->"):
            self.take(); typ=self.take()
            if typ.kind not in ("INT","BOOL"): raise CompileError(typ.line,typ.column,"expected int or bool return type")
            ret=typ.value
        b=self.block(); return self.node(ast.Function,name.value,ps,ret,b.statements,tok=start)
    def block(self):
        start=self.expect("{"); ss=[]
        while not self.at("}"):
            if self.at("EOF"): self.expect("}","unclosed block")
            ss.append(self.statement())
        self.take(); return self.node(ast.Block,ss,tok=start)
    def statement(self):
        x=self.cur()
        if self.at("LET"):
            self.take(); n=self.expect("IDENT","expected variable name"); self.expect("="); v=self.expression(); self.expect(";","expected ';' after declaration"); return self.node(ast.Let,n.value,v,tok=x)
        if self.at("IF"):
            self.take(); c=self.expression(); b=self.block(); other=self.block() if self.at("ELSE") and (self.take() is not None) else None
            return self.node(ast.If,c,b,other,tok=x)
        if self.at("WHILE"):
            self.take(); c=self.expression(); b=self.block(); return self.node(ast.While,c,b,tok=x)
        if self.at("RETURN"):
            self.take(); v=None if self.at(";") else self.expression(); self.expect(";","expected ';' after return"); return self.node(ast.Return,v,tok=x)
        if self.at("IDENT") and self.t[self.i+1].kind=="=":
            n=self.take(); self.take(); v=self.expression(); self.expect(";","expected ';' after assignment"); return self.node(ast.Assign,n.value,v,tok=x)
        e=self.expression(); self.expect(";","expected ';' after expression"); return self.node(ast.ExprStmt,e,tok=x)
    def expression(self): return self.binary(0)
    levels=[["||"],["&&"],["==","!=","<","<=",">",">="],["+","-"],["*","/","%"]]
    def binary(self,level):
        if level==5:
            if self.at("!"):
                x=self.take(); return self.node(ast.Unary,"!",self.binary(5),tok=x)
            return self.primary()
        left=self.binary(level+1)
        while self.cur().kind in self.levels[level]:
            op=self.take(); right=self.binary(level+1); left=self.node(ast.Binary,op.kind,left,right,tok=op)
            if level==2 and self.cur().kind in self.levels[level]:
                q=self.cur(); raise CompileError(q.line,q.column,"comparisons cannot be chained")
        return left
    def primary(self):
        x=self.cur()
        if x.kind=="NUMBER": self.take(); return self.node(ast.Literal,int(x.value),"int",tok=x)
        if x.kind=="STRING": self.take(); return self.node(ast.Literal,x.value,"string",tok=x)
        if x.kind in ("TRUE","FALSE"): self.take(); return self.node(ast.Literal,x.kind=="TRUE","bool",tok=x)
        if x.kind=="(": self.take(); e=self.expression(); self.expect(")","expected ')'"); return e
        if x.kind in ("IDENT","UART"):
            self.take(); name=x.value
            if self.at("."):
                self.take(); m=self.expect("IDENT","expected method name"); args=self.arguments(); return self.node(ast.Method,name,m.value,args,tok=x)
            if self.at("("): return self.node(ast.Call,name,self.arguments(),tok=x)
            if x.kind!="IDENT": raise CompileError(x.line,x.column,"UART receiver requires a method")
            return self.node(ast.Name,name,tok=x)
        if x.kind=="WAIT":
            self.take(); return self.node(ast.Call,"wait",self.arguments(),tok=x)
        raise CompileError(x.line,x.column,f"expected expression, found {x.value or 'end of file'}")
    def arguments(self):
        self.expect("("); args=[]
        if not self.at(")"):
            while True:
                args.append(self.expression())
                if not self.at(","): break
                self.take()
        self.expect(")","expected ')'"); return args

def parse(tokens): return Parser(tokens).parse()
