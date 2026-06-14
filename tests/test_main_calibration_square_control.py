import os
import tempfile
import unittest

from dmdcontrol.patterns.calibration_square import read_calibration_square_control_file


class CalibrationSquareControlFileTests(unittest.TestCase):

    def test_reads_only_new_valid_commands(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            path = f.name
            f.write("wzx\n")

        try:
            commands, offset = read_calibration_square_control_file(path, 0)
            self.assertEqual(commands, "wx")

            with open(path, "a", encoding="ascii") as f:
                f.write("A!f")

            commands, offset = read_calibration_square_control_file(path, offset)
            self.assertEqual(commands, "af")
        finally:
            os.unlink(path)

    def test_truncated_file_resets_offset(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            path = f.name
            f.write("wasd")

        try:
            commands, offset = read_calibration_square_control_file(path, 0)
            self.assertEqual(commands, "wasd")
            self.assertGreater(offset, 0)

            with open(path, "w", encoding="ascii") as f:
                f.write("qe")

            commands, offset = read_calibration_square_control_file(path, offset)
            self.assertEqual(commands, "qe")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
