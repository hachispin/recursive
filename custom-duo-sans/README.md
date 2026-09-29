# Custom Recursive Sans families

This build creates three proportional, separately installable Recursive families:

| Family | Roman | Italic |
| --- | --- | --- |
| Recursive Duo Sans | Linear | Casual |
| Recursive Linear Sans | Linear | Linear |
| Recursive Casual Sans | Casual | Casual |

All faces use `MONO=0`. Roman faces use `slnt=0`, `CRSV=0`; italics use
`slnt=-15`, `CRSV=1`. Linear faces use `CASL=0` and Casual faces use `CASL=1`.
Each family has its own style links and names, so all three can be installed
together. In Duo Sans, italic also switches from Linear to Casual; the other
two families keep the same genre when switching to italic.

All three families share the tweaks described below. Italic faces use Recursive's
mastered static Linear or Casual Italic sources. Their single-storey `a` and `g`
are baked into the base glyphs, rather than depending on an application to
activate the `rvrn` OpenType feature.

Italic `f` uses Recursive's swash outline with a plain angled top terminal and
a slightly longer right crossbar. Enable **`ss03` (Long descender f)** for the
archived non-swash long form (`f.italic`), or **`ss14` (Original italic f)** for
the former plain form (`f.simple`). Linear and Casual italics use their matching
slanted A/B/C masters, interpolated for each static weight. All three crossbars
align with the former plain `f` at each weight.
The forms share the same advance width and measured collision pair spacing, and
support mark attachment. If both `ss03` and `ss14` are enabled, `ss03` selects
the long form. `fi` and `fj` have tighter shared pair advances in roman and
italic. The archived long f places the following `i` or `j` to retain its ink
clearance.

Italic `fi` and `ffi` ligatures remain off by default with any form of `f`.
Enable **`ss13` (Italic fi/ffi ligatures)** to
use the original plain-form ligatures. These rules live in `ss13` instead of
[`liga`, which shapers normally enable automatically](https://learn.microsoft.com/en-us/typography/opentype/spec/features_ko#tag-liga).
When both `ss03` and `ss13` are enabled, standalone `f` uses the long form while
`fi`/`ffi` use the original plain-form ligatures. Neither feature enables code
ligatures, which remain under `dlig`. Roman faces retain their original behavior.

Italic faces move `e` or an accented `e` 20 font units left after `t`, making
the pair look tighter without changing its total advance width. The exception
includes accented `t` forms but excludes the unrelated `pi` glyph from the
source kerning class. Roman `te` spacing remains unchanged.

The 20-unit spacing reduction can make some ASCII pairs collide. The builds
retain upstream GPOS kerning except where the final outlines need more room.
A few pairs previously corrected for collisions still need a shared width
because their upstream kerning differs by slope. Measured corrections for a
10-unit horizontal ink gap are in [`collision_kerning.json`](collision_kerning.json).
The build uses one safe pair width across the retained families, weights, and
slopes. Glyph outlines stay intact. Recompute the corrections after changing
outlines or weights with `python3 custom-duo-sans/measure_collision_kerning.py`
(requires Pillow and NumPy), then rebuild and run the measurement with
`--verify` to check the final faces.

All advancing glyphs are spaced 20 font units closer together than the source
fonts, including spaces and punctuation. Zero-width marks remain zero-width.
The collision exceptions account for this tighter spacing.

The ordinary `/` keeps the source's spacing reduction (580 units). Between
digits, default-on `calt` substitutes a 500-unit `slash.num` alternate with the
same stroke centered in its narrower advance. Numeric text such as `1/2` stays
compact, while text such as `/g` keeps the ordinary slash spacing.

Colons between digits are vertically centered automatically: `12:34`, `9:05`,
`12:34:56`, and numeric ratios such as `3:2`. The build includes a `calt`
(Contextual Alternates) substitution from `:` to Recursive's existing `∶` glyph,
which has the same advance width. It also handles proportional figures and the
alternate digit styles. Colons in prose, spaced colons, and `::` keep their usual
form; the underlying text remains an ordinary colon.

This follows the approach shown by [Inter's contextual alternates](https://rsms.me/inter/#features).
[`calt` is enabled by default in standard OpenType shaping](https://learn.microsoft.com/en-us/typography/opentype/spec/features_ae#tag-calt),
so the built fonts need no feature opt-in. Applications must support contextual
alternates and leave them enabled. The rule stays contextual rather than being
frozen into the base colon glyph, which would raise every colon. Code ligatures
remain in the separate, opt-in `dlig` feature.

This build intentionally does not use Recursive Code Config. That project is
for configured monospace/code fonts; all faces here pin `MONO` to `0`.

## Build

From the repository root:

```sh
python3 custom-duo-sans/build.py
```

The default build creates all three families, each with six weights from Light
(300) through ExtraBold (800), with a roman and italic at each weight: 36 TTFs
in total. Install the desktop fonts from [`fonts/ttf`](../fonts/ttf); filenames
start with `RecursiveDuoSans`, `RecursiveLinearSans`, or `RecursiveCasualSans`.

For fewer weights across all three families:

```sh
python3 custom-duo-sans/build.py --weights 400 700
```

To select families, use `--variants` with one or more of `duo`, `linear`, and
`casual`. For example, to build only the original Duo Sans family:

```sh
python3 custom-duo-sans/build.py --variants duo
```

The build needs Python 3, FontTools, and the `ttfautohint` command. It assembles
the 32 mastered Sans static fonts tracked in [`sources/ttf`](sources/ttf), so it
does not need the older full Recursive mastering toolchain or a network download.
The builder removes the source hint instructions, then runs `ttfautohint` with
composite hinting after all outline and metric edits. This also hints the custom
italic `f` and `slash.num` glyphs. The upstream inputs stay untouched. See
[source provenance](sources/README.md).

To run the font shaping regression checks (requires HarfBuzz's `hb-shape`):

```sh
python3 -m unittest discover --start-directory custom-duo-sans --verbose
```

## Why static fonts?

The source font exposes Casual and Slant as independent axes. These derivatives
choose a fixed genre for each roman and italic face. Static paired faces express
those choices reliably in desktop applications without leaving extra Casual,
Monospace, or Cursive controls for users to coordinate.

## License

Recursive is copyright The Recursive Project Authors and is licensed under the
SIL Open Font License 1.1. The build copies `OFL.txt` into the output directory.
