import re

with open("disconnected_endpoints.md", "r", encoding="utf-8") as f:
    lines = f.readlines()

endpoints = []
for line in lines:
    if line.startswith("- `") and "(in" in line:
        m = re.match(r'- `([^`]+)`', line)
        if m:
            endpoints.append(m.group(1))

backend_only_patterns = [
    # Webhooks & Integrations
    r'/(whatsapp|telegram|discord|slack|google_chat|imessage|matrix|teams|zalo|signal|email)/\{webhook_path\}',
    r'/webhooks/.*',
    
    # Internal Host/Container APIs (used by executor, not frontend)
    r'/container/.*',
    r'/containers/.*',
    r'/file/(read|write)',
    r'/directory/list',
    r'/system/processes',
    
    # Background / Cron Operations
    r'/bulk/liquidate-idle',
    r'/run-sunset-cleanup',
    r'/admin/optimize',
    
    # Internal Health / System Probes
    r'/api/health',
    r'/health/.*',
    r'/api/v1/monitoring/health',
    
    # Mobile Specific (to be implemented in iOS/Android, not React Web UI)
    r'/register-device/.*',
    r'/offline/.*',
    
    # Audio/Voice streaming/internal parsing
    r'/synthesize',
    r'/transcribe',
    r'/voices',
    r'/languages',
    r'/audio/.*',
]

missing_frontend = []
backend_only = []

for ep in endpoints:
    is_backend = False
    for pat in backend_only_patterns:
        if re.search(pat, ep):
            is_backend = True
            break
            
    if is_backend:
        backend_only.append(ep)
    else:
        missing_frontend.append(ep)

with open("filtered_endpoints.md", "w", encoding="utf-8") as f:
    f.write("# Endpoint Analysis\n\n")
    f.write(f"Total disconnected endpoints: {len(endpoints)}\n")
    f.write(f"Backend-only/System endpoints: {len(backend_only)}\n")
    f.write(f"Truly missing frontend endpoints: {len(missing_frontend)}\n\n")

    f.write("## Truly Missing User-Facing Endpoints\n\n")
    f.write("These endpoints exist in the backend and represent user-facing functionality that appears to be missing from the React frontend.\n\n")
    
    grouped = {}
    for ep in missing_frontend:
        parts = ep.split(" (in ")
        path = parts[0]
        file = parts[1][:-1] if len(parts) > 1 else "Unknown"
        
        if file not in grouped:
            grouped[file] = []
        grouped[file].append(path)
        
    for file in sorted(grouped.keys()):
        f.write(f"### `{file}`\n")
        for path in sorted(grouped[file]):
            f.write(f"- `{path}`\n")
        f.write("\n")

    f.write("## Backend-Only / Internal Endpoints\n\n")
    f.write("These endpoints are not expected to be called directly by the React frontend.\n\n")
    
    grouped_backend = {}
    for ep in backend_only:
        parts = ep.split(" (in ")
        path = parts[0]
        file = parts[1][:-1] if len(parts) > 1 else "Unknown"
        
        if file not in grouped_backend:
            grouped_backend[file] = []
        grouped_backend[file].append(path)
        
    for file in sorted(grouped_backend.keys()):
        f.write(f"### `{file}`\n")
        for path in sorted(grouped_backend[file]):
            f.write(f"- `{path}`\n")
        f.write("\n")

print(f"Filtered out {len(backend_only)} backend-only endpoints.")
print(f"Found {len(missing_frontend)} truly missing endpoints.")
