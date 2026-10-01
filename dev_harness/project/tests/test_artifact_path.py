import unittest

from artifact_path import validate_artifact_path


class ArtifactPathTests(unittest.TestCase):
    def test_valid_names_preserved(self):
        for name in ('a.txt', 'reports/日本語 summary.json', 'nested/deep/file-1.md'):
            with self.subTest(name=name):
                self.assertEqual(validate_artifact_path(name), name)

    def test_invalid_names(self):
        names = ('', '/etc/passwd', '../secret', 'a/../b', './a', 'a//b',
                 'a/', 'C:/a', r'a\b', '//server/share', 'a\x00b', 'a\nb',
                 'CON', 'aux.txt', 'a/LPT9.log', 'a/name.', 'a/name ',
                 'a/<b>', 'a/file?.txt', 'a/x:y', '.', '..', None, 12)
        for name in names:
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_artifact_path(name)


if __name__ == '__main__':
    unittest.main()
