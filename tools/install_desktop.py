"""Entry point for per-user Linux desktop installation."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from re4pc.desktop import main

if __name__ == '__main__':
    sys.exit(main())
