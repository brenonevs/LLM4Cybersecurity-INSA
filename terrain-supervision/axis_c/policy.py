"""Load the versioned Axis C contract. This module does not authorize calls."""
import argparse
import hashlib
import json
import math
import posixpath
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple


DEFAULT_POLICY = Path(__file__).with_name("policy.json")
ORIGIN_LEVELS = MappingProxyType({
    "externe": 0, "interne": 1, "utilisateur": 2, "systeme": 3,
})
TOOL_NAMES = frozenset({
    "read_log", "search_document", "send_email", "restart_equipment", "write_file",
})


class PolicyError(ValueError):
    """Invalid configuration: do not continue with a partially loaded policy."""


@dataclass(frozen=True)
class ToolPolicy:
    minimum_origin: str
    minimum_confidence: Optional[float]
    allowed_domains: Tuple[str, ...] = ()
    allow_subdomains: bool = False
    allowed_directory: Optional[str] = None


@dataclass(frozen=True)
class Policy:
    version: str
    default_effect: str
    tools: Mapping[str, ToolPolicy]
    sha256: str


def _keys(value, expected, location):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise PolicyError(f"{location}: expected exactly {sorted(expected)}")


def _domain(value):
    # Configuration accepts canonical ASCII domain names, never email addresses,
    # wildcards or URLs. Subdomain matching is a separate, explicit condition.
    if not isinstance(value, str) or not 1 <= len(value) <= 253:
        return False
    labels = value.split(".")
    return len(labels) >= 2 and all(
        re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
        for label in labels
    )


def parse_policy(data):
    """Validate all five rules and return a detached, read-only configuration."""
    _keys(data, {"version", "default_effect", "tools"}, "policy")
    version = data["version"]
    if not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", version):
        raise PolicyError("version: expected a nonempty version identifier")
    if data["default_effect"] != "deny":
        raise PolicyError("default_effect: only deny is supported")
    _keys(data["tools"], TOOL_NAMES, "tools")
    rules = {}
    for name, rule in data["tools"].items():
        fields = {"minimum_origin", "minimum_confidence"}
        if name == "send_email":
            fields |= {"allowed_domains", "allow_subdomains"}
        elif name == "write_file":
            fields |= {"allowed_directory"}
        _keys(rule, fields, name)
        origin = rule["minimum_origin"]
        if not isinstance(origin, str) or origin not in ORIGIN_LEVELS:
            raise PolicyError(f"{name}: unknown minimum_origin")
        confidence = rule["minimum_confidence"]
        if confidence is not None and (
            type(confidence) not in (int, float)
            or not 0 <= confidence <= 1
            or not math.isfinite(confidence)
        ):
            raise PolicyError(f"{name}: minimum_confidence must be null or a finite number in [0, 1]")
        domains = rule.get("allowed_domains", [])
        subdomains = rule.get("allow_subdomains", False)
        if name == "send_email":
            if not isinstance(domains, list) or not domains or not all(_domain(d) for d in domains):
                raise PolicyError("send_email: allowed_domains must contain canonical domain names")
            if len(set(domains)) != len(domains):
                raise PolicyError("send_email: duplicate allowed_domains")
            if type(subdomains) is not bool:
                raise PolicyError("send_email: allow_subdomains must be boolean")
        directory = rule.get("allowed_directory")
        if name == "write_file":
            if (not isinstance(directory, str) or not directory.startswith("/")
                    or directory.startswith("//") or directory == "/"
                    or not directory.endswith("/")
                    or any(ord(c) < 32 or ord(c) == 127
                           or 0xD800 <= ord(c) <= 0xDFFF for c in directory)
                    or "\\" in directory
                    or directory != posixpath.normpath(directory) + "/"):
                raise PolicyError("write_file: expected a normalized absolute POSIX directory other than /")
        rules[name] = ToolPolicy(origin, confidence, tuple(domains), subdomains, directory)
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return Policy(version, "deny", MappingProxyType(rules),
                  hashlib.sha256(canonical).hexdigest())


def _unique_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise PolicyError(f"duplicate JSON key: {key}")
        obj[key] = value
    return obj


def load_policy(path=DEFAULT_POLICY):
    """Read strict JSON; unknown fields and duplicate keys are rejected."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"),
                          object_pairs_hook=_unique_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PolicyError(f"cannot read policy: {error}") from error
    return parse_policy(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", type=Path, default=DEFAULT_POLICY)
    args = parser.parse_args()
    try:
        policy = load_policy(args.path)
    except PolicyError as error:
        parser.error(str(error))
    print(json.dumps({"version": policy.version, "sha256": policy.sha256,
                      "tools": sorted(policy.tools), "default_effect": policy.default_effect,
                      "status": "configuration_validated_not_enforced"}, indent=2))


if __name__ == "__main__":
    main()
