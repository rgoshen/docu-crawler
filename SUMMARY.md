# Summary

## [2026-08-23 17:40] Commit Summary

**Change Type:** Fix
**Scope:** CLI argument parsing and configuration merge

**Summary:**
Config file settings are no longer discarded by argparse's own defaults.
`--single-file`, `--frontmatter` and `--use-gcs` now declare `default=None`
instead of relying on `store_true`'s implicit `False`, and `--storage-type` and
`--sftp-port` no longer carry literal defaults. `sftp_port` was added to the
`DEFAULTS` dict in `src/cli.py` so it keeps its fallback of 22.

The precedence rule that `run()` applied inline was extracted into
`resolve_params(config, args_dict)` so it can be tested without invoking the
whole CLI. Behaviour of that extraction is unchanged; it is the same merge
followed by the same `DEFAULTS` fill.

New `tests/test_config.py` adds 16 tests covering all three precedence levels.
Full suite: 54 tests, all passing.

**Rationale:**
`merge_config_and_args` decides that an argument was supplied by testing
`value is not None`. That contract is sound; the bug was that `store_true` and
literal `default=` values broke it by making unsupplied arguments indistinguishable
from supplied ones. Fixing the arguments rather than the merge keeps a single
unambiguous signal for "not supplied" and leaves `DEFAULTS` as the one place
fallback values are declared.

The alternative — special-casing boolean flags inside `merge_config_and_args` —
was rejected. It would have put knowledge of individual argument types into a
generic merge helper and left the same trap waiting for the next argument given
a literal default.

**Bug Fix Context:**
Reported after crawling `https://react.dev/reference/react/` with a config file
setting `single_file: true`, which produced 49 separate Markdown files instead of
one combined `documentation.md`. The failure was silent: because the startup
banner prints the merged `params`, the log reported `single_file: False` while the
config file plainly said true, and under docu-crawler 1.0.0 — which has no
`--single-file` argument at all — the same banner reported `True` for a setting
the crawler could not act on.

Verified end-to-end with the reporter's own config file: the crawl now logs
`Single file mode enabled` and writes a single `documentation.md`.

Two further defects were found while verifying and are recorded in `TODO.md`
rather than fixed here, per the agreed scope:
- 403 receives no retry backoff, so throttling cascades into total failure
- `--frontmatter` emits unparseable YAML, its keys reflowed onto one line by
  `_post_process_markdown`

**References:**
- TODO.md: [2026-08-23] Fix: config file values silently overridden by argparse defaults
