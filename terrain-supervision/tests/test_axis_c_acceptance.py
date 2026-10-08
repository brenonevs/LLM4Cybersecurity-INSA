"""Behavioral acceptance gate for the policy loader, not the future defense."""
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))

from axis_c.policy import DEFAULT_POLICY, ORIGIN_LEVELS, PolicyError, load_policy, parse_policy


@pytest.fixture
def config():
    return json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))


def cli(cwd, *args):
    env = dict(os.environ, PYTHONPATH=str(PROJECT))
    return subprocess.run(
        [sys.executable, "-B", "-S", "-m", "axis_c.policy", *map(str, args)],
        cwd=cwd, env=env, text=True, capture_output=True, timeout=10,
    )


@pytest.mark.parametrize("score", [None, 0, 1, 0.0, 1.0, 0.5])
@pytest.mark.parametrize("origin", ["externe", "interne", "utilisateur", "systeme"])
def test_valid_attribute_boundaries_for_every_tool(config, score, origin):
    for rule in config["tools"].values():
        rule.update(minimum_origin=origin, minimum_confidence=score)
    policy = parse_policy(config)
    assert all(r.minimum_origin == origin and r.minimum_confidence == score
               for r in policy.tools.values())
    assert list(ORIGIN_LEVELS) == ["externe", "interne", "utilisateur", "systeme"]
    assert list(ORIGIN_LEVELS.values()) == [0, 1, 2, 3]


@pytest.mark.parametrize("value", [None, [], "policy", True, 1])
def test_wrong_object_types_are_rejected_at_each_level(config, value):
    with pytest.raises(PolicyError):
        parse_policy(value)
    original_tools = config["tools"]
    config["tools"] = value
    with pytest.raises(PolicyError):
        parse_policy(config)
    config["tools"] = original_tools
    for name in original_tools:
        original = original_tools[name]
        original_tools[name] = value
        with pytest.raises(PolicyError):
            parse_policy(config)
        original_tools[name] = original


def test_all_required_fields_are_required(config):
    for key in list(config):
        value = config.pop(key)
        with pytest.raises(PolicyError):
            parse_policy(config)
        config[key] = value
    for rule in config["tools"].values():
        for key in list(rule):
            value = rule.pop(key)
            with pytest.raises(PolicyError):
                parse_policy(config)
            rule[key] = value


@pytest.mark.parametrize("version", ["", "v 1", "v1\n", None, [], 1])
def test_invalid_version_is_rejected(config, version):
    config["version"] = version
    with pytest.raises(PolicyError, match="version"):
        parse_policy(config)


def test_unknown_fields_are_rejected_at_each_level(config):
    for obj in [config, config["tools"], *config["tools"].values()]:
        obj["unexpected"] = None
        with pytest.raises(PolicyError):
            parse_policy(config)
        del obj["unexpected"]


@pytest.mark.parametrize("domains", [[], None, {}, "entreprise.fr", [None], [False],
    ["entreprise.fr", "entreprise.fr"], ["a" * 64 + ".fr"],
    ["a." * 126 + "fr"], ["münchen.fr"], ["a-.fr"], ["a_b.fr"], ["a.fr\n"]])
def test_domain_shape_and_length_boundaries(config, domains):
    config["tools"]["send_email"]["allowed_domains"] = domains
    with pytest.raises(PolicyError):
        parse_policy(config)


@pytest.mark.parametrize("flag", [None, 0, 1, "true", [], {}])
def test_subdomain_flag_is_strictly_boolean(config, flag):
    config["tools"]["send_email"]["allow_subdomains"] = flag
    with pytest.raises(PolicyError):
        parse_policy(config)


def test_valid_resource_variants(config):
    domains = ["a" * 63 + ".fr", "maintenance.entreprise.fr", "xn--mnchen-3ya.de",
               ".".join(["a" * 63] * 3 + ["a" * 61])]
    config["tools"]["send_email"].update(allowed_domains=domains, allow_subdomains=False)
    config["tools"]["write_file"]["allowed_directory"] = "/var/supervision/été/"
    policy = parse_policy(config)
    assert policy.tools["send_email"].allowed_domains == tuple(domains)
    assert policy.tools["send_email"].allow_subdomains is False
    assert policy.tools["write_file"].allowed_directory.endswith("été/")


@pytest.mark.parametrize("score", [-1, 2, False, "0.5", [], {}, float("nan"), float("inf")])
def test_invalid_scores_rejected_for_every_tool(config, score):
    for rule in config["tools"].values():
        original = rule["minimum_confidence"]
        rule["minimum_confidence"] = score
        with pytest.raises(PolicyError, match="minimum_confidence"):
            parse_policy(config)
        rule["minimum_confidence"] = original


def test_default_contract_matches_readme():
    policy = load_policy()
    assert policy.version == "axis-c-policy-v0.1"
    for tool in ("read_log", "search_document"):
        assert policy.tools[tool].minimum_origin == "externe"
        assert policy.tools[tool].minimum_confidence is None
    assert policy.tools["send_email"].minimum_origin == "utilisateur"
    assert policy.tools["send_email"].minimum_confidence == 0.7
    assert policy.tools["send_email"].allowed_domains == ("entreprise.fr",)
    assert policy.tools["send_email"].allow_subdomains is True
    for tool in ("restart_equipment", "write_file"):
        assert policy.tools[tool].minimum_origin == "interne"
        assert policy.tools[tool].minimum_confidence == 0.5
    assert policy.tools["write_file"].allowed_directory == "/var/supervision/"


@pytest.mark.parametrize("directory", [None, [], True, "", "/var/./supervision/",
                                      "/var/\nsupervision/", "/var/\x7fsupervision/",
                                      "/var/\ud800/", "/var/\udfff/"])
def test_directory_type_and_encoding(config, directory):
    config["tools"]["write_file"]["allowed_directory"] = directory
    with pytest.raises(PolicyError):
        parse_policy(config)


@pytest.mark.parametrize("text", [
    '{"tools":{"read_log":{},"read_log":{}}}',
    '{"tools":{"read_log":{"minimum_origin":"externe","minimum_origin":"systeme"}}}',
    "null", "[]", "{} trailing", "NaN", "Infinity", "-Infinity",
])
def test_invalid_file_content(tmp_path, text):
    path = tmp_path / "invalid.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(PolicyError):
        load_policy(path)


def test_bad_encoding_and_directory_input(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_bytes(b"\xff\xfe")
    with pytest.raises(PolicyError):
        load_policy(path)
    with pytest.raises(PolicyError):
        load_policy(tmp_path)


def test_nested_immutability_and_isolation(config):
    policy = parse_policy(config)
    rule = policy.tools["send_email"]
    with pytest.raises(FrozenInstanceError):
        policy.version = "changed"
    with pytest.raises(FrozenInstanceError):
        rule.minimum_origin = "externe"
    with pytest.raises(TypeError):
        rule.allowed_domains[0] = "external.net"
    with pytest.raises(TypeError):
        ORIGIN_LEVELS["externe"] = 4
    config["tools"]["send_email"]["allowed_domains"].append("external.net")
    assert rule.allowed_domains == ("entreprise.fr",)
    config["tools"]["send_email"]["minimum_confidence"] = -1
    with pytest.raises(PolicyError):
        parse_policy(config)
    assert rule.minimum_confidence == 0.7


@pytest.mark.parametrize("change", ["version", "domain", "subdomains", "directory", "origin"])
def test_fingerprint_changes_for_relevant_edits(config, change):
    before = parse_policy(config).sha256
    if change == "version":
        config["version"] = "axis-c-policy-v0.2"
    elif change == "domain":
        config["tools"]["send_email"]["allowed_domains"] = ["other.fr"]
    elif change == "subdomains":
        config["tools"]["send_email"]["allow_subdomains"] = False
    elif change == "directory":
        config["tools"]["write_file"]["allowed_directory"] = "/var/reports/"
    else:
        config["tools"]["send_email"]["minimum_origin"] = "systeme"
    assert parse_policy(config).sha256 != before


def test_real_cli_reproducibility_and_no_rewrite(tmp_path, config):
    def reverse_keys(obj):
        if isinstance(obj, dict):
            return {k: reverse_keys(v) for k, v in reversed(list(obj.items()))}
        return obj
    path = tmp_path / "custom policy.json"
    path.write_text(json.dumps(reverse_keys(config), indent=4), encoding="utf-8")
    before = path.read_bytes()
    first = cli(tmp_path)
    second = cli(tmp_path, path)
    expected = hashlib.sha256(json.dumps(config, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    for result in (first, second):
        assert result.returncode == 0, result.stderr
        assert result.stderr == ""
        report = json.loads(result.stdout)
        assert report["sha256"] == expected
        assert report["version"] == config["version"]
        assert report["tools"] == sorted(config["tools"])
        assert report["default_effect"] == "deny"
        assert report["status"] == "configuration_validated_not_enforced"
    assert path.read_bytes() == before


@pytest.mark.parametrize("case", ["missing", "json", "schema", "utf8", "duplicate", "surrogate"])
def test_real_cli_failure_contract(tmp_path, config, case):
    path = tmp_path / "invalid.json"
    if case == "json":
        path.write_text("{", encoding="utf-8")
    elif case == "schema":
        path.write_text("{}", encoding="utf-8")
    elif case == "utf8":
        path.write_bytes(b"\xff")
    elif case == "duplicate":
        path.write_text('{"version":"v1","version":"v2"}', encoding="utf-8")
    elif case == "surrogate":
        config["tools"]["write_file"]["allowed_directory"] = "/var/\ud800/"
        path.write_text(json.dumps(config), encoding="utf-8")
    result = cli(tmp_path, path)
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr
