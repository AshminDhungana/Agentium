import re

def normalize_path(path):
    # Remove query params
    path = path.split('?')[0]
    # Remove trailing slashes
    if path.endswith('/'):
        path = path[:-1]
    # Replace path params {id} or ${id} with {}
    path = re.sub(r'\{[^}]+\}', '{}', path)
    path = re.sub(r'\$\{[^}]+\}', '{}', path)
    # Sometimes frontend uses just /agents instead of /api/v1/agents if baseURL is set
    # Let's ensure both have or don't have /api/v1
    # But usually VITE_API_BASE_URL handles http://localhost:8000
    # In my extraction, frontend routes sometimes are just '/upload' instead of '/api/v1/files/upload'
    # Actually, let's keep it simple first and see
    return path.lower()

backend_routes = []
with open(r"e:\Agentium\test\backend_routes.txt", "r", encoding='utf-8') as f:
    for line in f:
        if line.strip():
            parts = line.split(' ')
            if len(parts) >= 2:
                method = parts[0]
                path = parts[1]
                backend_routes.append((method, path, line.strip()))

frontend_routes = []
with open(r"e:\Agentium\test\frontend_routes.txt", "r", encoding='utf-8') as f:
    for line in f:
        if line.strip():
            parts = line.split(' ')
            if len(parts) >= 2:
                method = parts[0]
                path = parts[1]
                frontend_routes.append((method, path, line.strip()))

# Create normalized sets
frontend_set = set()
for m, p, _ in frontend_routes:
    # Some frontend might just be /health instead of /api/health
    # We will store multiple variants to be safe in matching
    norm_p = normalize_path(p)
    frontend_set.add(f"{m} {norm_p}")
    if not norm_p.startswith('/api'):
        frontend_set.add(f"{m} /api{norm_p}")
        frontend_set.add(f"{m} /api/v1{norm_p}")

missing_in_frontend = []
found_in_frontend = []

for m, p, orig in backend_routes:
    norm_p = normalize_path(p)
    key = f"{m} {norm_p}"
    
    # Check if this backend route exists in frontend
    matched = False
    
    # exact match on normalized
    if key in frontend_set:
        matched = True
    else:
        # fuzzy match: if the backend path ends with the frontend path
        # Because frontend might do axios.get('/upload') with baseURL='/api/v1/files'
        for fm, fp, _ in frontend_routes:
            if m == fm:
                norm_fp = normalize_path(fp)
                if norm_p.endswith(norm_fp) or norm_fp.endswith(norm_p):
                    matched = True
                    break
                    
    if matched:
        found_in_frontend.append(orig)
    else:
        missing_in_frontend.append(orig)

# Output results to a markdown file
with open(r"e:\Agentium\test\disconnected_endpoints.md", "w", encoding='utf-8') as f:
    f.write("# Disconnected Backend Endpoints\n\n")
    f.write(f"Total backend endpoints: {len(backend_routes)}\n")
    f.write(f"Total frontend endpoints: {len(frontend_routes)}\n")
    f.write(f"Connected endpoints: {len(found_in_frontend)}\n")
    f.write(f"Disconnected endpoints: {len(missing_in_frontend)}\n\n")
    
    f.write("## Disconnected Endpoints (Backend -> Frontend)\n\n")
    for missing in sorted(missing_in_frontend):
        f.write(f"- `{missing}`\n")
        
print(f"Comparison complete. Found {len(missing_in_frontend)} missing.")
