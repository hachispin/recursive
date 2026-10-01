# Repository instructions

## Preserve Recursive's width behavior

Recursive Sans is designed so changing weight, Casual/Linear style, or slant does not reflow text. Treat this as a core requirement when editing `custom-duo-sans/` or rebuilding `fonts/ttf/`.

- All 36 generated faces, Light through ExtraBold, must have the same advance width for each glyph, even though this is a proportional family. Both `/` and `\` are 500 units in every face, including between digits (for example, `1/2`). The 500-unit `slash.num` alternate is retained but is not selected by `calt`. Keep these glyph widths identical across faces and do not reintroduce the numeric slash substitution.
- The slashes are narrowed by 80 units beyond the usual spacing reduction, with their strokes centered. Existing kerned pairs with exactly one slash receive 80 units of compensation so their total pair advance is preserved. Apply compensation to the union of these pairs across all source faces, including accented letters and italic `f` alternates, even when a pair's kerning is zero in one style. Repeated slashes keep shared kerning and matching run widths in both directions.
- Every pair listed in `custom-duo-sans/collision_kerning.json` must shape to the same total advance in every generated face. The build chooses one safe width across all families, weights, and slopes; do not replace it with style-specific kerning. `Q)` and `qj` are useful spot checks; `Lj` should retain upstream kerning.
- Preserve collision clearance in the heavy masters while keeping those pair widths shared. If a pair needs more room, update its measured correction and the shared target for all faces.
- Pairs without a collision, shared-width, or slash compensation exception keep their upstream GPOS kerning after the 20-unit glyph advance reduction.
- The tracked upstream static sources already have a few kerning differences outside the collision list (for example, `a/b` is 20 units wider in italic). Do not claim arbitrary strings are currently identical across all styles. Avoid introducing additional differences.

When changing font metrics or kerning, update the builder and relevant regression checks, run `python3 -m unittest discover --start-directory custom-duo-sans --verbose`, rebuild with `python3 custom-duo-sans/build.py`, and verify the generated faces in `fonts/ttf/`. Test shaped advances with HarfBuzz (`hb-shape`), since matching `hmtx` entries alone does not prove matching string widths.
