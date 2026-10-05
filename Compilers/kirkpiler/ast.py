from dataclasses import dataclass, field

@dataclass
class Node: line:int; column:int
@dataclass
class Program(Node): declarations:list
@dataclass
class PinDecl(Node): name:str; pin:str; mode:str
@dataclass
class UARTDecl(Node): name:str; tx:str; rx:str; baud:int
@dataclass
class Param(Node): name:str; type:str
@dataclass
class Function(Node): name:str; params:list; return_type:str|None; body:list
@dataclass
class Block(Node): statements:list
@dataclass
class Let(Node): name:str; value:Node
@dataclass
class Assign(Node): name:str; value:Node
@dataclass
class If(Node): condition:Node; then:Block; otherwise:Block|None
@dataclass
class While(Node): condition:Node; body:Block
@dataclass
class Return(Node): value:Node|None
@dataclass
class ExprStmt(Node): value:Node
@dataclass
class Literal(Node): value:object; type:str
@dataclass
class Name(Node): value:str
@dataclass
class Unary(Node): op:str; operand:Node
@dataclass
class Binary(Node): op:str; left:Node; right:Node
@dataclass
class Call(Node): name:str; args:list
@dataclass
class Method(Node): receiver:str; method:str; args:list
