#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo 'This host currently requires Linux x86_64.' >&2
  exit 1
fi
for tool in python3 cc pkg-config ffmpeg; do
  if ! command -v "$tool" >/dev/null; then
    echo "Missing dependency: $tool" >&2
    exit 1
  fi
done
pkg-config --exists sdl2 || { echo 'Install SDL2 development headers.' >&2; exit 1; }
python3 -c 'import tkinter' || { echo 'Install Python/Tk (python3-tk on Ubuntu, tk on Arch).' >&2; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/build_native.py
printf '\nReady. Import an APK with ./re4pc.sh import /path/to/game.apk\n'
printf 'Then launch with ./re4pc.sh run\n'
