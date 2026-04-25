# Per-tool fetcher specs over a single toolchain manager

`bootstrap/tools/<tool>.sh` files declare each pinned tool in shell
variables and source one of two helpers (`fetch_binary.sh`,
`fetch_source.sh`). We rejected standardizing on a single manager
(mise, asdf) because:

- Products may need both binary and source builds for the same
  toolchain (e.g. a stock binary + a hand-built variant with custom
  flags).
- A manager adds a third-party dependency that itself must be
  fetched and pinned.
- Per-tool files keep the cache-key invalidation surface obvious:
  changing `bootstrap/tools/<tool>.sh` bumps the CI cache key
  naturally; the helpers do not need to change.

Cost: more lines per tool. Acceptable because each spec is small
(URL, SHA, version) and copy-pasting one is fast.
