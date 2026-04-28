# Changelog

All notable changes to Thera AI are recorded here. This project follows the
shape of Keep a Changelog, with release decisions anchored in DESIGN_LOG.

## v1.1.0 - 2026-04-28

### Added

- Vendored kit119/D-tipitaka corpus source dumps under `vendor/D-tipitaka/1.2/`
  so `thera corpus init` can build the corpus from a full clone without network.
- Added `vendor/D-tipitaka/1.2/README.TXT` and `NOTICE` for upstream attribution.
- Added `vendor/D-tipitaka/1.2/UPSTREAM_FILES` SHA-256 manifest for all 5
  vendored upstream files.
- Added JSON diagnostics for `thera sikkhapada ... --format json` when parser
  hard-count verification exits 70.
- Added a default-mode local-vendor init test with a subprocess byte-equal hook.

### Changed

- `thera corpus init` now tries verified local vendor files first and falls back
  to the pinned network source only when local vendor files are missing or invalid.
- Existing-corpus init refusal now raises `CorpusAlreadyExistsError`, allowing CLI
  exit-code dispatch by exception type rather than message substring.
- Corpus-marked tests now follow the same skip-by-default convention as
  verify-marked tests.
- README files document offline corpus initialization and upstream attribution.
- `docs/CLI_SPEC.md` records the §28.7 scope clarification for bilingual
  language-switcher docs.

### Attribution

- Vendored kit119/D-tipitaka @ 645aa33 corpus sources under upstream README.TXT
  public-domain-leaning dedication; see NOTICE for attribution chain.

## v1.0.0 - 2026-04-28

### Added

- Initial public release of the zero-hallucination Tipitaka CLI.
- Verbatim retrieval commands: `info`, `search`, `read`, `compare`,
  `cross-ref`, `verify`, `sikkhapada`, and `corpus init|validate`.
- Bilingual user documentation: README, QUICKSTART, ARCHITECTURE, and USE_CASES.
- MIT license and public decision history through DESIGN_LOG §30.10.

### Verification

- Phase 4 and Phase 5 were LOKI-signed before public release.
- Default test suite passed with 89 passing and 2 network-gated skips at ship.
- v1.0.0 ship verdict is recorded in DESIGN_LOG §30 and §30.10.
