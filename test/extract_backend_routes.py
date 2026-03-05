import os
import re

backend_dir = r"e:\Agentium\backend"
routes = []

# regex to match @router.get("/path") or @app.post('/path') etc.
pattern = re.compile(r'@(router|app)\.(get|post|put|delete|patch)\([\'"]([^\'"]+)[\'"]')

for root, _, files in os.walk(backend_dir):
    for file in files:
        if file.endswith(".py"):
            with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                content = f.read()
                matches = pattern.findall(content)
                for match in matches:
                    method = match[1].upper()
                    path = match[2]
                    # Attempt to resolve router prefix if needed, though most explicit defines are enough
                    # For simplicity we'll just capture what is defined.
                    routes.append(f"{method} {path} (in {os.path.relpath(os.path.join(root, file), backend_dir)})")

with open(r"e:\Agentium\test\backend_routes.txt", "w", encoding='utf-8') as f:
    for r in sorted(set(routes)):
        f.write(r + "\n")
print(f"Found {len(set(routes))} routes.")
