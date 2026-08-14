"""
surgical_editor.py — v5.9.10.D
تعديل جراحي دقيق: يعدل دالة أو كلاس فقط بدون إعادة كتابة الملف كاملاً
"""
import ast
import re


def extract_symbol(file_path: str, symbol_name: str) -> dict:
    """يستخرج دالة أو كلاس محدد مع رقم السطر"""
    with open(file_path, encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source)
    lines = source.split('\n')

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol_name:
                start = node.lineno - 1
                end = node.end_lineno
                code = '\n'.join(lines[start:end])
                return {
                    "name": symbol_name,
                    "code": code,
                    "start_line": start,
                    "end_line": end,
                    "source": source,
                }
    return {}


def clean_llm_output(code: str, symbol_name: str) -> str:
    """يزيل أي كود خارج الدالة المطلوبة من مخرجات LLM"""
    lines = code.split("\n")
    # نبحث عن بداية الدالة
    start = None
    for i, line in enumerate(lines):
        if line.strip().startswith(f"def {symbol_name}") or \
           line.strip().startswith(f"async def {symbol_name}"):
            start = i
            break
    if start is not None:
        return "\n".join(lines[start:])
    return code


def patch_symbol(original_source: str, symbol_name: str,
                 new_code: str, start_line: int, end_line: int) -> str:
    """يستبدل الدالة القديمة بالجديدة في الملف"""
    lines = original_source.split('\n')
    new_lines = new_code.split('\n')
    patched = lines[:start_line] + new_lines + lines[end_line:]
    return '\n'.join(patched)


def validate_patch(original_source: str, patched_source: str) -> dict:
    """يتحقق أن الـ patch لم يحذف دوالاً موجودة"""
    try:
        import ast
        orig_tree = ast.parse(original_source)
        patch_tree = ast.parse(patched_source)

        orig_symbols = {n.name for n in ast.walk(orig_tree)
                       if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
        patch_symbols = {n.name for n in ast.walk(patch_tree)
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}

        missing = orig_symbols - patch_symbols
        if missing:
            return {"ok": False, "missing": list(missing)}
        return {"ok": True, "missing": []}
    except SyntaxError as e:
        return {"ok": False, "error": str(e)}


def list_symbols(file_path: str) -> list:
    """يعيد قائمة بكل الدوال والكلاسات في الملف"""
    try:
        with open(file_path, encoding="utf-8") as f:
            source = f.read()
        tree = ast.parse(source)
        symbols = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append({"kind": "function", "name": node.name, "line": node.lineno})
            elif isinstance(node, ast.ClassDef):
                symbols.append({"kind": "class", "name": node.name, "line": node.lineno})
        return sorted(symbols, key=lambda x: x["line"])
    except:
        return []
