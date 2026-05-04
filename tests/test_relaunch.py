import unittest
from unittest.mock import patch

from sankalp.macos import relaunch_with_latest_code


class RelaunchTests(unittest.TestCase):
    def test_relaunch_schedules_restart(self):
        with patch("sankalp.macos.is_macos", return_value=False), patch("threading.Thread") as thread:
            result = relaunch_with_latest_code()

        self.assertTrue(result["ok"])
        thread.assert_called_once()


if __name__ == "__main__":
    unittest.main()
