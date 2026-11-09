#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python -c 'from hub.app import app; from hub.registry import assert_mcp_v1; assert_mcp_v1(); print("imports: ok")'
ruff check --no-respect-gitignore hub tests
pytest -q
if command -v ss >/dev/null 2>&1; then
  ss -ltn
else
  printf 'ss unavailable; listening TCP sockets from /proc:\n'
  python - <<'PY'
import socket
from pathlib import Path

print("State Recv-Q Send-Q Local Address:Port Peer Address:Port")
for file_name, family in (("/proc/net/tcp", socket.AF_INET), ("/proc/net/tcp6", socket.AF_INET6)):
    path = Path(file_name)
    if not path.exists():
        continue
    for row in path.read_text().splitlines()[1:]:
        columns = row.split()
        if columns[3] != "0A":
            continue
        address, port = columns[1].split(":")
        raw = bytes.fromhex(address)
        if family == socket.AF_INET:
            raw = raw[::-1]
        else:
            raw = b"".join(raw[index:index + 4][::-1] for index in range(0, 16, 4))
        host = socket.inet_ntop(family, raw)
        print(f"LISTEN 0 0 {host}:{int(port, 16)} 0.0.0.0:*")
PY
fi
matches=$(grep -c 'KEY=\|sk-' mcp_servers.json || true)
if [ "$matches" -ne 0 ]; then
  printf 'mcp_servers.json contains %s secret-like line(s)\n' "$matches" >&2
  exit 1
fi
printf 'mcp_servers.json secret scan: 0 matches\n'
