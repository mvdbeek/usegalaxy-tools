import json
import tempfile
import unittest
from pathlib import Path

from tool_source_store import stamp_tool_conf, validate_manifest, write_config


class ToolSourceStoreHelperTestCase(unittest.TestCase):
    def test_stamp_preserves_existing_root_attributes(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "shed_tool_conf.xml"
            path.write_text(
                '<?xml version="1.0"?>\n<toolbox tool_path="../tools" custom="yes">\n</toolbox>\n',
                encoding="utf-8",
            )
            stamp_tool_conf(path, "cvmfs_main")
            content = path.read_text(encoding="utf-8")
            self.assertIn('tool_path="../tools"', content)
            self.assertIn('custom="yes"', content)
            self.assertIn('store="cvmfs_main"', content)

            stamp_tool_conf(path, "replacement")
            self.assertEqual(path.read_text(encoding="utf-8").count("store="), 1)
            self.assertIn('store="replacement"', path.read_text(encoding="utf-8"))

    def test_config_targets_named_store(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "galaxy.yml"
            write_config(path, Path("/cvmfs/main/config/shed_tool_conf.xml"), root / "output", "cvmfs_main")
            content = path.read_text(encoding="utf-8")
            self.assertIn("cvmfs_main:", content)
            self.assertIn("sources.sqlite", content)
            self.assertIn("shed_tool_conf.xml", content)

    def test_manifest_validation_checks_automatic_provenance(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "sources.sqlite.manifest.json"
            manifest = {
                "manifest_version": 1,
                "cohort": "v1",
                "store": "cvmfs_main",
                "producer": {"galaxy_version": "26.2.0", "git_revision": None},
                "formats": {"database": "1.0", "tool_source": "1.0", "tool_index": "1.0"},
                "tool_index_schema_hash": "a" * 32,
                "capabilities": ["tool-index.entries-by-version"],
                "built_at": "2026-07-16T12:00:00Z",
                "tool_snapshot": {
                    "digest": "b" * 64,
                    "default_tool_count": 2,
                    "versioned_entry_count": 3,
                },
            }
            path.write_text(json.dumps(manifest), encoding="utf-8")
            validate_manifest(path, "v1", "cvmfs_main", "pypi:26.2.0")
            with self.assertRaisesRegex(ValueError, "producer Galaxy version mismatch"):
                validate_manifest(path, "v1", "cvmfs_main", "pypi:25.1.0")

            del manifest["formats"]
            path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing formats"):
                validate_manifest(path, "v1", "cvmfs_main")


if __name__ == "__main__":
    unittest.main()
