import os
import tempfile
import unittest

from main import _read_calibration_square_control_file


class CalibrationSquareControlFileTests(unittest.TestCase):
    def test_reads_only_new_valid_commands(self):
        with tempfile.NamedTemporaryFile("w+", delete=False) as f:
            path = f.name
            f.write("wzx\n")

        try:
            commands, offset = _read_calibration_square_control_file(path, 0)
            self.assertEqual(commands, "wx")

            with open(path, "a", encoding="ascii") as f:
                f.write("A!f")

            commands, offset = _read_calibration_square_control_file(path, offset)
            self.assertEqual(commands, "af")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
