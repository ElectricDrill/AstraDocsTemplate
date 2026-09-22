from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path


TEMPLATE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TEMPLATE / "tools"))
from lockfile import LockfileError, load_and_validate  # noqa: E402
from astra_docs import configure_new_repository  # noqa: E402


class ToolkitTests(unittest.TestCase):
    def test_template_lock_is_valid(self) -> None:
        data = load_and_validate(TEMPLATE / "release-lock.yml")
        self.assertEqual(data["package"]["source"]["ref"], "main")

    def test_invalid_ref_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / "release-lock.yml"
            lock.write_text((TEMPLATE / "release-lock.yml").read_text().replace("ref: main", "ref: main; rm -rf /"), encoding="utf-8")
            with self.assertRaises(LockfileError):
                load_and_validate(lock)

    def test_sync_updates_only_managed_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "template"
            repository = root / "docs"
            shutil.copytree(TEMPLATE, source, ignore=shutil.ignore_patterns("__pycache__"))
            shutil.copytree(TEMPLATE, repository, ignore=shutil.ignore_patterns("__pycache__"))
            config = repository / "astra-docs.json"
            config.write_text('{"schema": 1, "package_name": "Health", "title": "Astra Health", "pages_url": "https://electricdrill.github.io/AstraHealthDocs/"}\n', encoding="utf-8")
            subprocess.run([sys.executable, "tools/astra_docs.py", "sync", "--apply", "--template-ref", "v1.0.0", "--template-path", str(source)], cwd=repository, check=True)
            lock_before = (repository / "release-lock.yml").read_text(encoding="utf-8")
            notes = repository / "guide.md"
            notes.write_text("keep me\n", encoding="utf-8")
            readme = repository / "README.md"
            readme.write_text("package-authored readme\n", encoding="utf-8")
            (source / "DocFx/styles/astra.css").write_text("/* newer */\n", encoding="utf-8")
            result = subprocess.run([sys.executable, "tools/astra_docs.py", "sync", "--check", "--template-ref", "v1.0.1", "--template-path", str(source)], cwd=repository)
            self.assertEqual(result.returncode, 1)
            subprocess.run([sys.executable, "tools/astra_docs.py", "sync", "--apply", "--template-ref", "v1.0.1", "--template-path", str(source)], cwd=repository, check=True)
            self.assertEqual((repository / "release-lock.yml").read_text(encoding="utf-8"), lock_before)
            self.assertEqual(notes.read_text(encoding="utf-8"), "keep me\n")
            self.assertEqual(readme.read_text(encoding="utf-8"), "package-authored readme\n")
            self.assertEqual((repository / "DocFx/styles/astra.css").read_text(encoding="utf-8"), "/* newer */\n")

    def test_configure_new_repository_renders_public_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary) / "docs"
            shutil.copytree(TEMPLATE, repository, ignore=shutil.ignore_patterns("__pycache__"))
            configure_new_repository(repository, Namespace(package_name="Health", package_id="com.electricdrill.astra-health", assembly="ElectricDrill.Astra.Health.Runtime", namespace="ElectricDrill.Astra.Health", source_repo="Cis8/AstraHealth", source_path="Packages/com.electricdrill.astra-health", ref="main", title=None))
            self.assertIn("Astra Health", (repository / "DocFx/docfx.json").read_text(encoding="utf-8"))
            self.assertNotIn("{{PACKAGE_NAME}}", (repository / "README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
