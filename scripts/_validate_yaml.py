"""Quick local YAML/XML well-formedness pass for CI artefacts."""

import glob
import sys
import xml.etree.ElementTree as ET

# We don't want pyyaml as a hard dep — use the stdlib + a tiny indent check.
import yaml  # noqa: E402

YAML_PATHS = [
    ".github/workflows/*.yml",
    ".github/dependabot.yml",
    ".github/ISSUE_TEMPLATE/*.yml",
    ".pre-commit-config.yaml",
]

failed = 0
for pattern in YAML_PATHS:
    for path in glob.glob(pattern):
        try:
            with open(path, encoding="utf-8") as f:
                yaml.safe_load(f)
            print(f"  [ok]   {path}")
        except yaml.YAMLError as exc:
            print(f"  [FAIL] {path}: {exc}")
            failed += 1

# Also validate every addon XML
for path in glob.glob("addons/**/*.xml", recursive=True):
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        print(f"  [FAIL XML] {path}: {exc}")
        failed += 1

if failed:
    print(f"\n{failed} file(s) failed validation.")
    sys.exit(1)
print("\nAll YAML + XML files parse cleanly.")
