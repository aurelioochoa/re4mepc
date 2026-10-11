#!/usr/bin/env bash
set -euo pipefail
RE4PC_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$RE4PC_DIR"
if [[ ! -x .venv/bin/python || ! -f build/libre4audio.so || ! -f build/libre4fast.so ]]; then
  echo 'Run ./setup.sh first.' >&2
  exit 1
fi
exec .venv/bin/python -u -m re4pc "$@"
