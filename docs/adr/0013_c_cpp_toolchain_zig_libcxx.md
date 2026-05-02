# Zig as the single C/C++ toolchain, libc++ only

The Template pins one C/C++ toolchain: the upstream Zig release tarball,
fetched into `.local/toolchain/$REPO_ARCH` like every other pinned tool.
Zig provides clang, LLD, libc, and libc++ in one archive and targets
musl by default. Products forking this Template build C and C++ code
through `zig cc` and `zig c++` against musl with libc++; nothing else
is supported out of the box. Tracking issue: #2.

The pinned-tools rationale already lives in ADR-0002 and ADR-0008. The
remaining choice was whether the C/C++ stack would be GCC + glibc +
libstdc++, clang + musl + libc++ assembled from separate pinned tarballs,
or a single bundled toolchain. Zig wins because one tarball replaces
five (`cc`, `c++`, `ld`, `libc`, libc++ headers and runtime), the same
binary cross-compiles between `x86_64-linux-musl` and `aarch64-linux-musl`
without a second sysroot, and the default ABI already matches the pinned
musl Python from ADR-0008. Upgrades follow the existing per-tool
fetcher upgrade path: bump version + sha256 in
`bootstrap/tools/zig.sh`, bump `bootstrap/vars/local_cache_key.sh` if
prune rules change, done.

## Why libc++ and not libstdc++

Zig ships libc++ sources in `lib/` of the same tarball; libc++ is the
only C++ standard library it knows how to build. libstdc++ would have
to come from a pinned GCC source tree, which would reintroduce the
"build your own compiler" cost ADR-0002 explicitly rejected. Mixing
both in one product is worse than picking either one — libstdc++ and
libc++ have incompatible string and exception ABIs, and any third-party
library compiled against the wrong stdlib silently breaks at link or
runtime. Pick one, document it, accept the consequence. We pick the
one that comes free with the toolchain we already have.

## Consequences

- Third-party C++ source must build against libc++. Most actively
  maintained projects already test that path; the porting cost is
  usually a `-stdlib=libc++` flag and dropping a few `<bits/...>`
  GCC-extension includes.
- The C++ standard available is whatever the bundled clang supports.
  Bumping the C++ language level means bumping Zig.
- `lib/` inside the Zig install is **not** prunable. Zig recompiles
  libc and libc++ from those sources on first use of each target;
  pruning `lib/` breaks the toolchain on the first build. Only `doc/`
  is pruned. ADR-0006 cache hygiene still applies (the install prefix
  is an accelerator and a refetch must restore it byte-identically).
- Runtime products linked against libc++ ship libc++ symbols, not
  libstdc++ symbols. A future need for a libstdc++-only library is a
  product-level decision, not a Template-level fallback.
- Zig version bumps are normal pinned-tool upgrades. Treat them as
  toolchain changes (cache-key impact, smoke test rerun) rather than
  routine dependency bumps.

## Considered options

- GCC + glibc + libstdc++ with hand-pinned tarballs. Rejected because
  it pulls glibc into the Template's default ABI, conflicts with the
  musl Python pin in ADR-0008, and the runtime would no longer be
  Alpine/static-portable by default.
- clang + musl + libc++ assembled from separately pinned LLVM, musl,
  and libc++ tarballs. Rejected because the per-tarball pin/upgrade
  matrix grows quadratically with target arches and the resulting stack
  is functionally equivalent to what Zig already ships pre-assembled
  and cross-compile-tested upstream.
- Ship Zig **and** GCC, let products pick. Rejected because two
  toolchains means two cache footprints, two sets of compiler-shaped
  bug reports, and the standing temptation to mix libc++ and libstdc++
  in one product.
