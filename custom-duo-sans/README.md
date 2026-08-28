# Recursive Duo Sans

This is a two-voice, proportional build of Recursive:

- roman: `MONO=0`, `CASL=0`, `slnt=0`, `CRSV=0` — Sans Linear
- italic: `MONO=0`, `CASL=1`, `slnt=-15`, `CRSV=1` — Sans Casual Italic

The result is one style-linked family named **Recursive Duo Sans**. Selecting
italic changes both the slant and the genre, so emphasis has a noticeably more
handwritten voice while upright text stays crisp and linear.

The italic build uses Recursive's mastered static Casual Italic sources. Its
single-storey `a` and `g` are baked into the base glyphs, rather than depending
on an application to activate the `rvrn` OpenType feature.

This build intentionally does not use Recursive Code Config. That project is
for configured monospace/code fonts; all faces here pin `MONO` to `0`.

## Build

From the repository root:

```sh
python3 custom-duo-sans/build.py
```

The default build creates eight weights from Light (300) through ExtraBlack
(1000), with a roman and italic at each weight. Install the desktop fonts from
`custom-duo-sans/dist/ttf`.

For a smaller family, pass specific weights:

```sh
python3 custom-duo-sans/build.py --weights 400 700
```

The build needs Python 3 and FontTools. It assembles the mastered Sans static
fonts already checked into this repository, so it does not need the older full
Recursive mastering toolchain.

## Why static fonts?

The source font exposes Casual and Slant as independent axes. This derivative
deliberately couples them to the normal/italic style switch. Static paired faces
express that relationship reliably in desktop applications without leaving
extra Casual, Monospace, or Cursive controls for users to coordinate.

## License

Recursive is copyright The Recursive Project Authors and is licensed under the
SIL Open Font License 1.1. The build copies `OFL.txt` into the output directory.
