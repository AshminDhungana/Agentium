import os
import re

frontend_dir = r"e:\Agentium\frontend\src"
routes = []

# Matches api.get('/path'), axios.post("/path"), fetch(`/path`), etc.
# Also matches strings like "/api/v1/something"
pattern = re.compile(r'(?:api|axios|fetch)\.?(?:get|post|put|delete|patch)?\s*\(\s*[\'"`](/?api/[^?\'"`$]+|/[^?\'"`$]+)[\'"`]')
# Let's use a simpler pattern to just find all strings that look like API paths and the HTTP method next to it if possible.
# Actually, let's just find things that look like URL paths starting with /api/ or being called by api.xxx.

# Matches api.get, axios.post, etc. with optional TypeScript generics <...>, and string literal quotes
pattern_method_path = re.compile(r'(?:api|axios)\.(get|post|put|delete|patch)[^(\n]*\(\s*[\'"`](/?api/[^\'"`]+|/[^\'"`]+)[\'"`]')

for root, _, files in os.walk(frontend_dir):
    for file in files:
        if file.endswith((".ts", ".tsx", ".js", ".jsx")):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                matches = pattern_method_path.findall(content)
                for match in matches:
                    method = match[0].upper()
                    path = match[1]
                    # normalize path
                    if not path.startswith('/'):
                        path = '/' + path
                    if not path.startswith('/api/'):
                        pass # sometimes they just call `/users` if baseURL has `/api`
                        
                    routes.append(f"{method} {path} (in {os.path.relpath(os.path.join(root, file), frontend_dir)})")

with open(r"e:\Agentium\test\frontend_routes.txt", "w", encoding='utf-8') as f:
    for r in sorted(set(routes)):
        f.write(r + "\n")
print(f"Found {len(set(routes))} frontend API calls.")
