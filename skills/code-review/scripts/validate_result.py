"""Validate a Skill result before handing it to a runner. No repository or network access."""

import argparse
import json
from pathlib import Path, PureWindowsPath
import sys


SCHEMA = Path(__file__).resolve().parents[1] / "references" / "result.schema.json"


def unique_keys(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def index_rows(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise ValueError(f"duplicate {key}: {value}")
        result[value] = row
    return result


def check_location(location):
    path = PureWindowsPath(location["path"])
    if path.anchor or not path.parts or ".." in path.parts:
        raise ValueError(f"expected a repository-relative location: {path}")
    if location.get("end_line", location["line"]) < location["line"]:
        raise ValueError(f"end_line precedes line in {path}")


def check_references(result):
    if result["kind"] == "explanation":
        nodes = index_rows(result["nodes"], "id")
        if "selected_node" in result and result["selected_node"] not in nodes:
            raise ValueError("selected_node must name a node in this explanation")
        for node in nodes.values():
            check_location(node["location"])
        for edge in result["edges"]:
            if edge["from"] not in nodes or edge["to"] not in nodes:
                raise ValueError(f"edge refers to an unknown node: {edge}")
        return

    candidates = index_rows(result["candidates"], "local_key")
    findings = index_rows(result["findings"], "candidate_key")
    updates = index_rows(result["updates"], "prior_ref")
    for key in findings:
        if key not in candidates or candidates[key]["disposition"] != "verified":
            raise ValueError(f"finding requires an independently verified candidate: {key}")
    for candidate in candidates.values():
        if candidate.get("duplicate_of") == candidate["local_key"]:
            raise ValueError(f"candidate marked as its own duplicate: {candidate['local_key']}")
    for row in (*candidates.values(), *findings.values(), *updates.values()):
        for location in row.get("locations", []):
            check_location(location)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", nargs="?", default="-", help="UTF-8 JSON file, or - for stdin")
    args = parser.parse_args()
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        parser.exit(2, "validate_result: requires Python package jsonschema (version 4 or newer)\n")
    try:
        raw = sys.stdin.buffer.read() if args.file == "-" else Path(args.file).read_bytes()
        result = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique_keys)
        if not isinstance(result, dict) or result.get("kind") not in ("review", "explanation"):
            raise ValueError("kind must be review or explanation")
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        schema["$ref"] = "#/$defs/" + result["kind"]
        del schema["oneOf"]
        error = next(Draft202012Validator(schema).iter_errors(result), None)
        if error:
            raise ValueError(f"{error.json_path}: {error.message}")
        check_references(result)
    except (ValueError, OSError) as error:
        parser.exit(1, f"validate_result: {error}\n")
    print(f"Valid {result['kind']} result.")


if __name__ == "__main__":
    main()
