import sys
import unittest
from pathlib import Path


BIN_DIR = Path(__file__).resolve().parents[1] / "bin"
sys.path.insert(0, str(BIN_DIR))

import kpush


class RenderFtpScriptTests(unittest.TestCase):
    def setUp(self):
        manifest = {
            "interface": {
                "tbl_cstatmov.pc": [],
                "tbl_init.pc": [],
            },
            "src": {"table.pc": []},
            "tp": {
                "cell4_defaults.ls": [],
                "userclr.ls": [],
            },
            "forms": {"screen.tx": []},
            "data": {"settings.xml": []},
        }
        self.plan = kpush.build_deploy_plan(manifest, exclude_interface=False)

    def test_deletes_dependencies_before_uploading(self):
        script = kpush.render_ftp_script("127.0.0.2", self.plan, delete_only=False)
        commands = script.splitlines()

        expected_order = [
            'delete "tbl_cstatmov.pc"',
            'delete "tbl_init.pc"',
            'delete "tbl_cstatmov.vr"',
            'delete "tbl_init.vr"',
            'delete "table.pc"',
            'delete "table.vr"',
            'delete "cell4_defaults.ls"',
            'delete "userclr.ls"',
            'delete "screen.tx"',
            'delete "settings.xml"',
            'put "table.pc"',
            'put "tbl_cstatmov.pc"',
            'put "tbl_init.pc"',
            'put "cell4_defaults.ls"',
            'put "userclr.ls"',
            'put "screen.tx"',
            'put "settings.xml"',
        ]

        positions = [commands.index(command) for command in expected_order]
        self.assertEqual(positions, sorted(positions))
        self.assertFalse(any(command.startswith("put ") and command.endswith('.vr"') for command in commands))

    def test_delete_only_never_uploads(self):
        script = kpush.render_ftp_script("127.0.0.2", self.plan, delete_only=True)

        self.assertFalse(any(line.startswith("put ") for line in script.splitlines()))


class FtpErrorTests(unittest.TestCase):
    def test_missing_files_are_expected_during_delete(self):
        output = """\
ftp> delete "missing.pc"
550 Program does not exist
ftp> delete "missing.vr"
550 File not found
"""

        self.assertEqual(kpush.find_ftp_errors(output), [])

    def test_missing_file_during_upload_is_still_an_error(self):
        output = """\
ftp> put "missing.pc"
550 File not found
"""

        self.assertEqual(
            kpush.find_ftp_errors(output),
            ["missing.pc: 550 File not found (put)"],
        )

    def test_other_delete_errors_are_still_reported(self):
        output = """\
ftp> delete "protected.ls"
550 Protection error occurred
"""

        self.assertEqual(
            kpush.find_ftp_errors(output),
            ["protected.ls: 550 Protection error occurred (delete)"],
        )

    def test_non_transfer_command_does_not_inherit_delete_context(self):
        output = """\
ftp> delete "missing.pc"
550 File not found
ftp> cd missing:\\
550 File not found
"""

        self.assertEqual(kpush.find_ftp_errors(output), ["550 File not found"])


if __name__ == "__main__":
    unittest.main()
