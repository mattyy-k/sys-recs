class CompileError(Exception):
    def __init__(self, line: int, column: int, message: str):
        self.line, self.column, self.message = line, column, message
        super().__init__(f"{line}:{column}: {message}")
