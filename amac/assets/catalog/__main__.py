"""Write the cross-software equivalence tables.

Usage: ``python -m amac.assets.catalog [DIRECTORY]`` (current directory by default).
"""

from __future__ import annotations

import argparse

from amac.parameter.catalog import OUTPUT_FILES, write_availability


def main(argv: list[str] | None = None) -> None:
    """Write the ``available_*.json`` files and print their paths."""
    parser = argparse.ArgumentParser(
        prog="python -m amac.assets.catalog",
        description=f"Write {', '.join(OUTPUT_FILES.values())} from the catalog "
        "and the doc.json files.",
    )
    parser.add_argument(
        "directory", nargs="?", default=".", help="output directory (default: .)"
    )
    args = parser.parse_args(argv)
    for path in write_availability(args.directory):
        print(path)


if __name__ == "__main__":
    main()
