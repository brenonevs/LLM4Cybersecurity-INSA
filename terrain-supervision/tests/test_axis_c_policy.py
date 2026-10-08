"""Configuration failures must be explicit before an Axis C experiment starts."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from axis_c.policy import DEFAULT_POLICY, PolicyError, load_policy, parse_policy
from terrain.outils import Outils


@pytest.fixture
def config():
    return json.loads(DEFAULT_POLICY.read_text(encoding="utf-8"))


def test_contract_matches_frozen_tools_and_assignment():
    policy = load_policy()
    assert set(policy.tools) == set(Outils.NOMS)
    assert policy.tools["send_email"].minimum_origin == "utilisateur"
    assert policy.tools["send_email"].minimum_confidence == 0.7
    assert policy.tools["restart_equipment"].minimum_confidence == 0.5
    assert policy.tools["write_file"].allowed_directory == "/var/supervision/"


def test_hash_identifies_content_and_ignores_key_order(config):
    first = parse_policy(config)
    reordered = dict(reversed(list(config.items())))
    assert first.sha256 == parse_policy(reordered).sha256
    config["tools"]["send_email"]["minimum_confidence"] = 0.8
    assert first.sha256 != parse_policy(config).sha256
    assert first.tools["send_email"].minimum_confidence == 0.7
    with pytest.raises(TypeError):
        first.tools["send_email"] = None


@pytest.mark.parametrize("value", [-0.1, 1.1, True, "0.7", float("nan"), float("inf"), {}])
def test_invalid_confidence_is_rejected(config, value):
    config["tools"]["send_email"]["minimum_confidence"] = value
    with pytest.raises(PolicyError, match="minimum_confidence"):
        parse_policy(config)


@pytest.mark.parametrize("domain", ["*.entreprise.fr", "user@entreprise.fr", "https://entreprise.fr",
                                   "Entreprise.fr", "entreprise.fr.", "-x.fr", "x..fr", ""])
def test_ambiguous_domains_are_rejected(config, domain):
    config["tools"]["send_email"]["allowed_domains"] = [domain]
    with pytest.raises(PolicyError, match="allowed_domains"):
        parse_policy(config)


@pytest.mark.parametrize("path", ["/", "var/supervision/", "/var/supervision/../",
                                 "/var//supervision/", "//var/supervision/", "/var/supervision",
                                 "/var/\x00supervision/", "/var/supervision\\/"])
def test_unsafe_directory_configurations_are_rejected(config, path):
    config["tools"]["write_file"]["allowed_directory"] = path
    with pytest.raises(PolicyError, match="POSIX directory"):
        parse_policy(config)


@pytest.mark.parametrize("mutation", ["extra", "missing_tool", "unknown_tool", "origin", "allow"])
def test_incomplete_or_unknown_policy_is_rejected(config, mutation):
    if mutation == "extra":
        config["tools"]["send_email"]["min_confidance"] = 0.9
    elif mutation == "missing_tool":
        del config["tools"]["read_log"]
    elif mutation == "unknown_tool":
        config["tools"]["read_file"] = config["tools"]["read_log"]
    elif mutation == "origin":
        config["tools"]["read_log"]["minimum_origin"] = "trusted"
    else:
        config["default_effect"] = "allow"
    with pytest.raises(PolicyError):
        parse_policy(config)


def test_duplicate_keys_are_rejected(tmp_path):
    path = tmp_path / "policy.json"
    path.write_text('{"default_effect":"deny","default_effect":"allow"}', encoding="utf-8")
    with pytest.raises(PolicyError, match="duplicate JSON key"):
        load_policy(path)


def test_invalid_json_and_missing_file_are_reported(tmp_path):
    path = tmp_path / "policy.json"
    with pytest.raises(PolicyError, match="cannot read policy"):
        load_policy(path)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(PolicyError, match="cannot read policy"):
        load_policy(path)
