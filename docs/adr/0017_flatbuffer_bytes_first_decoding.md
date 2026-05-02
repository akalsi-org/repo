# FlatBuffer bytes-first decoding

We will use pooled FlatBuffer byte buffers as the canonical decoded
message representation for fast-path data, not heap-allocated object
graphs. Binary input verifies once and is read through generated
accessors; JSON input must parse from `bytes`/`memoryview` and write
directly into preallocated `bytearray`/builder buffers so app logic
receives the same pooled bytes representation.

This keeps the fast read path allocation-free and makes JSON a producer
of the same representation rather than a separate DOM/object model.
Python/mypyc JSON code is acceptable only when it preserves that contract:
no `dict`/`list` parse tree, no per-field Python string allocation on the
hot path, and no ownership outside the message pool. If that contract
cannot be met, the JSON parser moves to generated C SAX/trie code.

Considered but rejected as the default: a custom pooled C struct decoder.
It gives full control, but duplicates schema evolution, verification, and
zero-copy accessor machinery that FlatBuffers already provides.
