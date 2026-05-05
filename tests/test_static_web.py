import tempfile
import unittest
from pathlib import Path

from sankalp.server import resolve_web_asset


class StaticWebTests(unittest.TestCase):
    def test_root_resolves_to_built_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            self.assertEqual(resolve_web_asset("/", root), index.resolve())

    def test_asset_resolves_inside_build_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "_app" / "entry.js"
            asset.parent.mkdir()
            asset.write_text("console.log('ok')", encoding="utf-8")

            self.assertEqual(resolve_web_asset("/_app/entry.js", root), asset.resolve())

    def test_unknown_route_uses_spa_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = root / "index.html"
            index.write_text("<html></html>", encoding="utf-8")

            self.assertEqual(resolve_web_asset("/settings/memory", root), index.resolve())

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "web"
            root.mkdir()
            (root / "index.html").write_text("<html></html>", encoding="utf-8")

            self.assertIsNone(resolve_web_asset("/../secret.txt", root))


if __name__ == "__main__":
    unittest.main()
