#!/usr/bin/env python3
"""Measure ASCII pair corrections after the 20-unit spacing reduction.

Run after building the current faces. The generated fonts provide the final
outlines, including the custom italic f; source fonts provide upstream kerning.
Pillow and NumPy are only needed for this measurement, not for normal builds.
"""

from __future__ import annotations

import argparse
import json
import string
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fontTools.ttLib import TTFont

from build import (
    DEFAULT_SOURCE_DIR,
    FAMILIES,
    ITALIC_F_FOLLOWER_PLACEMENT,
    SOURCE_FILES,
    SPACING_REDUCTION,
    WEIGHTS,
    kern_lookup,
    pair_kerning,
)


HERE = Path(__file__).resolve().parent
DEFAULT_FONT_DIR = HERE.parent / "fonts" / "ttf"
ASCII = string.printable[:95]
INK_THRESHOLD = 127


def ink_rows(font: ImageFont.FreeTypeFont, character: str) -> tuple[int, np.ndarray, np.ndarray]:
    """Return each occupied row's left and right ink bounds at 1000 px/em."""
    x0, y0, x1, y1 = font.getbbox(character, anchor="ls")
    image = Image.new("L", (max(1, x1 - x0), max(1, y1 - y0)))
    ImageDraw.Draw(image).text((-x0, -y0), character, font=font, anchor="ls", fill=255)
    pixels = np.asarray(image) > INK_THRESHOLD
    occupied = pixels.any(axis=1)
    left = np.argmax(pixels, axis=1).astype(np.int32) + x0
    right = pixels.shape[1] - 1 - np.argmax(pixels[:, ::-1], axis=1) + x0
    left[~occupied] = 1_000_000
    right[~occupied] = -1_000_000
    return y0, left, right


def minimum_gap(left, right, origin: int) -> int:
    """Minimum horizontal ink clearance on a row occupied by both glyphs."""
    left_y, _, left_edge = left
    right_y, right_edge, _ = right
    start = max(left_y, right_y)
    end = min(left_y + len(left_edge), right_y + len(right_edge))
    if start >= end:
        return 1_000_000
    left_end = left_edge[start - left_y:end - left_y]
    right_start = right_edge[start - right_y:end - right_y]
    valid = (left_end > -1_000_000) & (right_start < 1_000_000)
    if not valid.any():
        return 1_000_000
    return int(np.min(origin + right_start[valid] - left_end[valid] - 1))


def remap_f(font_path: Path, glyph_name: str, output: Path) -> Path:
    """Make an alternate f addressable through cmap for outline measurement."""
    with TTFont(font_path) as font:
        for table in font["cmap"].tables:
            if table.isUnicode() and ord("f") in table.cmap:
                table.cmap[ord("f")] = glyph_name
        font.save(output)
    return output


def measure(source_dir: Path, font_dir: Path, margin: int, verify: bool = False):
    corrections = {f"{voice}-{slope}": {} for voice in ("linear", "casual")
                   for slope in ("upright", "italic")}
    failures = []
    characters = tuple(ASCII)
    with tempfile.TemporaryDirectory(prefix="recursive-kerning-measure-") as directory:
        temporary = Path(directory)
        for voice in ("linear", "casual"):
            for italic in (False, True):
                style = f"{voice}-{'italic' if italic else 'upright'}"
                for weight, weight_name in WEIGHTS.items():
                    source_path = source_dir / SOURCE_FILES[voice][weight][int(italic)]
                    built_path = font_dir / (
                        f"{FAMILIES[voice].replace(' ', '')}-{weight_name}"
                        f"{'Italic' if italic else ''}.ttf"
                    )
                    built_font = ImageFont.truetype(str(built_path), 1000)
                    masks = {c: ink_rows(built_font, c) for c in characters}
                    alternate_masks = {}
                    if italic:
                        for name in ("f.italic", "f.simple"):
                            path = remap_f(
                                built_path, name,
                                temporary / f"{voice}-{weight}-{name}.ttf",
                            )
                            alternate_masks[name] = ink_rows(ImageFont.truetype(str(path), 1000), "f")
                    with TTFont(source_path) as source, TTFont(built_path) as built:
                        source_cmap = source.getBestCmap()
                        built_cmap = built.getBestCmap()
                        lookup = kern_lookup(source)
                        built_lookup = kern_lookup(built)
                        for left in characters:
                            left_forms = ("f", "f.italic", "f.simple") if italic and left == "f" else (left,)
                            base_advance = built["hmtx"][built_cmap[ord(left)]][0]
                            for right in characters:
                                pair = left + right
                                source_kern = pair_kerning(
                                    lookup, source_cmap[ord(left)], source_cmap[ord(right)]
                                )
                                right_forms = ("f", "f.italic", "f.simple") if italic and right == "f" else (right,)
                                needed = 0
                                for left_form in left_forms:
                                    left_ink = alternate_masks.get(left_form, masks[left])
                                    placement = ITALIC_F_FOLLOWER_PLACEMENT.get(left_form, {}).get(pair, 0)
                                    if italic and pair == "te":
                                        placement -= SPACING_REDUCTION
                                    for right_form in right_forms:
                                        right_ink = alternate_masks.get(right_form, masks[right])
                                        gap = minimum_gap(
                                            left_ink, right_ink,
                                            base_advance + source_kern + placement,
                                        )
                                        needed = max(needed, margin - gap)
                                        if verify:
                                            left_glyph = left_form if left_form in alternate_masks else built_cmap[ord(left)]
                                            right_glyph = right_form if right_form in alternate_masks else built_cmap[ord(right)]
                                            actual_kern = pair_kerning(
                                                built_lookup, left_glyph, right_glyph
                                            )
                                            actual_gap = minimum_gap(
                                                left_ink, right_ink,
                                                base_advance + actual_kern + placement,
                                            )
                                            if actual_gap < margin:
                                                failures.append((built_path.name, pair, left_form, right_form, actual_gap))
                                if needed > 0:
                                    corrections[style][pair] = max(
                                        needed, corrections[style].get(pair, 0)
                                    )
    return corrections, failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--font-dir", type=Path, default=DEFAULT_FONT_DIR)
    parser.add_argument("--margin", type=int, default=10)
    parser.add_argument("--output", type=Path, default=HERE / "collision_kerning.json")
    parser.add_argument("--verify", action="store_true", help="check the built faces without writing corrections")
    args = parser.parse_args()
    if args.margin < 0:
        parser.error("margin must be nonnegative")
    corrections, failures = measure(args.source_dir, args.font_dir, args.margin, args.verify)
    if args.verify:
        if failures:
            for failure in failures[:20]:
                print("insufficient gap:", *failure)
            raise SystemExit(f"{len(failures)} shaped pair forms have less than {args.margin} units of clearance")
        print(f"Verified a {args.margin}-unit raster gap for all ASCII pair forms in the retained faces")
        return
    args.output.write_text(json.dumps(corrections, indent=2, sort_keys=True) + "\n")
    print(f"Measured {sum(map(len, corrections.values()))} style-pair corrections for a {args.margin}-unit gap")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
