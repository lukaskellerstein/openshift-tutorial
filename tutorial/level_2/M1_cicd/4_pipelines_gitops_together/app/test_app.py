"""Basic tests for the demo app."""
import unittest


class TestApp(unittest.TestCase):
    def test_version_is_set(self):
        from app import VERSION
        self.assertIsNotNone(VERSION)

    def test_version_format(self):
        from app import VERSION
        parts = VERSION.split(".")
        self.assertEqual(len(parts), 3, "Version should be in X.Y.Z format")


if __name__ == "__main__":
    unittest.main()
