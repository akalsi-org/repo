---
name: simplify
description: Review changed code for reuse, quality, and efficiency, then fix any issues found. Use after a feature lands, before opening a PR, or when the user says "simplify" / "tighten this up".
---

# simplify

Pass over recently-changed code and remove what does not earn its keep.
Land the fixes in the same branch.

## When to run

- Just finished a feature or fix and tests are green.
- About to open a PR — last sweep before review.
- User says "simplify", "tighten", "clean up", "trim", "shorter".
- After accepting an autocomplete-heavy session, before committing.

## Process

1. **Identify the diff scope.** `git diff main...HEAD` (or against the
   merge-base of the working branch) is the surface to review.
2. **Pass once for each axis below.** Note each finding with a
   file:line.
3. **Fix the findings in-place.** Do not turn this into a "future
   cleanup" list. The whole point is to ship simpler now.
4. **Re-run tests** after fixes. Verify the diff is still green.
5. **Amend or follow-up commit** depending on whether the original
   commits have already been pushed (see `git-style`).

## Axes

### Reuse

- Same-shape code already exists in the repo? Use the existing thing.
- Two near-identical functions in the diff? Collapse into one.
- A wrapper that adds nothing over the wrapped call? Inline it.

### Quality

- Comments explaining *what* the code does (vs *why*)? Delete — names
  should carry the *what*. Keep comments only for non-obvious *why*.
- Defensive checks for impossible inputs (already guaranteed by types
  or the caller)? Delete.
- Error handling for cases that cannot occur? Delete.
- Mock paths, feature flags, or backwards-compat shims that no longer
  have a live consumer? Delete.
- Dead code: removed feature whose helpers still linger. Delete.
- Variable-renamed-to-`_unused` or `// removed` placeholder? Delete
  the line.
- Logging that does not aid debugging or operations? Delete.

### Efficiency

- O(n²) where O(n) is trivial? Fix.
- Repeated work in a tight loop that could be hoisted? Hoist.
- Sync I/O on a hot path that should be async/batched? Fix.
- Allocations or copies that the language's lifetime/ownership rules
  could elide? Fix.

### Shape

- Module shallow (interface as wide as implementation)? See `tdd/`
  + `improve-codebase-architecture/` for the deepening playbook.
- Function too long because it does two things? Split, but only if
  callers gain something from the split.
- Three similar lines is fine. Three similar *blocks* is the bar
  for extracting a helper — not before.

## Anti-patterns to avoid

- Don't add abstractions "in case." If two more callers appear, *then*
  extract.
- Don't rewrite working code in a different style for taste alone.
- Don't ship a simplification that removes a check whose absence
  could surprise a future reader — keep the *why*, drop the noise.

## Validate

- All tests pass before and after.
- `git diff --check` clean.
- Diff is *smaller* than when you started — if it's larger, you
  probably refactored when you should have simplified.
