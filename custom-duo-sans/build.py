#!/usr/bin/env python3
"""Build proportional Recursive Duo, Linear, and Casual Sans families."""

from __future__ import annotations

import argparse
from copy import deepcopy
from functools import lru_cache
from itertools import product
import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from fontTools.otlLib.builder import (
    ChainContextSubstBuilder,
    ChainContextualRule,
    SingleSubstBuilder,
    buildPairPosGlyphsSubtable,
    buildValue,
)
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.pointPen import PointToSegmentPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables
from fontTools.ufoLib.glifLib import readGlyphFromString
from fontTools.varLib.featureVars import buildFeatureRecord, sortFeatureList


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
DEFAULT_SOURCE_DIR = HERE / "sources" / "ttf"
DEFAULT_OUTPUT = REPO_ROOT / "fonts"
FAMILIES = {
    "duo": "Recursive Duo Sans",
    "linear": "Recursive Linear Sans",
    "casual": "Recursive Casual Sans",
}
BUILD_VERSION = "1.101"
SPACING_REDUCTION = 20
SLASH_ADVANCE_REDUCTION = 80
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
    "linear": {
        300: ("RecursiveSansLnrSt-Light.ttf", "RecursiveSansLnrSt-LightItalic.ttf"),
        400: ("RecursiveSansLnrSt-Regular.ttf", "RecursiveSansLnrSt-Italic.ttf"),
        500: ("RecursiveSansLnrSt-Med.ttf", "RecursiveSansLnrSt-MedItalic.ttf"),
        600: ("RecursiveSansLnrSt-SemiBold.ttf", "RecursiveSansLnrSt-SmBdItalic.ttf"),
        700: ("RecursiveSansLnrSt-Bold.ttf", "RecursiveSansLnrSt-BoldItalic.ttf"),
        800: ("RecursiveSansLnrSt-ExtraBold.ttf", "RecursiveSansLnrSt-ExBdItalic.ttf"),
        900: ("RecursiveSansLnrSt-Black.ttf", "RecursiveSansLnrSt-BlackItalic.ttf"),
        1000: ("RecursiveSansLnrSt-XBlk.ttf", "RecursiveSansLnrSt-XBlkItalic.ttf"),
    },
    "casual": {
        300: ("RecursiveSansCslSt-Light.ttf", "RecursiveSansCslSt-LtItalic.ttf"),
        400: ("RecursiveSansCslSt-Regular.ttf", "RecursiveSansCslSt-Italic.ttf"),
        500: ("RecursiveSansCslSt-Med.ttf", "RecursiveSansCslSt-MedItalic.ttf"),
        600: ("RecursiveSansCslSt-SemiBd.ttf", "RecursiveSansCslSt-SmBdItalic.ttf"),
        700: ("RecursiveSansCslSt-Bold.ttf", "RecursiveSansCslSt-BdItalic.ttf"),
        800: ("RecursiveSansCslSt-ExtraBd.ttf", "RecursiveSansCslSt-XBdItalic.ttf"),
        900: ("RecursiveSansCslSt-Black.ttf", "RecursiveSansCslSt-BlkItalic.ttf"),
        1000: ("RecursiveSansCslSt-XBlk.ttf", "RecursiveSansCslSt-XBlkItalic.ttf"),
    },
}
SOURCE_FILES["duo"] = {
    weight: (SOURCE_FILES["linear"][weight][0], SOURCE_FILES["casual"][weight][1])
    for weight in WEIGHTS
}

# Measured ASCII collisions in the upstream heavy masters. The largest safe
# resulting pair width is shared by every genre, slope, and weight.
COLLISION_KERNING = json.loads((HERE / "collision_kerning.json").read_text())


def add_numeric_punctuation(font: TTFont) -> None:
    """Select centered colons and narrow slashes between lining digits."""
    cmap = font.getBestCmap()
    colon = cmap[ord(":")]
    ratio = cmap[ord("∶")]
    slash = cmap[ord("/")]
    digit_names = {cmap[codepoint] for codepoint in range(ord("0"), ord("9") + 1)}
    # Include proportional, slashed/dotted-zero and stylistic digit alternates.
    # Superscripts, subscripts and fraction figures need their own punctuation.
    digits = {name for name in font.getGlyphOrder() if name.split(".")[0] in digit_names}
    gsub = font["GSUB"].table
    lookups = gsub.LookupList.Lookup

    replacement = SingleSubstBuilder(font, None)
    replacement.mapping[colon] = ratio
    replacement.mapping[slash] = "slash.num"
    replacement.lookup_index = len(lookups)
    context = ChainContextSubstBuilder(font, None)
    # Equivalent feature syntax: sub @digits colon' @digits by uni2236;
    context.rules.append(ChainContextualRule([digits], [{colon}], [digits], [replacement]))
    context.rules.append(ChainContextualRule([digits], [{slash}], [digits], [replacement]))
    context_index = len(lookups) + 1
    lookups.extend([replacement.build(), context.build()])
    gsub.LookupList.LookupCount = len(lookups)

    # Append lookups so existing substitutions (including dlig) retain their
    # indices and digit alternates have already been selected when calt runs.
    records = gsub.FeatureList.FeatureRecord
    calt_indices = set()
    for index, record in enumerate(records):
        if record.FeatureTag == "calt":
            record.Feature.LookupListIndex.append(context_index)
            record.Feature.LookupCount = len(record.Feature.LookupListIndex)
            calt_indices.add(index)

    new_index = None
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        languages = [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]
        for language in languages:
            if language is None or calt_indices.intersection(language.FeatureIndex):
                continue
            if new_index is None:
                new_index = len(records)
                records.append(buildFeatureRecord("calt", [context_index]))
            language.FeatureIndex.append(new_index)
            language.FeatureCount = len(language.FeatureIndex)
    gsub.FeatureList.FeatureCount = len(records)
    # OpenType requires sorted feature tags; remap all language references too.
    sortFeatureList(gsub)


ARCHIVED_F_LAYERS = {
    "linear": ("glyphs.45degrees", "glyphs.45degrees", "glyphs.background"),
    "casual": ("glyphs.background", "glyphs.background", "glyphs.background"),
}
ARCHIVED_F_MASTERS = ("A", "B", "C")
ARCHIVED_F_LOCATIONS = (250, 800, 900)
# User-facing weights mapped to the source designspace's interpolation values.
ARCHIVED_F_WEIGHT_MAP = {
    300: 250, 400: 450, 500: 533, 600: 616,
    700: 700, 800: 800, 900: 850, 1000: 900,
}
# The source swash f ends its upper stroke in a tight curl. Use a plain,
# angled terminal based on the original italic f instead. Each tuple holds
# the inner shoulder, outer tip, and two controls returning to the arch.
SWASH_F_TOP = {
    "linear": {
        250: ((500, 706), (531, 743), (531, 750), (491, 760)),
        800: ((488, 646), (535, 747), (535, 755), (485, 770)),
        900: ((463, 564), (507, 751), (507, 757), (485, 770)),
    },
    "casual": {
        250: ((502, 673), (519, 744), (518, 755), (439, 760)),
        800: ((500, 644), (535, 744), (535, 760), (463, 770)),
        900: ((449, 563), (479, 740), (480, 754), (436, 770)),
    },
}
SWASH_F_BAR_EXTENSION = 16

# The shared fi/fj advances are tight enough for the default swash and roman f.
# Keep the archived long f's ink clearance with placement on its follower;
# the plain ss14 f needs a smaller fi adjustment in the heaviest Casual face.
ITALIC_F_FOLLOWER_PLACEMENT = {
    "f.italic": {"fi": 80, "fj": 35},
    "f.simple": {"fi": 20},
}


@lru_cache(maxsize=None)
def f_master(voice: str, master: int, swash: bool) -> list:
    """Read a slanted swash or archived long-f UFO master."""
    index = ARCHIVED_F_LOCATIONS.index(master)
    letter = ARCHIVED_F_MASTERS[index]
    style = voice.title()
    layer = "glyphs" if swash else ARCHIVED_F_LAYERS[voice][index]
    path = (
        REPO_ROOT / "src" / "ufo" / "sans"
        / f"Recursive Sans-{style} {letter} Slanted.ufo" / layer / "f.italic.glif"
    )
    pen = RecordingPen()
    readGlyphFromString(path.read_text(), pointPen=PointToSegmentPen(pen))
    return pen.value


def custom_swash_f_master(voice: str, master: int) -> list:
    """Give the swash f a plain upper terminal and a slightly longer bar."""
    outline = f_master(voice, master, True)
    expected_top = [
        "curveTo", "curveTo", "lineTo", "curveTo",
        "curveTo", "lineTo", "curveTo", "curveTo",
    ]
    if (
        len(outline) != 29
        or [command for command, _ in outline[8:16]] != expected_top
    ):
        raise ValueError("Unexpected swash f top contour")
    shoulder, tip, outer_control, arch_control = SWASH_F_TOP[voice][master]
    arch_peak = outline[15][1][-1]
    outline = (
        outline[:9]
        + [("lineTo", (shoulder,)), ("lineTo", (tip,))]
        + [("curveTo", (outer_control, arch_control, arch_peak))]
        + outline[16:]
    )
    if [command for command, _ in outline[-4:-1]] != ["lineTo", "curveTo", "curveTo"]:
        raise ValueError("Unexpected swash f bar contour")
    # Move the three commands that form the right end, leaving the left end
    # and the bar's vertical alignment intact.
    for index in range(len(outline) - 4, len(outline) - 1):
        command, points = outline[index]
        outline[index] = (
            command,
            tuple((x + SWASH_F_BAR_EXTENSION, y) for x, y in points),
        )
    return outline


def plain_f_bar_center(font: TTFont) -> float:
    """Locate the two horizontal edges of the source italic f crossbar."""
    glyph = font["glyf"]["f"]
    edges = set()
    start = 0
    for end in glyph.endPtsOfContours:
        for index in range(start, end + 1):
            next_index = start if index == end else index + 1
            x1, y1 = glyph.coordinates[index]
            x2, y2 = glyph.coordinates[next_index]
            if (
                glyph.flags[index] & 1 and glyph.flags[next_index] & 1
                and y1 == y2 and 250 <= y1 <= 550 and abs(x2 - x1) >= 25
            ):
                edges.add(y1)
        start = end + 1
    if len(edges) != 2:
        raise ValueError(f"Expected two plain f bar edges, found {sorted(edges)}")
    return sum(edges) / 2


def aligned_f_glyph(voice: str, weight: int, swash: bool, target_bar_center: float):
    """Interpolate the f masters and align their separate bar contour."""
    location = ARCHIVED_F_WEIGHT_MAP[weight]
    lower, upper = (
        (250, 800) if location <= 800 else (800, 900)
    )
    fraction = (location - lower) / (upper - lower)
    if swash:
        left = custom_swash_f_master(voice, lower)
        right = custom_swash_f_master(voice, upper)
    else:
        left = f_master(voice, lower, False)
        right = f_master(voice, upper, False)
    if len(left) != len(right):
        raise ValueError("Italic f masters have incompatible outlines")

    interpolated = []
    for (command, first), (other_command, second) in zip(left, right):
        if command != other_command or len(first) != len(second):
            raise ValueError("Italic f masters have incompatible contours")
        points = tuple(
            tuple(round(a + (b - a) * fraction) for a, b in zip(p, q))
            for p, q in zip(first, second)
        )
        interpolated.append((command, points))

    # Both source forms have a separate bar contour. The swash puts it second.
    bar_contour = 1 if swash else 0
    bar_points = []
    contour = 0
    for command, points in interpolated:
        if contour == bar_contour:
            bar_points.extend(points)
        if command == "closePath":
            contour += 1
    if contour != 2 or not bar_points:
        raise ValueError("Expected separate stem and bar contours for italic f")
    bar_center = (min(y for _, y in bar_points) + max(y for _, y in bar_points)) / 2
    bar_shift = round(target_bar_center - bar_center)

    pen = TTGlyphPen(None)
    quadratic = Cu2QuPen(pen, max_err=1, reverse_direction=True)
    contour = 0
    for command, points in interpolated:
        if contour == bar_contour:
            points = tuple((x, y + bar_shift) for x, y in points)
        getattr(quadratic, command)(*points)
        if command == "closePath":
            contour += 1
    return pen.glyph()


def configure_italic_f_outlines(font: TTFont, voice: str, weight: int) -> None:
    """Make swash f the default and retain the long and plain forms."""
    target_bar_center = plain_f_bar_center(font)
    glyf = font["glyf"]
    glyf["f.simple"] = deepcopy(glyf["f"])
    for name, swash in (("f", True), ("f.italic", False)):
        glyf[name] = aligned_f_glyph(voice, weight, swash, target_bar_center)
        glyf[name].recalcBounds(glyf)
        advance, _ = font["hmtx"][name]
        font["hmtx"][name] = (advance, glyf[name].xMin)

    # f.simple was a component of f and had no independent mark anchors.
    # Give it the plain f's anchors, then exchange the swash/long-f anchors.
    order = font.getReverseGlyphMap()
    for lookup in font["GPOS"].table.LookupList.Lookup:
        if lookup.LookupType != 4:
            continue
        for subtable in lookup.SubTable:
            names = subtable.BaseCoverage.glyphs
            if "f" not in names or "f.simple" in names:
                continue
            records = dict(zip(names, subtable.BaseArray.BaseRecord))
            plain_record = deepcopy(records["f"])
            records["f.simple"] = plain_record
            if "f.italic" in records:
                records["f"] = deepcopy(records["f.italic"])
                records["f.italic"] = deepcopy(plain_record)
            subtable.BaseCoverage.glyphs = sorted(records, key=order.__getitem__)
            subtable.BaseArray.BaseRecord = [records[name] for name in subtable.BaseCoverage.glyphs]
            subtable.BaseArray.BaseCount = len(records)


def configure_italic_f(font: TTFont) -> None:
    """Expose the long f with ss03 and original plain f with ss14."""
    gsub = font["GSUB"].table
    if any(r.FeatureTag in ("ss13", "ss14") for r in gsub.FeatureList.FeatureRecord):
        raise ValueError("The italic source already uses ss13 or ss14")
    params = otTables.FeatureParamsStylisticSet()
    params.Version = 0
    params.UINameID = font["name"].addName("Italic fi/ffi ligatures")
    ligature_indices = set()
    long_f_indices = set()
    for feature_index, record in enumerate(gsub.FeatureList.FeatureRecord):
        if record.FeatureTag == "ss03":
            long_f_indices.add(feature_index)
            set_name(font, record.Feature.FeatureParams.UINameID, "Long descender f")
            for index in record.Feature.LookupListIndex:
                for subtable in gsub.LookupList.Lookup[index].SubTable:
                    # The former swash glyph slot now holds the long f.
                    for name in ("f", "f.mono", "f.simple"):
                        subtable.mapping[name] = "f.italic"
        elif record.FeatureTag == "liga":
            # liga is normally enabled by shapers; ss13 is explicitly opt-in.
            record.FeatureTag = "ss13"
            record.Feature.FeatureParams = deepcopy(params)
            ligature_indices.update(record.Feature.LookupListIndex)

    # Allow explicitly requested ligatures with the plain and alternate forms.
    # Keep the source's longer-first rule order so ffi takes priority over fi.
    f_forms = ("f", "f.italic", "f.simple")
    for index in ligature_indices:
        for subtable in gsub.LookupList.Lookup[index].SubTable:
            original_rules = subtable.ligatures["f"]
            for first in f_forms:
                rules = []
                for original in original_rules:
                    choices = [f_forms if name == "f" else (name,) for name in original.Component]
                    for components in product(*choices):
                        rule = deepcopy(original)
                        rule.Component = list(components)
                        rules.append(rule)
                subtable.ligatures[first] = rules

    lookup_index = len(gsub.LookupList.Lookup)
    replacement = SingleSubstBuilder(font, None)
    replacement.mapping["f"] = "f.simple"
    gsub.LookupList.Lookup.append(replacement.build())
    gsub.LookupList.LookupCount += 1
    original_index = len(gsub.FeatureList.FeatureRecord)
    original_feature = buildFeatureRecord("ss14", [lookup_index])
    original_feature.Feature.FeatureParams = deepcopy(params)
    original_feature.Feature.FeatureParams.UINameID = font["name"].addName("Original italic f")
    gsub.FeatureList.FeatureRecord.append(original_feature)
    gsub.FeatureList.FeatureCount += 1
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        languages = [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]
        for language in languages:
            if language is not None and long_f_indices.intersection(language.FeatureIndex):
                language.FeatureIndex.append(original_index)
                language.FeatureCount = len(language.FeatureIndex)
    sortFeatureList(gsub)


def add_italic_te_kerning(font: TTFont) -> None:
    """Shift italic e toward t without changing their combined advance width."""
    lookup = kern_lookup(font)
    class_subtables = []
    for subtable in lookup.SubTable:
        if subtable.Format != 2 or "t" not in subtable.Coverage.glyphs:
            continue
        left_class = subtable.ClassDef1.classDefs.get("t", 0)
        right_class = subtable.ClassDef2.classDefs.get("e", 0)
        value = subtable.Class1Record[left_class].Class2Record[right_class].Value1
        if value is None or (getattr(value, "XAdvance", 0) or 0) != 0:
            raise ValueError("The italic t-e class pair is no longer unkerned")
        class_subtables.append((subtable, left_class, right_class))
    if len(class_subtables) != 1:
        raise ValueError("Expected exactly one italic t-e class pair")

    subtable, left_class, right_class = class_subtables[0]
    glyph_order = font.getGlyphOrder()
    left_glyphs = {
        name
        for name in glyph_order
        if subtable.ClassDef1.classDefs.get(name, 0) == left_class and name != "pi"
    }
    right_glyphs = {
        name
        for name in glyph_order
        if subtable.ClassDef2.classDefs.get(name, 0) == right_class
    }
    adjustment = buildValue({"XPlacement": -20})
    pairs = {
        (left, right): (None, adjustment)
        for left in left_glyphs
        for right in right_glyphs
    }
    append_kern_pair_lookup(font, pairs)


def kern_lookup(font: TTFont):
    """Find the original advance kerning lookup, ahead of added placement lookups."""
    gpos = font["GPOS"].table
    kern_indices = {
        record.Feature.LookupListIndex[0]
        for record in gpos.FeatureList.FeatureRecord
        if record.FeatureTag == "kern"
    }
    if len(kern_indices) != 1:
        raise ValueError("Expected one original kerning lookup")
    return gpos.LookupList.Lookup[kern_indices.pop()]


def append_kern_pair_lookup(font: TTFont, pairs: dict) -> None:
    """Apply second-glyph placement separately so adjacent advance pairs overlap."""
    gpos = font["GPOS"].table
    lookup = otTables.Lookup()
    lookup.LookupType = 2
    lookup.LookupFlag = 0
    lookup.SubTable = [buildPairPosGlyphsSubtable(pairs, font.getReverseGlyphMap())]
    lookup.SubTableCount = 1
    index = len(gpos.LookupList.Lookup)
    gpos.LookupList.Lookup.append(lookup)
    gpos.LookupList.LookupCount += 1
    for record in gpos.FeatureList.FeatureRecord:
        if record.FeatureTag == "kern":
            record.Feature.LookupListIndex.append(index)
            record.Feature.LookupCount += 1


def pair_kerning(lookup, left: str, right: str) -> int:
    for subtable in lookup.SubTable:
        if subtable.Format == 1 and left in subtable.Coverage.glyphs:
            pair_set = subtable.PairSet[subtable.Coverage.glyphs.index(left)]
            record = next((r for r in pair_set.PairValueRecord if r.SecondGlyph == right), None)
            if record is not None:
                return (getattr(record.Value1, "XAdvance", 0) or 0) if record.Value1 else 0
        elif subtable.Format == 2 and left in subtable.Coverage.glyphs:
            left_class = subtable.ClassDef1.classDefs.get(left, 0)
            right_class = subtable.ClassDef2.classDefs.get(right, 0)
            value = subtable.Class1Record[left_class].Class2Record[right_class].Value1
            return (getattr(value, "XAdvance", 0) or 0) if value else 0
    return 0


@lru_cache(maxsize=None)
def collision_targets(source_dir: Path) -> dict[str, int]:
    """Choose the largest safe kerning value across all source styles and weights."""
    all_pairs = set().union(*(set(corrections) for corrections in COLLISION_KERNING.values()))
    targets = {}
    for voice in ("linear", "casual"):
        for italic in (False, True):
            style = "italic" if italic else "upright"
            corrections = COLLISION_KERNING[f"{voice}-{style}"]
            for weight in WEIGHTS:
                source = source_dir / SOURCE_FILES[voice][weight][int(italic)]
                with TTFont(source) as font:
                    lookup = kern_lookup(font)
                    cmap = font.getBestCmap()
                    for pair in all_pairs:
                        left, right = (cmap[ord(character)] for character in pair)
                        safe = pair_kerning(lookup, left, right) + corrections.get(pair, 0)
                        targets[pair] = max(targets.get(pair, safe), safe)
    return targets


def add_collision_kerning(font: TTFont, source_dir: Path = DEFAULT_SOURCE_DIR) -> None:
    """Give collision pairs one safe width across all styles and weights."""
    lookup = kern_lookup(font)
    cmap = font.getBestCmap()
    pairs = {}
    placements = {}
    italic_f_forms = ("f.simple", "f.italic") if font["OS/2"].fsSelection & 1 else ()
    for pair, target in collision_targets(source_dir).items():
        left, right = (cmap[ord(character)] for character in pair)
        # The reduced glyph advance would remove part of this safety gap.
        value = (buildValue({"XAdvance": target + SPACING_REDUCTION}), None)
        # The italic alternates share the default f's pair advance.
        left_forms = (left, *italic_f_forms) if left == "f" else (left,)
        right_forms = (right, *italic_f_forms) if right == "f" else (right,)
        for left_form in left_forms:
            for right_form in right_forms:
                pairs[(left_form, right_form)] = value
                placement = ITALIC_F_FOLLOWER_PLACEMENT.get(left_form, {}).get(pair)
                if placement is not None:
                    placements[(left_form, right_form)] = (
                        None,
                        buildValue({"XPlacement": placement}),
                    )
    lookup.SubTable.insert(0, buildPairPosGlyphsSubtable(pairs, font.getReverseGlyphMap()))
    lookup.SubTableCount = len(lookup.SubTable)
    if placements:
        append_kern_pair_lookup(font, placements)


def reduce_spacing(font: TTFont) -> None:
    """Tighten positive glyph advances uniformly without moving their outlines."""
    metrics = font["hmtx"].metrics
    for name, (advance, left_bearing) in metrics.items():
        if advance:
            if advance <= SPACING_REDUCTION:
                raise ValueError(f"{name} is too narrow for the spacing reduction")
            metrics[name] = (advance - SPACING_REDUCTION, left_bearing)
    font["hhea"].recalc(font)


def add_narrow_numeric_slash(font: TTFont) -> None:
    """Add a narrow alternate without changing ordinary slash spacing."""
    glyf = font["glyf"]
    metrics = font["hmtx"].metrics
    slash = deepcopy(glyf["slash"])
    shift = SLASH_ADVANCE_REDUCTION // 2
    for index, (x, y) in enumerate(slash.coordinates):
        slash.coordinates[index] = (x - shift, y)
    slash.recalcBounds(glyf)
    width, _ = metrics["slash"]
    glyf.glyphs["slash.num"] = slash
    metrics["slash.num"] = (width - SLASH_ADVANCE_REDUCTION, slash.xMin)
    font.setGlyphOrder([*font.getGlyphOrder(), "slash.num"])
    font["maxp"].numGlyphs = len(font.getGlyphOrder())
    font["hhea"].recalc(font)


def autohint_face(raw_path: Path, hinted_path: Path) -> None:
    """Replace inherited hints after editing outlines and metrics."""
    binary = shutil.which("ttfautohint")
    if binary is None:
        raise RuntimeError("ttfautohint is required to build the static TTFs")
    dehinted = raw_path.with_name("dehinted.ttf")
    clean_path = raw_path.with_name("clean.ttf")
    subprocess.run([binary, "--dehint", "--no-info", str(raw_path), str(dehinted)], check=True)

    # The mastered inputs contain ttfautohint's unused helper glyph. A second
    # hinting pass rejects fonts that still contain it, even after --dehint.
    with TTFont(dehinted, lazy=False) as clean:
        # Layout tables refer to glyph IDs. Decompile them before removing the
        # helper so FontTools rewrites those references for the new glyph order.
        clean.ensureDecompiled()
        helper = ".ttfautohint"
        glyf = clean["glyf"]
        hmtx = clean["hmtx"]
        if helper in clean.getGlyphOrder():
            referenced = helper in clean.getBestCmap().values()
            for name in clean.getGlyphOrder():
                if name == helper:
                    continue
                glyph = glyf[name]
                if glyph.isComposite() and any(c.glyphName == helper for c in glyph.components):
                    referenced = True
                    break
            if referenced:
                raise ValueError("ttfautohint helper glyph is referenced")
            del glyf.glyphs[helper]
            del hmtx.metrics[helper]
            clean.setGlyphOrder([name for name in clean.getGlyphOrder() if name != helper])
            clean["maxp"].numGlyphs = len(clean.getGlyphOrder())
        clean.save(clean_path)

    subprocess.run([binary, "--composites", str(clean_path), str(hinted_path)], check=True)


def set_name(font: TTFont, name_id: int, value: str) -> None:
    """Replace a name in English Windows and Macintosh records."""
    table = font["name"]
    table.names = [record for record in table.names if record.nameID != name_id]
    table.setName(value, name_id, 3, 1, 0x409)
    table.setName(value, name_id, 1, 0, 0)


def style_names(weight: int, italic: bool, variant: str = "duo") -> dict[str, str]:
    family = FAMILIES[variant]
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
        legacy_family = family
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
        legacy_family = f"{family} {weight_name}"
        legacy_style = "Italic" if italic else "Regular"

    full_name = family if typographic_style == "Regular" else f"{family} {typographic_style}"
    postscript_name = f"{family.replace(' ', '')}-{typographic_style.replace(' ', '')}"
    return {
        "legacy_family": legacy_family,
        "legacy_style": legacy_style,
        "typographic_style": typographic_style,
        "full_name": full_name,
        "postscript_name": postscript_name,
    }


def update_metadata(font: TTFont, weight: int, italic: bool, variant: str = "duo") -> None:
    family = FAMILIES[variant]
    names = style_names(weight, italic, variant)

    set_name(font, 1, names["legacy_family"])
    set_name(font, 2, names["legacy_style"])
    set_name(font, 3, f"{BUILD_VERSION};{names['postscript_name']}")
    set_name(font, 4, names["full_name"])
    set_name(font, 5, f"Version {BUILD_VERSION}; {family} build")
    set_name(font, 6, names["postscript_name"])
    set_name(font, 16, family)
    set_name(font, 17, names["typographic_style"])
    set_name(font, 18, names["full_name"])
    set_name(font, 21, family)
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

    advance_widths = [width for width, _ in font["hmtx"].metrics.values() if width]
    if advance_widths:
        os2.xAvgCharWidth = round(sum(advance_widths) / len(advance_widths))

    # Windows GDI uses these values as clipping bounds. The head bounds cover
    # every outline, including unencoded alternates reached through OpenType.
    head = font["head"]
    os2.usWinAscent = max(os2.usWinAscent, head.yMax)
    os2.usWinDescent = max(os2.usWinDescent, -head.yMin)

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


def build_face(
    source_dir: Path, output: Path, weight: int, italic: bool, variant: str = "duo"
) -> tuple[Path, Path]:
    source_path = source_dir / SOURCE_FILES[variant][weight][1 if italic else 0]
    font = TTFont(source_path, recalcTimestamp=False, lazy=False)
    if italic:
        voice = "casual" if variant in ("duo", "casual") else "linear"
        configure_italic_f_outlines(font, voice, weight)
        configure_italic_f(font)
        add_italic_te_kerning(font)
    add_collision_kerning(font, source_dir)
    reduce_spacing(font)
    add_narrow_numeric_slash(font)
    add_numeric_punctuation(font)
    update_metadata(font, weight, italic, variant)
    suffix = "Italic" if italic else ""
    filename = f"{FAMILIES[variant].replace(' ', '')}-{WEIGHTS[weight]}{suffix}.ttf"
    ttf_path = output / "ttf" / filename
    with tempfile.TemporaryDirectory(prefix="recursive-autohint-", dir=ttf_path.parent) as directory:
        raw_path = Path(directory) / "raw.ttf"
        hinted_path = Path(directory) / "hinted.ttf"
        font.save(raw_path, reorderTables=False)
        font.close()
        autohint_face(raw_path, hinted_path)
        hinted_path.replace(ttf_path)

    return ttf_path, source_path


def validate_face(
    path: Path, source_path: Path, weight: int, italic: bool, variant: str = "duo"
) -> None:
    font = TTFont(path)
    source = TTFont(source_path)
    try:
        expected_style = style_names(weight, italic, variant)["typographic_style"]
        assert "fvar" not in font, f"{path.name}: variation axes were not fully pinned"
        assert font["name"].getDebugName(16) == FAMILIES[variant]
        assert font["name"].getDebugName(17) == expected_style
        assert font["name"].getDebugName(5).startswith(f"Version {BUILD_VERSION}")
        assert font["OS/2"].usWeightClass == weight
        assert bool(font["OS/2"].fsSelection & 1) == italic
        assert bool(font["head"].macStyle & 2) == italic
        assert font["post"].isFixedPitch == 0
        advance_widths = [width for width, _ in font["hmtx"].metrics.values() if width]
        assert font["OS/2"].xAvgCharWidth == round(
            sum(advance_widths) / len(advance_widths)
        )
        assert font["OS/2"].usWinAscent >= font["head"].yMax
        assert font["OS/2"].usWinDescent >= -font["head"].yMin
        if italic:
            assert font.getBestCmap()[ord("f")] == "f"
            assert "liga" not in {
                record.FeatureTag for record in font["GSUB"].table.FeatureList.FeatureRecord
            }
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
    parser.add_argument(
        "--variants", nargs="+", choices=list(FAMILIES), default=list(FAMILIES),
        help="families to build (default: all three)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    unknown_weights = sorted(set(args.weights) - set(WEIGHTS))
    if unknown_weights:
        raise SystemExit(f"Unsupported weights: {', '.join(map(str, unknown_weights))}")
    required_sources = {
        filename
        for variant in args.variants
        for weight in args.weights
        for filename in SOURCE_FILES[variant][weight]
    }
    required_sources.update(
        SOURCE_FILES[voice][400][int(italic)]
        for voice in ("linear", "casual")
        for italic in (False, True)
    )
    missing_sources = [
        args.source_dir / filename
        for filename in sorted(required_sources)
        if not (args.source_dir / filename).is_file()
    ]
    if missing_sources:
        raise SystemExit(f"Static source not found: {missing_sources[0]}")

    output = args.output.resolve()
    (output / "ttf").mkdir(parents=True, exist_ok=True)

    built = []
    for variant in args.variants:
        for weight in args.weights:
            for italic in (False, True):
                ttf, source_path = build_face(args.source_dir, output, weight, italic, variant)
                validate_face(ttf, source_path, weight, italic, variant)
                built.append(ttf)
                print(f"built {ttf.relative_to(output)}")

    shutil.copyfile(REPO_ROOT / "OFL.txt", output / "OFL.txt")
    print(f"\n{len(built)} TTF faces written to {output}")


if __name__ == "__main__":
    main()
