import unittest
from unittest.mock import patch

import sankalp.server as server


class AppLifecycleTests(unittest.TestCase):
    def test_schedule_relaunch_opens_macos_app(self):
        with patch("sankalp.server.platform.system", return_value="Darwin"), patch("sankalp.server.subprocess.Popen") as popen:
            result = server._schedule_relaunch()

        self.assertTrue(result)
        command = popen.call_args.args[0]
        self.assertEqual(command[:2], ["/bin/sh", "-c"])
        self.assertIn("/usr/bin/open", command[2])
        self.assertIn("Sankalp.app", command[2])

    def test_schedule_relaunch_rejects_unsupported_platform(self):
        with patch("sankalp.server.platform.system", return_value="Linux"), patch("sankalp.server.subprocess.Popen") as popen:
            result = server._schedule_relaunch()

        self.assertFalse(result)
        popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
