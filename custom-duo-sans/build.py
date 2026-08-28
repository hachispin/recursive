#!/usr/bin/env python3
"""Build a proportional Recursive family with Linear romans and Casual italics."""

from __future__ import annotations

import argparse
import math
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_SOURCE_DIR = (
    REPO_ROOT
    / "fonts"
    / "recursive_for_googlefonts"
    / "static"
)
DEFAULT_OUTPUT = HERE / "dist"
FAMILY = "Recursive Duo Sans"
BUILD_VERSION = "1.086"
WEIGHTS = {
    300: "Light",
    400: "Regular",
    500: "Medium",
    600: "SemiBold",
    700: "Bold",
    800: "ExtraBold",
    900: "Black",
    1000: "ExtraBlack",
}
SOURCE_FILES = {
    300: ("RecursiveSansLnrSt-Light.ttf", "RecursiveSansCslSt-LtItalic.ttf"),
    400: ("RecursiveSansLnrSt-Regular.ttf", "RecursiveSansCslSt-Italic.ttf"),
    500: ("RecursiveSansLnrSt-Med.ttf", "RecursiveSansCslSt-MedItalic.ttf"),
    600: ("RecursiveSansLnrSt-SemiBold.ttf", "RecursiveSansCslSt-SmBdItalic.ttf"),
    700: ("RecursiveSansLnrSt-Bold.ttf", "RecursiveSansCslSt-BdItalic.ttf"),
    800: ("RecursiveSansLnrSt-ExtraBold.ttf", "RecursiveSansCslSt-XBdItalic.ttf"),
    900: ("RecursiveSansLnrSt-Black.ttf", "RecursiveSansCslSt-BlkItalic.ttf"),
    1000: ("RecursiveSansLnrSt-XBlk.ttf", "RecursiveSansCslSt-XBlkItalic.ttf"),
}


def set_name(font: TTFont, name_id: int, value: str) -> None:
    """Replace a name in English Windows and Macintosh records."""
    table = font["name"]
    table.names = [record for record in table.names if record.nameID != name_id]
    table.setName(value, name_id, 3, 1, 0x409)
    table.setName(value, name_id, 1, 0, 0)


def style_names(weight: int, italic: bool) -> dict[str, str]:
    weight_name = WEIGHTS[weight]
    typographic_style = (
        "Italic"
        if weight == 400 and italic
        else "Regular"
        if weight == 400
        else f"{weight_name} Italic"
        if italic
        else weight_name
    )

    # The four classic RIBBI faces share one legacy family. Other weights get
    # their own legacy family so older Windows applications still link italics.
    if weight in (400, 700):
        legacy_family = FAMILY
        legacy_style = (
            "Bold Italic"
            if weight == 700 and italic
            else "Bold"
            if weight == 700
            else "Italic"
            if italic
            else "Regular"
        )
    else:
        legacy_family = f"{FAMILY} {weight_name}"
        legacy_style = "Italic" if italic else "Regular"

    full_name = FAMILY if typographic_style == "Regular" else f"{FAMILY} {typographic_style}"
    postscript_name = f"RecursiveDuoSans-{typographic_style.replace(' ', '')}"
    return {
        "legacy_family": legacy_family,
        "legacy_style": legacy_style,
        "typographic_style": typographic_style,
        "full_name": full_name,
        "postscript_name": postscript_name,
    }


def update_metadata(font: TTFont, weight: int, italic: bool) -> None:
    names = style_names(weight, italic)

    set_name(font, 1, names["legacy_family"])
    set_name(font, 2, names["legacy_style"])
    set_name(font, 3, f"{BUILD_VERSION};RecursiveDuoSans;{names['postscript_name']}")
    set_name(font, 4, names["full_name"])
    set_name(font, 5, f"Version {BUILD_VERSION}; Recursive Duo Sans build 2")
    set_name(font, 6, names["postscript_name"])
    set_name(font, 16, FAMILY)
    set_name(font, 17, names["typographic_style"])
    set_name(font, 18, names["full_name"])
    set_name(font, 21, FAMILY)
    set_name(font, 22, names["typographic_style"])

    os2 = font["OS/2"]
    os2.usWeightClass = weight
    os2.fsSelection &= ~((1 << 0) | (1 << 5) | (1 << 6) | (1 << 9))
    if italic:
        os2.fsSelection |= 1 << 0
    if weight == 700:
        os2.fsSelection |= 1 << 5
    if weight == 400 and not italic:
        os2.fsSelection |= 1 << 6

    cmap = font.getBestCmap()
    lowercase_widths = [
        font["hmtx"].metrics[cmap[codepoint]][0]
        for codepoint in range(ord("a"), ord("z") + 1)
        if codepoint in cmap
    ]
    if lowercase_widths:
        os2.xAvgCharWidth = round(sum(lowercase_widths) / len(lowercase_widths))

    font["head"].fontRevision = float(BUILD_VERSION)
    font["head"].macStyle = (1 if weight == 700 else 0) | (2 if italic else 0)
    font["post"].italicAngle = -15.0 if italic else 0.0
    font["post"].isFixedPitch = 0
    font["hhea"].caretSlopeRise = 1000 if italic else 1
    font["hhea"].caretSlopeRun = round(math.tan(math.radians(15)) * 1000) if italic else 0
    font["hhea"].caretOffset = 0

    # A signature over the upstream font is no longer valid after renaming.
    if "DSIG" in font:
        del font["DSIG"]


def build_face(source_dir: Path, output: Path, weight: int, italic: bool) -> tuple[Path, Path]:
    source_path = source_dir / SOURCE_FILES[weight][1 if italic else 0]
    font = TTFont(source_path, recalcTimestamp=False, lazy=False)
    update_metadata(font, weight, italic)
    suffix = "Italic" if italic else ""
    filename = f"RecursiveDuoSans-{WEIGHTS[weight]}{suffix}.ttf"
    ttf_path = output / "ttf" / filename
    font.save(ttf_path, reorderTables=False)
    font.close()

    return ttf_path, source_path


def validate_face(path: Path, source_path: Path, weight: int, italic: bool) -> None:
    font = TTFont(path)
    source = TTFont(source_path)
    try:
        expected_style = style_names(weight, italic)["typographic_style"]
        assert "fvar" not in font, f"{path.name}: variation axes were not fully pinned"
        assert font["name"].getDebugName(16) == FAMILY
        assert font["name"].getDebugName(17) == expected_style
        assert font["name"].getDebugName(5).startswith(f"Version {BUILD_VERSION}")
        assert font["OS/2"].usWeightClass == weight
        assert bool(font["OS/2"].fsSelection & 1) == italic
        assert bool(font["head"].macStyle & 2) == italic
        assert font["post"].isFixedPitch == 0
        if italic:
            # The cursive a/g must live in the base glyphs. This deliberately
            # avoids relying on the rvrn feature, which some desktop apps skip.
            for glyph_name in ("a", "g"):
                assert font["glyf"][glyph_name].compile(font["glyf"]) == source[
                    "glyf"
                ][glyph_name].compile(source["glyf"])
    finally:
        font.close()
        source.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--weights", type=int, nargs="+", default=list(WEIGHTS))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    unknown_weights = sorted(set(args.weights) - set(WEIGHTS))
    if unknown_weights:
        raise SystemExit(f"Unsupported weights: {', '.join(map(str, unknown_weights))}")
    missing_sources = [
        args.source_dir / filename
        for weight in args.weights
        for filename in SOURCE_FILES[weight]
        if not (args.source_dir / filename).is_file()
    ]
    if missing_sources:
        raise SystemExit(f"Static source not found: {missing_sources[0]}")

    output = args.output.resolve()
    (output / "ttf").mkdir(parents=True, exist_ok=True)

    built = []
    for weight in args.weights:
        for italic in (False, True):
            ttf, source_path = build_face(args.source_dir, output, weight, italic)
            validate_face(ttf, source_path, weight, italic)
            built.append(ttf)
            print(f"built {ttf.relative_to(output)}")

    shutil.copyfile(REPO_ROOT / "OFL.txt", output / "OFL.txt")
    print(f"\n{len(built)} TTF faces written to {output}")


if __name__ == "__main__":
    main()
