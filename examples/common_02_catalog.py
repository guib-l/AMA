"""The canonical catalog and its links with the ``doc.json`` of each software.

Runnable without any program: only metadata is read.

``catalog/`` names methods, modules and options independently of any software
(format in ``CATALOG_SCHEMA.md``). A ``doc.json`` node points to an entry with
``CANONICAL``; ``links()`` reads these pointers, so the same canonical name can be
followed from one software to another.
"""

from collections import Counter

from amac.parameter.catalog import documented_software, links, load_catalog

# Canonical names used by the other examples of this directory.
CANONICAL_NAMES = ("DFTB2", "GFN2-xTB", "SINGLE_POINT", "MONKHORST_PACK")

# This example describes no calculation: it only reads metadata.
SPECS = ()


def show_catalog() -> None:
    """List what the catalog names, and resolve a few aliases."""
    catalog = load_catalog()
    for kind in ("METHOD", "MODULE", "OPTION"):
        entries = catalog.of_kind(kind)
        top = [entry.id for entry in entries if entry.parent is None]
        print(f"{kind:7s} {len(entries):3d} entries, {len(top)} top level: {top}")

    # Aliases resolve to the entry, whatever their case.
    for name in ("SCC-DFTB", "ks-dft", "MONKHORST_PACK"):
        entry = catalog.resolve(name)
        parent = entry.parent or "-"
        print(f"{name:16s} -> {entry.id} ({entry.kind}, parent {parent})")

    # Variants are children of their family.
    print(f"DFTB variants: {[child.id for child in catalog.children('DFTB')]}")


def show_links() -> None:
    """Follow the CANONICAL pointers of every software that has a doc.json."""
    catalog = load_catalog()
    for software, schema in documented_software().items():
        found = links(schema, catalog)
        kinds = Counter(catalog.resolve(link.canonical).kind for link in found)
        print(f"{software:8s} {len(found)} links {dict(kinds)}")

    # The same canonical name, written differently by each program.
    for canonical in CANONICAL_NAMES:
        keywords = {
            software: link.keyword
            for software, schema in documented_software().items()
            for link in links(schema, catalog)
            if link.canonical == canonical
        }
        print(f"{canonical:14s} {keywords or 'not implemented yet'}")


def main() -> None:
    """Show the catalog, then its links with the implemented software."""
    show_catalog()
    show_links()


if __name__ == "__main__":
    main()
