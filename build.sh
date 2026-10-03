#!/bin/sh
# Builds dist/macout: one executable file (a Python zipapp). The file contains no compiled code,
# so the same file runs on x86_64 and aarch64 as long as python3 and python3-gi are installed.
# build.sh also writes per-architecture copies named macout-x86_64 and macout-arm64 so release
# files are labelled clearly. They are byte-identical apart from the name.
set -e
cd "$(dirname "$0")"
rm -rf build dist && mkdir -p build/pkg dist
cp -r macout_app build/pkg/
find build/pkg -name __pycache__ -prune -exec rm -rf {} +
cat > build/pkg/__main__.py <<'PY'
import sys
sys.argv[0] = sys.argv[0]
from macout_app import launcher
sys.exit(launcher.main())
PY
# the launcher logic lives in the package so both ./macout and the zipapp share it
python3 -m zipapp build/pkg -o dist/macout -p "/usr/bin/env python3"
chmod +x dist/macout
cp dist/macout dist/macout-x86_64
cp dist/macout dist/macout-arm64
( cd dist && sha256sum macout macout-x86_64 macout-arm64 > SHA256SUMS )
echo "Built dist/macout (architecture independent Python zipapp)"
