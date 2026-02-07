import sys

# Force unbuffered output for immediate feedback
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

from agents.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

