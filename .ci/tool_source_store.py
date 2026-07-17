#!/usr/bin/env python3
"""Prepare and validate versioned CVMFS tool source store bundles."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any


MANIFEST_VERSION = 1
HEX_32 = re.compile(r"^[0-9a-f]{32}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def stamp_tool_conf(path: Path, store: str) -> None:
    """Set the stable store alias while preserving all other root attributes."""
    ET.parse(path)
    content = path.read_text(encoding="utf-8")
    root_match = re.search(r"<toolbox(?:\s[^<>]*?)?>", content)
    if root_match is None:
        raise ValueError(f"{path} does not have a <toolbox> root element")
    root_tag = root_match.group(0)
    escaped = store.replace("&", "&amp;").replace('"', "&quot;")
    if re.search(r"\sstore\s*=", root_tag):
        stamped = re.sub(r"(\sstore\s*=\s*)('[^']*'|\"[^\"]*\")", rf'\1"{escaped}"', root_tag, count=1)
    else:
        stamped = f'{root_tag[:-1]} store="{escaped}">'
    atomic_write(path, f"{content[:root_match.start()]}{stamped}{content[root_match.end():]}")


def yaml_string(value: str | Path) -> str:
    return json.dumps(str(value))


def write_config(path: Path, shed_tool_conf: Path, output_dir: Path, store: str) -> None:
    """Write the minimal Galaxy configuration consumed by the populator."""
    database = output_dir / "sources.sqlite"
    default_database = output_dir / "default.sqlite"
    content = f"""galaxy:
  data_dir: {yaml_string(output_dir / 'data')}
  tool_config_file: []
  shed_tool_config_file: {yaml_string(shed_tool_conf)}
  tool_source_database_connection: {yaml_string(f'sqlite:///{default_database}')}
  tool_source_stores:
    {store}:
      url: {yaml_string(f'sqlite:///{database}')}
"""
    atomic_write(path, content)


def load_manifest(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("manifest must contain a JSON object")
    return value


def validate_manifest(path: Path, cohort: str, store: str, producer: str | None = None) -> None:
    manifest = load_manifest(path)
    errors: list[str] = []

    def expect(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)

    expect(manifest.get("manifest_version") == MANIFEST_VERSION, "unsupported manifest_version")
    expect(manifest.get("cohort") == cohort, f"cohort is not {cohort!r}")
    expect(manifest.get("store") == store, f"store is not {store!r}")
    formats = manifest.get("formats")
    expect(isinstance(formats, dict), "missing formats")
    if isinstance(formats, dict):
        for format_name in ("database", "tool_source", "tool_index"):
            format_version = formats.get(format_name)
            expect(isinstance(format_version, str) and bool(format_version), f"invalid {format_name} format")
    schema_hash = manifest.get("tool_index_schema_hash")
    expect(isinstance(schema_hash, str) and HEX_32.fullmatch(schema_hash) is not None, "invalid schema hash")
    capabilities = manifest.get("capabilities")
    expect(
        isinstance(capabilities, list) and all(isinstance(capability, str) for capability in capabilities),
        "invalid capabilities",
    )
    expect(isinstance(manifest.get("built_at"), str) and bool(manifest.get("built_at")), "missing built_at")
    snapshot = manifest.get("tool_snapshot")
    expect(isinstance(snapshot, dict), "missing tool_snapshot")
    if isinstance(snapshot, dict):
        digest = snapshot.get("digest")
        expect(isinstance(digest, str) and HEX_64.fullmatch(digest) is not None, "invalid snapshot digest")
        for count_name in ("default_tool_count", "versioned_entry_count"):
            count = snapshot.get(count_name)
            expect(isinstance(count, int) and not isinstance(count, bool) and count >= 0, f"invalid {count_name}")
    manifest_producer = manifest.get("producer")
    expect(isinstance(manifest_producer, dict), "missing producer")
    if producer and isinstance(manifest_producer, dict):
        producer_version = producer.removeprefix("pypi:") if producer.startswith("pypi:") else None
        if producer_version:
            expect(manifest_producer.get("galaxy_version") == producer_version, "producer Galaxy version mismatch")
        elif producer.startswith("git:"):
            revision = producer.rsplit("@", 1)[-1]
            expect(manifest_producer.get("git_revision") == revision, "producer Git revision mismatch")
    if errors:
        raise ValueError(f"invalid manifest {path}: {'; '.join(errors)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    stamp = subparsers.add_parser("stamp")
    stamp.add_argument("--tool-conf", type=Path, required=True)
    stamp.add_argument("--store", required=True)
    config = subparsers.add_parser("config")
    config.add_argument("--output", type=Path, required=True)
    config.add_argument("--shed-tool-conf", type=Path, required=True)
    config.add_argument("--output-dir", type=Path, required=True)
    config.add_argument("--store", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--manifest", type=Path, required=True)
    validate.add_argument("--cohort", required=True)
    validate.add_argument("--store", required=True)
    validate.add_argument("--producer")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "stamp":
        stamp_tool_conf(args.tool_conf, args.store)
    elif args.command == "config":
        write_config(args.output, args.shed_tool_conf, args.output_dir, args.store)
    else:
        validate_manifest(args.manifest, args.cohort, args.store, args.producer)


if __name__ == "__main__":
    main()
