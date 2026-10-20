# docproc execution contract

Run from the repository root:

- `bash services/docproc/test_sandbox.sh` (static suite always; runs the container isolation probe when Docker Compose is available, otherwise prints "LIVE: SKIPPED" — not I13 evidence; `DOCPROC_SANDBOX_REQUIRE_LIVE=1` makes Docker absence a failure)
- `python3 -B -m unittest discover -s services/docproc/tests -v`
- `python3 -B services/docproc/tests/container_network.py` (requires Docker Compose; absence is a failure, never a skip)
- `python3 -I tools/ci/check_leak.py`
- `python3 -I tools/ci/check_skeleton.py`
- `cargo test --workspace`

Extraction requires Poppler 24.02.x, matching ontology fp-0.1. The Dockerfile uses Ubuntu 24.04 and asserts that version during build. It deliberately rejects other Poppler versions rather than relabeling their fingerprints. No Python dependencies beyond the standard library.

Build/run: set DOCPROC_INPUT_DIR to a directory containing a PDF and segment specification, then run `docker compose -f services/docproc/compose.yaml run --build --rm docproc /input/document.pdf --segments /input/segments.json`. JSON goes to stdout, never to a tracked file. For fixtures add `--origin fixture`. Verify saved JSON using `--verify /input/result.json` instead of `--segments`.

Segment input is a nonempty JSON array of objects with integer page_from/page_to (physical, inclusive, 1-based), doc_role (보통약관, 특약 약관, 별표, 요약서, 공시 목록, 안내 쪽), seg_rule_ver (slug of the upstream boundary rule), and optional boundary (confirmed/unconfirmed; default unconfirmed). Overlaps and nonexistent pages fail. Classification and boundary decisions come from the caller; this extractor does not invent them. Table/heading/footnote/reference reconstruction is not implemented: empty arrays/null mean unclassified, not confirmed absent. Every occurrence stays hold/extraction_uncertain. Textless pages fail for a separate OCR strategy. No semantic mapping or approval is performed.

Occurrences are physical layout lines with word boxes, exact reconstructed word text (single word separators), and a top-left PDF-point bounding box [xmin,ymin,xmax,ymax]. Printed article headings have printed paths; other lines have inferred location paths. No claim of complete article hierarchy. Quotes are not normalized for comparison. verify reextracts the PDF and compares the entire result including source hash, coordinates, text and metadata. Fingerprints separately use per-page -layout output concatenation, NFC, whitespace removal, UTF-8 SHA-256.

The local development host has Poppler 25.03.0. Unit tests execute its real bbox/layout extraction on generated synthetic PDFs but patch the version gate to exercise object wiring. They do NOT demonstrate byte compatibility with 24.02 or validate real insurance documents. Fingerprint normalization has independent known-answer tests. Run the same unit suite inside a Poppler 24.02 environment for pinned-tool evidence.

Network isolation is provided by compose network_mode:none, not the Docker image alone. Do not deploy with host/default networking. The local compose database/archive stack is intentionally not attached: docproc receives only a read-only staged input mount, with no credentials or network. The container probe uses documentation-only IPv4/IPv6 addresses and fails if a connection succeeds. No production requests are needed.
