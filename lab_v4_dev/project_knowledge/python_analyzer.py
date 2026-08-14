import ast

from .base_analyzer import BaseAnalyzer, AnalysisResult

class PythonAnalyzer(BaseAnalyzer):
    def supports(self, file_path: str) -> bool:
        return file_path.endswith(".py")

    def analyze(self, file_path: str) -> AnalysisResult:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        ast.parse(source, filename=file_path)

        return AnalysisResult(
            file_path=file_path,
            language="python",
            symbols=self.collect_symbols(file_path),
            dependencies=self.collect_dependencies(file_path),
            errors=[],
        )

    def collect_symbols(self, file_path: str) -> list:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=file_path)

        symbols = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "line": node.lineno,
                })

            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({
                    "name": node.name,
                    "kind": "function",
                    "line": node.lineno,
                })

        return symbols

    def collect_dependencies(self, file_path: str) -> list:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=file_path)

        dependencies = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    dependencies.append({
                        "name": item.name,
                        "kind": "import",
                        "line": node.lineno,
                    })

            elif isinstance(node, ast.ImportFrom):
                dependencies.append({
                    "name": node.module or "",
                    "kind": "from_import",
                    "line": node.lineno,
                })

        return dependencies

    def metadata(self) -> dict:
        return {"name": "python", "extensions": [".py"]}
