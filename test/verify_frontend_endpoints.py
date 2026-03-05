import os
import re

frontend_dir = r"e:\Agentium\frontend\src"
filtered_file = r"e:\Agentium\test\filtered_endpoints.md"

# 1. Read entire frontend codebase into memory
frontend_texts = []
for root, _, files in os.walk(frontend_dir):
    for f in files:
        if f.endswith((".ts", ".tsx", ".js", ".jsx")):
            with open(os.path.join(root, f), "r", encoding="utf-8") as file:
                frontend_texts.append((os.path.join(root, f), file.read()))

print(f"Loaded {len(frontend_texts)} frontend files.")

# 2. Parse missing endpoints
with open(filtered_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

missing_endpoints = [] # List of (line_idx, method, path, original_line)
current_section = None
for i, line in enumerate(lines):
    if line.startswith("## Truly Missing User-Facing Endpoints"):
        current_section = "missing"
    elif line.startswith("## Backend-Only / Internal Endpoints"):
        current_section = "backend"
        break
    
    if current_section == "missing" and line.startswith("- `"):
        m = re.match(r'- `([A-Z]+)\s+([^`]+)`', line)
        if m:
            missing_endpoints.append((i, m.group(1), m.group(2), line))

implemented_indices = set()

# 3. Check each endpoint
for i, method, path, orig in missing_endpoints:
    # Get meaningful segments
    segments = [s for s in path.split('/') if s and not s.startswith('{') and not s.startswith('$')]
    
    found = False
    for filepath, content in frontend_texts:
        normalized_content = content.lower()
        method_lower = method.lower()
        
        # We look for files where the API method (e.g. get, post) is used, or 'api.get', 'axios.post', etc.
        # But more importantly, the segments must be present.
        if len(segments) == 0:
            continue
            
        # Ensure all segments are in this file
        all_match = True
        for seg in segments:
            if seg.lower() not in normalized_content:
                all_match = False
                break
                
        if all_match:
            # Check if there's any API-calling looking thing or fetch
            if re.search(r'(api|axios|fetch)\.?(get|post|put|delete|patch|)', normalized_content):
                implemented_indices.add(i)
                print(f"Found {method} {path} in {os.path.basename(filepath)}")
                found = True
                break
                
    if not found:
        pass # print(f"Still missing: {method} {path}")

print(f"Identified {len(implemented_indices)} as implemented out of {len(missing_endpoints)} missing endpoints.")

# Rewrite the file, removing the implemented ones, and cleaning up empty headers
new_lines = []
for i, line in enumerate(lines):
    if i in implemented_indices:
        continue
    new_lines.append(line)

# Clean up empty headers
final_lines = []
for i, line in enumerate(new_lines):
    if line.startswith("### `"):
        # check if there are any endpoints under this header before the next header
        has_endpoints = False
        for j in range(i+1, len(new_lines)):
            if new_lines[j].startswith("### `") or new_lines[j].startswith("## "):
                break
            if new_lines[j].startswith("- `"):
                has_endpoints = True
                break
        if not has_endpoints:
            continue
    final_lines.append(line)

# Also update the counts at the top
truly_missing_count = len(missing_endpoints) - len(implemented_indices)
final_text = "".join(final_lines)
final_text = re.sub(r'Truly missing frontend endpoints: \d+', f'Truly missing frontend endpoints: {truly_missing_count}', final_text)

with open(filtered_file, "w", encoding="utf-8") as f:
    f.write(final_text)

print("Updated filtered_endpoints.md")
