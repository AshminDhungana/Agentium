#!/usr/bin/env bash
# enforce-shared-components.sh
# Fails CI if ad-hoc loading spinner or toast patterns bypass shared components.
set -euo pipefail

FAIL=0

echo "🔍 Checking for ad-hoc Loader2 usage..."
# Find Loader2 imports outside LoadingSpinner.tsx
if grep -rn "import.*Loader2" frontend/src/ | grep -v "LoadingSpinner.tsx"; then
  echo "❌ Found ad-hoc Loader2 import(s). Use <LoadingSpinner> instead."
  FAIL=1
fi

echo "🔍 Checking for direct react-hot-toast imports..."
# Find direct toast imports outside useToast.ts and App.tsx (which mounts the <Toaster>)
if grep -rn "from 'react-hot-toast'" frontend/src/ | grep -v "useToast.ts" | grep -v "App.tsx"; then
  echo "❌ Found direct react-hot-toast import(s). Use useToast() / showToast instead."
  FAIL=1
fi

if [ "$FAIL" -eq 1 ]; then
  exit 1
fi

echo "✅ Shared component enforcement passed."
