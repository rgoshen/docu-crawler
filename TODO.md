# TODO

## [2026-08-23] Fix: config file values silently overridden by argparse defaults

**Objective:**
Settings supplied in `crawler_config.yaml` are discarded whenever the corresponding
CLI argument declares a non-`None` default. A user with `single_file: true` in their
config file gets one Markdown file per page instead of the combined
`documentation.md`, with no warning — the startup banner even reports
`single_file: False`, so the failure is silent and misleading.

Reported against a crawl of `https://react.dev/reference/react/` using
`--config ~/.config/docu-crawler/crawler_config.yaml`.

**Root cause:**
`merge_config_and_args` (`src/utils/config.py`) treats "argument is not `None`" as
"user supplied this argument":

```python
for key, value in args_dict.items():
    if value is not None:
        result[key] = value
```

`--single-file` and `--frontmatter` are declared `action='store_true'`, so argparse
sets them to `False` — not `None` — when the flag is absent. `False is not None`,
so the implicit CLI value overwrites the config file's `true`. The same defect
affects every argument carrying a non-`None` argparse default: `--storage-type`
(`'local'`), `--sftp-port` (`22`) and `--use-gcs` (`False`).

**Approach:**
Make "absent" unambiguous rather than special-casing the merge. Every optional
argument declares `default=None`; the single source of truth for fallback values
stays the `DEFAULTS` dict in `src/cli.py`, which already fills any `None` after the
merge. `sftp_port` is added to `DEFAULTS` so it retains its 22 fallback.

Precedence after the fix, highest first: explicit CLI argument → config file →
`DEFAULTS`.

**Tests:**
New `tests/test_config.py` covering `merge_config_and_args` and CLI parsing:
- config `single_file: true` survives when `--single-file` is absent
- config `frontmatter: true` survives when `--frontmatter` is absent
- explicit `--single-file` still overrides config `single_file: false`
- config `storage_type: s3` survives when `--storage-type` is absent
- config `sftp_port: 2222` survives when `--sftp-port` is absent
- config `use_gcs: true` survives when `--use-gcs` is absent
- unrelated config keys pass through untouched
- `DEFAULTS` supplies the fallback when neither config nor CLI provides a value

**Risks & Tradeoffs:**
- Behaviour change for anyone relying on the CLI default to reset a config value.
  There is no way to express "force false" on the command line for a `store_true`
  flag, but that limitation already exists and no `--no-*` counterparts are being
  removed.
- `get_storage_config` reads `config.get('sftp_port', 22)`, which returns `None`
  for a present-but-`None` key. Adding `sftp_port` to `DEFAULTS` resolves this
  before `get_storage_config` is reached; ordering in `src/cli.py` is covered by
  test.

---

## [2026-08-23] Deferred: adaptive backoff on HTTP 403/429

**Objective:**
A throttled crawl currently cascades into total failure. In the 2026-08-22
react.dev run, 87 consecutive pages returned 403 and every one was recorded as a
hard failure.

**Decision (agreed 2026-08-23, not yet implemented):**
Adaptive backoff. On 403 or 429: retry with exponential backoff, honour
`Retry-After` when the server sends it, and permanently raise the inter-request
delay for that domain for the remainder of the crawl. The crawl finishes, more
slowly, instead of failing outright.

**Approach:**
- Add `403` to `retry_status_codes` in `retry_on_http_error`
  (`src/utils/retry.py`); it currently lists only `(500, 502, 503, 504, 429)`, so
  403 gets no backoff at all.
- Give `SimpleRateLimiter` a method to raise a domain's delay, and call it from
  `DocuCrawler` when a throttling response is seen.
- Parse `Retry-After` (both delta-seconds and HTTP-date forms).

**Tests:**
- 403 triggers retry rather than immediate failure
- domain delay increases after a throttling response and persists
- `Retry-After` header is honoured when present
- non-throttling 4xx (404) still fails fast without backoff

**Risks & Tradeoffs:**
- 403 is ambiguous: it means "throttled" on some hosts and "permanently forbidden"
  on others. Retrying a genuine authorization failure wastes three requests per
  URL. Cap the escalation so a misread 403 cannot stall a large crawl.

**Note:** The dominant *cause* of the react.dev throttling — refetching `#fragment`
URLs as if they were distinct pages, 113 requests for 49 unique pages — was already
fixed in v1.1.0 by the `urldefrag` call in
`src/processors/html_processor.py:extract_links`. This item addresses the crawler's
reaction to throttling, not its cause.

---

## [2026-08-23] Deferred: --frontmatter emits unparseable YAML

**Objective:**
`--frontmatter` is documented as producing YAML frontmatter for RAG and LLM
indexing, but the emitted block is not valid YAML, so any downstream parser
rejects it or silently reads a single bogus key.

Observed:

```
---

title: "React Reference Overview" source: "https://react.dev/reference/react/" date: 2026-08-23

---
```

Expected: `title`, `source` and `date` on separate lines, with no blank line
between the `---` delimiters and the keys.

**Root cause:**
`_add_frontmatter` (`src/processors/html_processor.py:155`) builds the block
correctly with newline joins. The defect is ordering: `extract_text` calls
`_add_frontmatter` at line 139 and then `_post_process_markdown` at line 144, and
the latter ends with a paragraph-reflow loop that joins consecutive lines not
recognised as "special" (headings, list items, code fences). The three YAML keys
match none of those, so they are reflowed into one line as if they were prose.

Reproduced in both single-file and per-file modes, so this is independent of
`single_file`.

**Approach:**
Apply the frontmatter after post-processing rather than before, so the block is
never reflowed. Prefer this over teaching `_post_process_markdown` to recognise
frontmatter: it keeps the cleanup routine ignorant of document metadata and there
is no reason to post-process generated text that was never HTML.

Also review whether per-page frontmatter belongs in `--single-file` output at all.
Frontmatter is by definition file-level, and the combined document currently
carries one block per page, mid-file.

**Tests:**
- emitted frontmatter parses with `yaml.safe_load` and yields the three keys
- `title`, `source`, `date` each occupy their own line
- a title containing a colon or a double quote is escaped rather than breaking
  the document
- post-processing still reflows ordinary body prose as before

**Risks & Tradeoffs:**
- Moving the call changes output for every existing `--frontmatter` user. The
  current output is unparseable, so nothing that works today can break, but any
  downstream regex tuned to the collapsed form would need updating.
- Titles are interpolated into a quoted YAML scalar without escaping; a title
  containing `"` produces a broken document. Worth fixing in the same change.
