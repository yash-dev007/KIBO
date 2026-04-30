import json
from pathlib import Path

path = Path('graphify-out/.graphify_incremental.json')
if not path.exists():
    print("No incremental detection file found.")
    exit(1)

result = json.loads(path.read_text())
new_total = result.get("new_total", 0)
deleted_files = result.get("deleted_files", [])
new_files = result.get("new_files", {})

code_exts = {'.py', '.ts', '.js', '.go', '.rs', '.java', '.cpp', '.c', '.rb', '.swift', '.kt', '.cs', '.scala', '.php', '.cc', '.cxx', '.hpp', '.h', '.kts', '.lua', '.toc'}
all_new = [f for files in new_files.values() for f in files]
code_only = all(Path(f).suffix.lower() in code_exts for f in all_new)

print(f"new_total: {new_total}")
print(f"deleted_count: {len(deleted_files)}")
print(f"code_only: {code_only}")
