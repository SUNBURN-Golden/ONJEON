"""Extracted-coverage table plumbing: provisional row schema, extractors, versioned writer.

The schema in tables/schema.py is PROVISIONAL and is not the data contract (docs/data/ owns it).
Subpackage of crawler: stdlib only, no network, no I/O beyond the files explicitly written by
writer.write_table.
"""
