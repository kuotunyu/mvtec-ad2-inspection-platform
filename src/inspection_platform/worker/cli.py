from __future__ import annotations

import argparse

from .service import serve


def main() -> int:
    parser = argparse.ArgumentParser(prog="inspection-worker")
    parser.add_argument("command", choices=("serve",))
    args = parser.parse_args()
    if args.command == "serve":
        serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
