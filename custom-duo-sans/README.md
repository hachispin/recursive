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

Italic `f` uses its original plain form by default. Enable **`ss03` (Swash f)**
to use Recursive's existing proportional swash (`f.italic`). Both forms retain
their original outlines, spacing, and accent anchors.

Italic `fi` and `ffi` ligatures remain off by default with either form of `f`.
Enable **`ss13` (Italic fi/ffi ligatures)** to
use the original plain-form ligatures. These rules live in `ss13` instead of
[`liga`, which shapers normally enable automatically](https://learn.microsoft.com/en-us/typography/opentype/spec/features_ko#tag-liga).
When both `ss03` and `ss13` are enabled, standalone `f` uses the swash while
`fi`/`ffi` use the original plain-form ligatures. Neither feature enables code
ligatures, which remain under `dlig`. Roman faces retain their original behavior.

Italic faces tighten `t` followed by `e` or an accented `e` by 20 font units.
The exception includes accented `t` forms but excludes the unrelated `pi` glyph
from the source kerning class. Roman `te` spacing remains unchanged.

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

The default build creates all three families, each with eight weights from Light
(300) through ExtraBlack (1000), with a roman and italic at each weight: 48 TTFs
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

The build needs Python 3 and FontTools. It assembles the 32 mastered Sans static
fonts tracked in [`sources/ttf`](sources/ttf), so it does not need the older full
Recursive mastering toolchain or a network download. These upstream inputs are
kept separately from the custom output fonts. See [source provenance](sources/README.md).

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
