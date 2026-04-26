# Pinned binary Python for repo machinery

The Template bootstraps a pinned CPython binary into
`.local/toolchain/$REPO_ARCH` and puts it on `PATH` before dispatching
repo commands. We chose a python-build-standalone musl
`install_only_stripped` CPython 3.14.4 build instead of targeting a
broad host Python subset because repo machinery should run against one
explicit interpreter with baked-in CI caching rather than accumulate
polyfill and host-version drift.

The host still needs enough POSIX shell, `curl`, `tar`, and checksum
tooling to fetch stage-0 tools. Python itself is then repo-owned
toolchain state and follows the cache hygiene rules: source URL and
SHA256 are canonical, `.local/toolchain` and `.local/stamps` are only
accelerators, and cache misses refetch. We default to musl artifacts
because Alpine/static product portability is the more flexible baseline
than GNU libc runner convenience. The upstream musl install-only
artifacts are dynamically linked to `/lib/ld-musl-*`; the Python spec
therefore wraps the interpreter with the bootstrapped Alpine musl
loader so the host does not need musl installed. This makes bwrap's
Alpine rootfs a bootstrap prerequisite for Python, so `python.sh`
declares `TOOL_DEPS=(bwrap)` and `repo.sh` solves the bootstrap graph
before fetching tools.

## Considered options

- Require host Python `>=3.10` and keep scripts on a compatibility
  subset. Rejected because it pushes interpreter behavior into ambient
  host state and encourages internal polyfills.
- Build CPython from source. Rejected for now because source builds add
  too much first-run and CI cost for this Template's current needs.
- Default to GNU libc Python. Rejected because it optimizes for the
  current CI runner instead of the more portable Alpine/static Product
  target.
