import sys
import unittest
from pathlib import Path
from unittest import mock


BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

import rossum
from rossum_cli import CliError


class CleanSafetyTests(unittest.TestCase):
    def setUp(self):
        self.build_dir = r"C:\project\build"
        self.temp_dir = r"C:\project\temp"
        self.other_dir = r"C:\project"

    def test_allows_clean_from_marked_build_directory(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=True), \
                mock.patch.object(rossum, "is_rossum_build_dir", return_value=True):
            target = rossum.validate_clean_target(self.build_dir, self.build_dir)

        self.assertEqual(target, self.build_dir)

    def test_refuses_target_when_current_directory_is_different(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=True), \
                mock.patch.object(rossum, "is_rossum_build_dir", return_value=True), \
                self.assertRaises(CliError) as caught:
            rossum.validate_clean_target(self.build_dir, self.other_dir)

        self.assertIn("outside the build directory", caught.exception.title)

    def test_refuses_marked_directory_not_named_build(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=True), \
                mock.patch.object(rossum, "is_rossum_build_dir", return_value=True), \
                self.assertRaises(CliError) as caught:
            rossum.validate_clean_target(self.temp_dir, self.temp_dir)

        self.assertIn("not named 'build'", caught.exception.title)

    def test_refuses_current_directory_without_build_marker(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=True), \
                mock.patch.object(rossum, "is_rossum_build_dir", return_value=False), \
                self.assertRaises(CliError) as caught:
            rossum.validate_clean_target(self.build_dir, self.build_dir)

        self.assertIn("No build.ninja", caught.exception.detail)

    def test_force_overrides_location_and_marker_checks(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=True), \
                mock.patch.object(rossum, "is_rossum_build_dir", return_value=False):
            target = rossum.validate_clean_target(
                self.temp_dir,
                self.other_dir,
                force=True,
            )

        self.assertEqual(target, self.temp_dir)

    def test_force_does_not_allow_a_missing_target(self):
        with mock.patch.object(rossum.os.path, "isdir", return_value=False), \
                self.assertRaises(CliError):
            rossum.validate_clean_target(
                self.build_dir,
                self.other_dir,
                force=True,
            )


if __name__ == "__main__":
    unittest.main()
