"""Exercise the generated fonts with HarfBuzz's real OpenType shaper."""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from fontTools.ttLib import TTFont

from build import DEFAULT_SOURCE_DIR, WEIGHTS, build_face, validate_face


@unittest.skipUnless(shutil.which("hb-shape"), "HarfBuzz hb-shape is required")
class TimeColonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix="recursive-duo-sans-test-")
        cls.addClassCleanup(temporary.cleanup)
        output = Path(temporary.name)
        (output / "ttf").mkdir()
        cls.faces = []
        for weight in WEIGHTS:
            for italic in (False, True):
                path, source = build_face(DEFAULT_SOURCE_DIR, output, weight, italic)
                validate_face(path, source, weight, italic)
                cls.faces.append((path, source))

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

    def test_times_are_centered_by_default_and_calt_can_disable_them(self):
        text = "12:34 9:05 12:34:56 0:00 23:59 3:2 123:456 00:00:00.000"
        for path, source in self.faces:
            with self.subTest(face=path.name):
                self.assert_centered(path, text)
                self.assertEqual(self.shape(path, text, "calt=0"), self.shape(source, text))

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

    def test_non_numeric_colons_and_literal_ratios_keep_their_forms(self):
        text = (
            ": 12: :34 key:value a:2 2:b :: 12::34 12: 34 12 :34 12 : 34 "
            "https://example.test C:\\path 1∶2 ¹:² ₁:₂"
        )
        for path, source in self.faces:
            with self.subTest(face=path.name):
                self.assertEqual(self.shape(path, text), self.shape(source, text))

    def test_raised_and_lowered_digits_do_not_get_lining_punctuation(self):
        for path, source in self.faces:
            for features in ("sups=1", "sinf=1", "numr=1", "dnom=1"):
                with self.subTest(face=path.name, features=features):
                    self.assertEqual(
                        self.shape(path, "12:34", features),
                        self.shape(source, "12:34", features),
                    )

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

    def test_default_and_localized_language_systems(self):
        for path, source in self.faces:
            for language in ("und", "en", "ca", "mo", "nl", "ro", "vi"):
                options = ("--script=Latn", f"--language={language}")
                with self.subTest(face=path.name, language=language):
                    self.assert_centered(path, "12:34:56", options=options)
                    text = "L·l ij́ fi Șș Ţţ"
                    self.assertEqual(
                        self.shape(path, text, options=options),
                        self.shape(source, text, options=options),
                    )

    def test_original_outlines_character_maps_and_positioning_are_preserved(self):
        for path, source_path in self.faces:
            with self.subTest(face=path.name), TTFont(path) as font, TTFont(source_path) as source:
                self.assertEqual(font.getGlyphOrder(), source.getGlyphOrder())
                for tag in ("cmap", "glyf", "hmtx", "GDEF", "GPOS"):
                    # Recompile both sides so cmap subtable packing is normalized.
                    self.assertEqual(font[tag].compile(font), source[tag].compile(source), tag)
                gsub = font["GSUB"].table
                tags = [record.FeatureTag for record in gsub.FeatureList.FeatureRecord]
                self.assertEqual(tags, sorted(tags))
                for record in gsub.ScriptList.ScriptRecord:
                    script = record.Script
                    for lang in [script.DefaultLangSys] + [r.LangSys for r in script.LangSysRecord]:
                        if lang is not None:
                            self.assertIn("calt", [tags[i] for i in lang.FeatureIndex])


if __name__ == "__main__":
    unittest.main()
