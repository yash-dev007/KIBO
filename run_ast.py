import sys
import json
from graphify.extract import collect_files, extract
from pathlib import Path

path = Path('graphify-out/.graphify_incremental.json')
if not path.exists():
    print("No incremental detection file found.")
    exit(1)

detect = json.loads(path.read_text())
code_files = [Path(f) for f in detect.get('new_files', {}).get('code', [])]

if code_files:
    result = extract(code_files, cache_root=Path('.'))
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps(result, indent=2))
    print(f"AST: {len(result['nodes'])} nodes, {len(result['edges'])} edges")
else:
    Path('graphify-out/.graphify_ast.json').write_text(json.dumps({'nodes':[],'edges':[],'input_tokens':0,'output_tokens':0}))
    print("No code files - skipping AST extraction")
