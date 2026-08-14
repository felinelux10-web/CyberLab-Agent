with open("lab_v4_dev/awareness/project_reader.py", "r") as f:
    code = f.read()

old = '            "entry_points": ["run.py"],'
new = '''            "entry_points": _find_entry_points(base_dir),'''

# نضيف الدالة قبل generate_outputs
func = '''
def _find_entry_points(base_dir: str) -> list:
    """يبحث عن نقاط الدخول الفعلية في المشروع"""
    import os
    candidates = ["main.py", "run.py", "app.py", "server.py", "cli.py", "__main__.py"]
    found = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d not in ["__pycache__", ".git", "tests", "test"]]
        for f in files:
            if f in candidates:
                rel = os.path.relpath(os.path.join(root, f), base_dir)
                found.append(rel)
    return found or ["unknown"]

'''

# نضيف الدالة قبل generate_outputs
old2 = 'def _find_entry_points'
if old2 not in code:
    # أضف الدالة قبل generate_outputs
    code = code.replace('    def generate_outputs(self):', func + '    def generate_outputs(self):')

if old in code:
    code = code.replace(old, new)
    with open("lab_v4_dev/awareness/project_reader.py", "w") as f:
        f.write(code)
    print("OK")
else:
    print("ERROR - line not found")
    for i, l in enumerate(code.split('\n')[70:76], 71):
        print(f"{i}: {l}")
