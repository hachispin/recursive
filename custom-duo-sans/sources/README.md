# Upstream build inputs

`ttf/` contains 32 unmodified Recursive 1.085 static fonts: Sans Linear and Sans
Casual, each with eight weights and matching roman/italic faces.

These files were preserved byte-for-byte from the repository's former
`fonts/recursive_for_googlefonts/static/` directory. Their embedded version is
`1.085`; the custom builds have their own version and family names.

The custom builder reads these fonts and writes the modified families to
[`fonts/ttf`](../../fonts/ttf). Keep these inputs tracked so a fresh checkout can
build all three families without downloading an upstream release or running the
original mastering toolchain. The unused Mono fonts and duplicate upstream
release packages are not needed by this build.

Recursive is copyright The Recursive Project Authors. These inputs are licensed
under the [SIL Open Font License 1.1](OFL.txt).
