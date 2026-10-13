#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
if [[ $(uname -s) != Linux || $(uname -m) != x86_64 ]]; then
  echo 'This host currently requires Linux x86_64.' >&2
  exit 1
fi
missing=()
for tool in python3 cc pkg-config ffmpeg; do
  if ! command -v "$tool" >/dev/null; then
    missing+=("$tool")
  fi
done
if command -v pkg-config >/dev/null && ! pkg-config --exists sdl2; then
  missing+=('SDL2 development headers')
fi
if command -v python3 >/dev/null; then
  python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || missing+=('Python 3.10 or later')
  python3 -c 'import tkinter' 2>/dev/null || missing+=('Python/Tk')
  python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=('Python venv/ensurepip')
fi
if (( ${#missing[@]} )); then
  printf 'Missing prerequisites:\n' >&2
  printf '  - %s\n' "${missing[@]}" >&2
  printf '\nInstall system packages, then rerun make setup or make install.\n' >&2
  printf 'Debian/Ubuntu:\n  sudo apt-get install python3-venv python3-tk build-essential pkg-config libsdl2-dev libgl1-mesa-dev ffmpeg fonts-ipafont-gothic\n' >&2
  printf 'Arch Linux:\n  sudo pacman -S --needed python tk make gcc pkgconf sdl2-compat ffmpeg mesa noto-fonts-cjk\n' >&2
  exit 1
fi
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python tools/build_native.py
printf '\nReady. Open the launcher with make play to import your APK and play.\n'
printf 'CLI import: make import APK="/path/to/game.apk"\n'
printf 'Validate with make check-game, then start with make run.\n'
