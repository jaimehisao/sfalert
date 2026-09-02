import unittest

import sfalert


class PackageTest(unittest.TestCase):
    def test_version_is_set(self) -> None:
        self.assertRegex(sfalert.__version__, r"^\d+\.\d+")
