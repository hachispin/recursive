"""Exercise the generated fonts with HarfBuzz's real OpenType shaper."""

import json
import shutil
import string
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fontTools.pens.recordingPen import RecordingPen
from fontTools.ttLib import TTFont

from build import (
    DEFAULT_SOURCE_DIR,
    COLLISION_KERNING,
    FAMILIES,
    NORMALIZE_KERNING_PAIRS,
    SOURCE_FILES,
    SPACING_REDUCTION,
    WEIGHTS,
    add_collision_kerning,
    add_italic_el_kerning,
    add_italic_te_kerning,
    build_face,
    collision_targets,
    configure_italic_f_outlines,
    kern_lookup,
    add_narrow_numeric_slash,
    pair_kerning,
    plain_f_bar_center,
    reduce_spacing,
    validate_face,
)


requires_harfbuzz = unittest.skipUnless(
    shutil.which("hb-shape"), "HarfBuzz hb-shape is required"
)


def outline_commands(font: TTFont, name: str) -> list:
    pen = RecordingPen()
    font.getGlyphSet()[name].draw(pen)
    return pen.value


class DuoSansTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="recursive-duo-sans-test-")
        cls.addClassCleanup(temporary.cleanup)
        output = Path(temporary.name)
        (output / "ttf").mkdir()
        (output / "reference").mkdir()
        (output / "plain-reference").mkdir()
        cls.faces = []
        cls.configurations = []
        references = {}
        cls.plain_references = {}
        for variant in FAMILIES:
            for weight in WEIGHTS:
                for italic in (False, True):
                    path, source = build_face(DEFAULT_SOURCE_DIR, output, weight, italic, variant)
                    validate_face(path, source, weight, italic, variant)
                    if source not in references:
                        reference = output / "reference" / source.name
                        with TTFont(source) as font:
                            if italic:
                                voice = "casual" if "Csl" in source.name else "linear"
                                configure_italic_f_outlines(font, voice, weight)
                                add_italic_te_kerning(font)
                                add_italic_el_kerning(font)
                            add_collision_kerning(font)
                            reduce_spacing(font)
                            add_narrow_numeric_slash(font)
                            font.save(reference)
                        if italic:
                            plain_reference = output / "plain-reference" / source.name
                            with TTFont(source) as plain_font:
                                add_italic_te_kerning(plain_font)
                                add_italic_el_kerning(plain_font)
                                add_collision_kerning(plain_font)
                                reduce_spacing(plain_font)
                                add_narrow_numeric_slash(plain_font)
                                plain_font.save(plain_reference)
                            cls.plain_references[source.name] = plain_reference
                        references[source] = reference
                    reference = references[source]
                    cls.faces.append((path, reference))
                    cls.configurations.append((variant, weight, italic, path, reference))

    def test_family_identity_and_source_selection(self):
        voices = {"duo": ("Lnr", "Csl"), "linear": ("Lnr", "Lnr"), "casual": ("Csl", "Csl")}
        postscript_names = set()
        unique_ids = set()
        self.assertEqual(len(self.faces), 36)
        for variant, weight, italic, path, source_path in self.configurations:
            with self.subTest(face=path.name), TTFont(path) as font, TTFont(source_path) as source:
                self.assertTrue(source_path.name.startswith(f"RecursiveSans{voices[variant][italic]}St-"))
                self.assertEqual(source["OS/2"].usWeightClass, weight)
                self.assertEqual(bool(source["OS/2"].fsSelection & 1), italic)
                family = FAMILIES[variant]
                legacy_family = family if weight in (400, 700) else f"{family} {WEIGHTS[weight]}"
                self.assertEqual(font["name"].getDebugName(1), legacy_family)
                self.assertEqual(font["name"].getDebugName(16), family)
                self.assertEqual(font["name"].getDebugName(21), family)
                postscript_names.add(font["name"].getDebugName(6))
                unique_ids.add(font["name"].getDebugName(3))
        self.assertEqual(len(postscript_names), 36)
        self.assertEqual(len(unique_ids), 36)

    def test_spacing_reduction_preserves_zero_width_marks(self):
        for path, reference in self.faces:
            with self.subTest(face=path.name), TTFont(path) as font, TTFont(DEFAULT_SOURCE_DIR / reference.name) as source:
                for name, (advance, left_bearing) in source["hmtx"].metrics.items():
                    if name == ".ttfautohint":
                        continue
                    expected = advance - SPACING_REDUCTION if advance else 0
                    if name in ("f", "f.italic") and path.name.endswith("Italic.ttf"):
                        left_bearing = font["glyf"][name].xMin
                    self.assertEqual(font["hmtx"][name], (expected, left_bearing))
                self.assertEqual(
                    font["hhea"].advanceWidthMax,
                    max(advance for advance, _ in font["hmtx"].metrics.values()),
                )

    def test_all_faces_share_glyph_and_collision_pair_advances(self):
        expected_advances = None
        targets = collision_targets(DEFAULT_SOURCE_DIR)
        for path, _ in self.faces:
            with self.subTest(face=path.name), TTFont(path) as font:
                advances = {name: width for name, (width, _) in font["hmtx"].metrics.items()}
                if expected_advances is None:
                    expected_advances = advances
                self.assertEqual(advances, expected_advances)

                lookup = kern_lookup(font)
                self.assertTrue(all(
                    subtable.ValueFormat2 == 0 for subtable in lookup.SubTable
                ))
                gpos = font["GPOS"].table
                placement_indices = {
                    index
                    for record in gpos.FeatureList.FeatureRecord
                    if record.FeatureTag == "kern"
                    for index in record.Feature.LookupListIndex[1:]
                }
                for index in placement_indices:
                    self.assertTrue(all(
                        subtable.ValueFormat1 == 0
                        for subtable in gpos.LookupList.Lookup[index].SubTable
                    ))
                cmap = font.getBestCmap()
                for pair, target in targets.items():
                    left, right = (cmap[ord(character)] for character in pair)
                    self.assertEqual(
                        pair_kerning(lookup, left, right),
                        target,
                        pair,
                    )

    def test_unlisted_ascii_pairs_keep_upstream_kerning(self):
        targets = collision_targets(DEFAULT_SOURCE_DIR)
        for path, reference in self.faces:
            with self.subTest(face=path.name), TTFont(path) as font, TTFont(DEFAULT_SOURCE_DIR / reference.name) as source:
                built_lookup = kern_lookup(font)
                source_lookup = kern_lookup(source)
                built_cmap = font.getBestCmap()
                source_cmap = source.getBestCmap()
                for left in string.printable[:95]:
                    for right in string.printable[:95]:
                        pair = left + right
                        if pair in targets:
                            continue
                        self.assertEqual(
                            pair_kerning(built_lookup, built_cmap[ord(left)], built_cmap[ord(right)]),
                            pair_kerning(source_lookup, source_cmap[ord(left)], source_cmap[ord(right)]),
                            pair,
                        )

    def test_upstream_style_differences_are_normalized(self):
        targets = collision_targets(DEFAULT_SOURCE_DIR)
        for pair in NORMALIZE_KERNING_PAIRS:
            self.assertIn(pair, targets)
        for pair in ("ri", "ra", "re", "rv", "Lj"):
            self.assertNotIn(pair, targets)

    @requires_harfbuzz
    def test_slash_is_narrower_only_between_digits(self):
        for path, reference in self.faces:
            with self.subTest(face=path.name), TTFont(path) as font:
                cmap = font.getBestCmap()
                slash = cmap[ord("/")]
                digit = cmap[ord("1")]
                self.assertEqual(font["hmtx"][slash][0], 580)
                self.assertEqual(font["hmtx"]["slash.num"][0], 500)
                self.assertEqual(font["hmtx"][digit][0], 580)
                for text, expected in (("1/2", 1660), ("12/34", 2820)):
                    shaped = self.shape(path, text)
                    self.assertIn("slash.num", [glyph["g"] for glyph in shaped])
                    self.assertEqual(sum(glyph["ax"] for glyph in shaped), expected)
                for text in ("/g", "a/b", "1/g", "a/2", "1/", "/2"):
                    self.assertEqual(self.shape(path, text), self.shape(reference, text))
                self.assertEqual(
                    sum(glyph["ax"] for glyph in self.shape(path, "1/2", "calt=0")),
                    1740,
                )

    def test_cli_builds_selected_families(self):
        with tempfile.TemporaryDirectory(prefix="recursive-family-selection-") as directory:
            subprocess.run(
                [sys.executable, str(Path(__file__).with_name("build.py")),
                 "--variants", "linear", "casual", "--weights", "400", "--output", directory],
                check=True, capture_output=True, text=True,
            )
            self.assertEqual(
                {path.name for path in (Path(directory) / "ttf").glob("*.ttf")},
                {"RecursiveLinearSans-Regular.ttf", "RecursiveLinearSans-RegularItalic.ttf",
                 "RecursiveCasualSans-Regular.ttf", "RecursiveCasualSans-RegularItalic.ttf"},
            )
            self.assertTrue((Path(directory) / "OFL.txt").is_file())

    def shape(self, path, text, features="", options=()):
        command = [
            "hb-shape", "--shapers=ot", "--output-format=json", "--verify",
            *options, str(path), "--text", text,
        ]
        if features:
            command.append(f"--features={features}")
        result = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(result.stdout)

    def assert_centered(self, path, text, features="", options=()):
        disabled = ",".join(filter(None, (features, "calt=0")))
        original = self.shape(path, text, disabled, options)
        expected = [dict(glyph) for glyph in original]
        with TTFont(path) as font:
            cmap = font.getBestCmap()
            colon, ratio = cmap[ord(":")], cmap[ord("∶")]
        colon_count = 0
        for glyph in expected:
            if glyph["g"] == colon:
                glyph["g"] = ratio
                colon_count += 1
        self.assertEqual(colon_count, text.count(":"))
        # Only the drawn glyph changes: advances, offsets and text clusters stay.
        self.assertEqual(self.shape(path, text, features, options), expected)

    @requires_harfbuzz
    def test_times_are_centered_by_default_and_calt_can_disable_them(self):
        text = "12:34 9:05 12:34:56 0:00 23:59 3:2 123:456 00:00:00.000"
        for path, source in self.faces:
            with self.subTest(face=path.name):
                self.assert_centered(path, text)
                self.assertEqual(self.shape(path, text, "calt=0"), self.shape(source, text))

    @requires_harfbuzz
    def test_all_digit_pairs_and_numeral_styles(self):
        text = " ".join(f"{left}:{right}" for left in range(10) for right in range(10))
        for path, _ in self.faces:
            for features in (
                "", "pnum=1", "zero=1", "ss09=1", "ss10=1", "ss11=1", "ss20=1",
                "pnum=1,zero=1,ss09=1,ss11=1",
                "pnum=1,ss10=1,ss09=1,ss11=1",
            ):
                with self.subTest(face=path.name, features=features):
                    self.assert_centered(path, text, features)

    @requires_harfbuzz
    def test_non_numeric_colons_and_literal_ratios_keep_their_forms(self):
        text = (
            ": 12: :34 key:value a:2 2:b :: 12::34 12: 34 12 :34 12 : 34 "
            "https://example.test C:\\path 1∶2 ¹:² ₁:₂"
        )
        for path, source in self.faces:
            with self.subTest(face=path.name):
                self.assertEqual(
                    self.shape(path, text, "kern=0"),
                    self.shape(source, text, "kern=0"),
                )

    @requires_harfbuzz
    def test_raised_and_lowered_digits_do_not_get_lining_punctuation(self):
        for path, source in self.faces:
            for features in ("sups=1", "sinf=1", "numr=1", "dnom=1"):
                with self.subTest(face=path.name, features=features):
                    self.assertEqual(
                        self.shape(path, "12:34", features),
                        self.shape(source, "12:34", features),
                    )

    @requires_harfbuzz
    def test_code_ligatures_remain_opt_in_and_independent(self):
        operators = "a:=b :: -> => === != <= >= && ||"
        for path, source in self.faces:
            with self.subTest(face=path.name):
                default = self.shape(path, operators)
                enabled = self.shape(path, operators, "dlig=1")
                self.assertEqual(default, self.shape(source, operators))
                self.assertEqual(enabled, self.shape(source, operators, "dlig=1"))
                self.assertNotEqual(default, enabled)
                self.assert_centered(path, "12:34", "dlig=0")
                self.assert_centered(path, "12:34", "dlig=1")
                self.assertEqual(
                    self.shape(path, "12:34", "calt=0,dlig=1"),
                    self.shape(source, "12:34", "dlig=1"),
                )

    @requires_harfbuzz
    def test_default_and_localized_language_systems(self):
        for path, source in self.faces:
            for language in ("und", "en", "ca", "mo", "nl", "ro", "vi"):
                options = ("--script=Latn", f"--language={language}")
                with self.subTest(face=path.name, language=language):
                    self.assert_centered(path, "12:34:56", options=options)
                    text = "L·l ij́ fi ffi Șș Ţţ"
                    features = "ss13=1" if path.name.endswith("Italic.ttf") else ""
                    self.assertEqual(
                        self.shape(path, text, features, options),
                        self.shape(source, text, options=options),
                    )
                    if path.name.endswith("Italic.ttf"):
                        self.assertEqual(self.shape(path, "f", "ss03=1", options)[0]["g"], "f.italic")
                        self.assertEqual(self.shape(path, "f", "ss14=1", options)[0]["g"], "f.simple")

    @requires_harfbuzz
    def test_swash_f_is_the_italic_default_and_alternates_remain_opt_in(self):
        text = "f of off coffee fluffy fi ffi fifty office gf pf yf"
        alternates = ",".join(f"aalt[{i}]=3" for i, char in enumerate(text) if char == "f")
        for path, source in self.faces:
            if not path.name.endswith("Italic.ttf"):
                continue
            expected = self.shape(source, text, "liga=0")
            for features in ("", "calt=0", "liga=0", "liga=1", "dlig=1"):
                with self.subTest(face=path.name, features=features):
                    self.assertEqual(self.shape(path, text, features), expected)
            for features in ("ss03=1", "ss03=1,liga=1"):
                with self.subTest(face=path.name, features=features):
                    self.assertEqual(
                        self.shape(path, text, features), self.shape(source, text, f"liga=0,{alternates}")
                    )
            for features in ("ss14=1", "ss14=1,liga=1"):
                with self.subTest(face=path.name, features=features):
                    expected_plain = self.shape(source, text, "liga=0")
                    actual = self.shape(path, text, features)
                    self.assertEqual([g["ax"] for g in actual], [g["ax"] for g in expected_plain])
                    self.assertEqual(
                        [g["g"] for g in actual],
                        ["f.simple" if g["g"] == "f" else g["g"] for g in expected_plain],
                    )
            # The swash f is the cmap default even without OpenType shaping.
            shaped = self.shape(path, "f", options=("--shapers=fallback",))
            self.assertEqual(shaped[0]["g"], "f")

    def test_italic_f_outlines_and_shared_advances(self):
        for _, _, italic, path, _ in self.configurations:
            if not italic:
                continue
            with self.subTest(face=path.name), TTFont(path) as font:
                source = TTFont(DEFAULT_SOURCE_DIR / SOURCE_FILES[
                    "casual" if path.name.startswith(("RecursiveDuo", "RecursiveCasual")) else "linear"
                ][font["OS/2"].usWeightClass][1])
                try:
                    for name, bar_contour in (("f", 1), ("f.italic", 0)):
                        glyph = font["glyf"][name]
                        self.assertLessEqual(glyph.yMin, -185)
                        start = 0 if bar_contour == 0 else glyph.endPtsOfContours[0] + 1
                        end = glyph.endPtsOfContours[bar_contour] + 1
                        bar_ys = [y for _, y in glyph.coordinates[start:end]]
                        self.assertLessEqual(
                            abs((min(bar_ys) + max(bar_ys)) / 2 - plain_f_bar_center(source)),
                            1,
                        )
                    self.assertEqual(
                        outline_commands(font, "f.simple"),
                        outline_commands(source, "f"),
                    )
                    self.assertEqual(font["hmtx"]["f"][0], font["hmtx"]["f.simple"][0])
                finally:
                    source.close()

    @requires_harfbuzz
    def test_italic_f_alternates_share_collision_pair_spacing(self):
        for path, _ in self.faces:
            if not path.name.endswith("Italic.ttf"):
                continue
            for pair in (
                "fi", "fj", "fD", "f,", "qf", "#f", "`f", "ff",
                "Df", "Pf", "rf", "tf", "(f", "f/",
            ):
                with self.subTest(face=path.name, pair=pair):
                    widths = [
                        sum(glyph["ax"] for glyph in self.shape(path, pair, features))
                        for features in ("", "ss03=1", "ss14=1")
                    ]
                    self.assertEqual(widths, [widths[0]] * len(widths))
                    if pair in ("fi", "fj"):
                        self.assertEqual(self.shape(path, pair)[1]["dx"], 0)
                        self.assertEqual(
                            self.shape(path, pair, "ss03=1")[1]["dx"],
                            {"fi": 80, "fj": 35}[pair],
                        )
                        self.assertEqual(
                            self.shape(path, pair, "ss14=1")[1]["dx"],
                            20 if pair == "fi" else 0,
                        )
            # A following letter must sit at its normal distance from i.
            fil = self.shape(path, "fil")
            il = self.shape(path, "il")
            self.assertEqual(
                [(glyph["dx"], glyph["ax"]) for glyph in fil[1:]],
                [(glyph["dx"], glyph["ax"]) for glyph in il],
            )

    @requires_harfbuzz
    def test_italic_ligatures_require_ss13(self):
        text = "fi ffi f of office fifty"
        for path, source in self.faces:
            if not path.name.endswith("Italic.ttf"):
                continue
            with self.subTest(face=path.name):
                original = self.shape(source, text)
                expected = [dict(glyph) for glyph in original]
                for glyph in expected:
                    if glyph["g"] == "f":
                        glyph["g"] = "f.italic"
                self.assertEqual(self.shape(path, text, "ss13=1"), original)
                self.assertEqual(self.shape(path, text, "ss03=1,ss13=1"), expected)
                for features in ("", "liga=1", "ss03=1", "dlig=1"):
                    glyphs = self.shape(path, "fi ffi", features)
                    self.assertFalse({"uniFB01", "f_f_i"}.intersection(g["g"] for g in glyphs))

    @requires_harfbuzz
    def test_italic_te_kerning_excludes_pi(self):
        pairs = ("te", "ţé", "ťě", "țệ", "ṭë", "ṯê", "ẗē", "ŧė")
        for _, _, italic, path, _ in self.configurations:
            for pair in pairs:
                with self.subTest(face=path.name, pair=pair):
                    kerned = self.shape(path, pair)
                    unkerned = self.shape(path, pair, "kern=0")
                    self.assertEqual(sum(g["ax"] for g in kerned), sum(g["ax"] for g in unkerned))
                    self.assertEqual(kerned[1]["dx"] - unkerned[1]["dx"], -20 if italic else 0)
            with self.subTest(face=path.name, pair="πe"):
                self.assertEqual(self.shape(path, "πe"), self.shape(path, "πe", "kern=0"))

        for variant in FAMILIES:
            for weight in WEIGHTS:
                widths = [
                    sum(g["ax"] for g in self.shape(path, "te"))
                    for v, w, _, path, _ in self.configurations
                    if (v, w) == (variant, weight)
                ]
                with self.subTest(variant=variant, weight=weight):
                    self.assertEqual(widths, [widths[0], widths[0]])

    @requires_harfbuzz
    def test_italic_el_tightening_preserves_advance(self):
        pairs = ("el", "él", "ẹḷ", "eł", "ěl")
        for _, _, italic, path, _ in self.configurations:
            for pair in pairs:
                with self.subTest(face=path.name, pair=pair):
                    shaped = self.shape(path, pair)
                    unkerned = self.shape(path, pair, "kern=0")
                    self.assertEqual(sum(g["ax"] for g in shaped), sum(g["ax"] for g in unkerned))
                    self.assertEqual(shaped[1]["dx"] - unkerned[1]["dx"], -20 if italic else 0)
            for pair in ("æl", "eh"):
                with self.subTest(face=path.name, pair=pair):
                    self.assertEqual(self.shape(path, pair), self.shape(path, pair, "kern=0"))

        for weight in WEIGHTS:
            widths = [
                sum(g["ax"] for g in self.shape(path, "el"))
                for variant, face_weight, _, path, _ in self.configurations
                if face_weight == weight
            ]
            with self.subTest(weight=weight):
                self.assertEqual(widths, [widths[0]] * len(widths))

    @requires_harfbuzz
    def test_both_f_forms_preserve_accent_positioning(self):
        text = "f́ f̣ f̨"
        alternates = ",".join(f"aalt[{i}]=3" for i, char in enumerate(text) if char == "f")
        for path, source in self.faces:
            if not path.name.endswith("Italic.ttf"):
                continue
            with self.subTest(face=path.name):
                self.assertEqual(self.shape(path, text), self.shape(source, text))
                self.assertEqual(self.shape(path, text, "ss03=1"), self.shape(source, text, alternates))
                plain_expected = [
                    dict(glyph) for glyph in self.shape(self.plain_references[source.name], text)
                ]
                for glyph in plain_expected:
                    if glyph["g"] == "f":
                        glyph["g"] = "f.simple"
                self.assertEqual(
                    self.shape(path, text, "ss14=1"),
                    plain_expected,
                )

    @requires_harfbuzz
    def test_roman_fi_spacing_and_ligatures(self):
        text = "f of off coffee fi ffi fluffy"
        for path, source in self.faces:
            if path.name.endswith("Italic.ttf"):
                continue
            upstream = DEFAULT_SOURCE_DIR / source.name
            self.assertEqual(
                sum(glyph["ax"] for glyph in self.shape(path, "fi")),
                sum(glyph["ax"] for glyph in self.shape(upstream, "fi")) - 2 * SPACING_REDUCTION,
            )
            for features in ("", "ss03=1", "ss14=1", "liga=1", "dlig=1", "ss13=1"):
                with self.subTest(face=path.name, features=features):
                    self.assertEqual(self.shape(path, text, features), self.shape(source, text, features))

    @requires_harfbuzz
    def test_collision_pairs_share_the_largest_safe_width(self):
        for pair in (
            "Q)", "qj", "Lj", "Tx", "YY", "sT", "*q", "fD", "fi", "fj", "f,", "qf", "#f", "`f",
            "Df", "Pf", "rf", "ri", "tf", "(f", "f/", "Qf", "_f",
        ):
            safe_source_widths = []
            for voice in ("linear", "casual"):
                for italic in (False, True):
                    style = "italic" if italic else "upright"
                    for weight in WEIGHTS:
                        source = DEFAULT_SOURCE_DIR / SOURCE_FILES[voice][weight][int(italic)]
                        source_width = sum(glyph["ax"] for glyph in self.shape(source, pair))
                        safe_source_widths.append(
                            source_width + COLLISION_KERNING[f"{voice}-{style}"].get(pair, 0)
                        )
            expected = max(safe_source_widths) - 2 * SPACING_REDUCTION
            for path, _ in self.faces:
                with self.subTest(face=path.name, pair=pair):
                    self.assertEqual(
                        sum(glyph["ax"] for glyph in self.shape(path, pair)),
                        expected,
                    )

    @requires_harfbuzz
    def test_every_corrected_pair_shapes_to_one_shared_width(self):
        targets = collision_targets(DEFAULT_SOURCE_DIR)
        expected_widths = {}
        for path, _ in self.faces:
            with TTFont(path) as font:
                cmap = font.getBestCmap()
                for pair, target in targets.items():
                    with self.subTest(face=path.name, pair=pair):
                        width = sum(font["hmtx"][cmap[ord(c)]][0] for c in pair) + target
                        shaped = self.shape(path, pair, "liga=0")
                        self.assertEqual(len(shaped), 2)
                        self.assertEqual(sum(glyph["ax"] for glyph in shaped), width)
                        expected_widths.setdefault(pair, width)
                        self.assertEqual(width, expected_widths[pair])

    @requires_harfbuzz
    def test_restored_pairs_shape_with_upstream_kerning(self):
        for path, reference in self.faces:
            source = DEFAULT_SOURCE_DIR / reference.name
            for pair in ("ri", "ra", "re", "rv", "Lj"):
                with self.subTest(face=path.name, pair=pair):
                    upstream = self.shape(source, pair, "liga=0")
                    built = self.shape(path, pair, "liga=0")
                    self.assertEqual(
                        [glyph["ax"] for glyph in built],
                        [glyph["ax"] - SPACING_REDUCTION for glyph in upstream],
                    )

    @requires_harfbuzz
    def test_adjacent_pair_adjustments_both_apply(self):
        # The first pair must not consume the middle glyph and suppress the
        # second. Include the italic t-e and f-alternate placement exceptions.
        for path, _ in self.faces:
            features_list = ("", "ss03=1", "ss14=1") if path.name.endswith("Italic.ttf") else ("",)
            for features in features_list:
                for text in ("arf", "ari", "afi", "rfi", "fDf", "tef"):
                    with self.subTest(face=path.name, features=features, text=text):
                        left = self.shape(path, text[:2], features)
                        right = self.shape(path, text[1:], features)
                        middle = self.shape(path, text[1], features)
                        triple = self.shape(path, text, features)
                        self.assertEqual(len(triple), 3)
                        self.assertEqual(
                            sum(glyph["ax"] for glyph in triple),
                            sum(glyph["ax"] for glyph in left)
                            + sum(glyph["ax"] for glyph in right)
                            - middle[0]["ax"],
                        )
                        self.assertEqual(triple[1]["ax"], right[0]["ax"])
                        if text == "tef" and path.name.endswith("Italic.ttf"):
                            self.assertEqual(triple[1]["dx"], left[1]["dx"])

    @requires_harfbuzz
    def test_text_length_is_constant_across_weights(self):
        text = "Q) qj L+ P. Lj YY Quickly jumping past Q)"
        for variant in FAMILIES:
            for italic in (False, True):
                advances = []
                for weight in WEIGHTS:
                    path = next(
                        path for v, w, i, path, _ in self.configurations
                        if (v, w, i) == (variant, weight, italic)
                    )
                    advances.append(sum(glyph["ax"] for glyph in self.shape(path, text)))
                with self.subTest(variant=variant, italic=italic):
                    self.assertEqual(advances, [advances[0]] * len(WEIGHTS))

    def test_original_outlines_character_maps_and_other_positioning_are_preserved(self):
        for variant, weight, italic, path, source_path in self.configurations:
            with self.subTest(face=path.name), TTFont(path) as font, TTFont(source_path) as source:
                names = [name for name in font.getGlyphOrder() if name != ".ttfautohint"]
                self.assertEqual(
                    names,
                    [name for name in source.getGlyphOrder() if name != ".ttfautohint"],
                )
                for name in names:
                    self.assertEqual(outline_commands(font, name), outline_commands(source, name), name)
                    self.assertEqual(font["hmtx"][name], source["hmtx"][name], name)
                for tag in ("cmap", "GDEF"):
                    # Recompile both sides so cmap subtable packing is normalized.
                    self.assertEqual(font[tag].compile(font), source[tag].compile(source), tag)
                self.assertEqual(
                    font["GPOS"].compile(font), source["GPOS"].compile(source), "GPOS"
                )
                gsub = font["GSUB"].table
                tags = [record.FeatureTag for record in gsub.FeatureList.FeatureRecord]
                self.assertEqual(tags, sorted(tags))
                for record in gsub.ScriptList.ScriptRecord:
                    script = record.Script
                    for lang in [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]:
                        if lang is not None:
                            self.assertIn("calt", [tags[i] for i in lang.FeatureIndex])

    def test_edited_glyphs_are_autohinted(self):
        for _, _, italic, path, _ in self.configurations:
            with self.subTest(face=path.name), TTFont(path) as font:
                self.assertIn("ttfautohint", font["name"].getDebugName(5))
                for name in ("slash.num", "f", "f.italic") if italic else ("slash.num",):
                    self.assertGreater(len(font["glyf"][name].program.getBytecode()), 0, name)


if __name__ == "__main__":
    unittest.main()
