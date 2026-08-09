from __future__ import annotations

import argparse


def main() -> int:
    parser = argparse.ArgumentParser(prog="inspection-worker")
    parser.add_argument("command", choices=("serve",))
    parser.parse_args()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
