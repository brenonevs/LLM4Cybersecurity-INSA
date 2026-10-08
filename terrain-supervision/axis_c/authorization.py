"""Deterministic call authorization; no tool execution or model inference."""
from dataclasses import dataclass
import math
import posixpath
import re
from types import MappingProxyType

from .policy import ORIGIN_LEVELS, _domain

SCHEMAS = MappingProxyType({name: frozenset(fields) for name, fields in {
    "read_log": {"equipement"},
    "search_document": {"requete"},
    "restart_equipment": {"equipement"},
    "send_email": {"destinataire", "sujet", "corps"},
    "write_file": {"chemin", "contenu"},
}.items()})


@dataclass(frozen=True)
class Attributes:
    origin: str = None
    confidence: float = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    policy_version: str
    policy_sha256: str


def decide(policy, tool, args, attributes):
    """Evaluate a validated policy against untrusted call data."""
    def result(reason):
        return Decision(reason == "allowed", reason, policy.version, policy.sha256)

    if not isinstance(tool, str) or tool not in SCHEMAS or tool not in policy.tools:
        return result("unknown_tool")
    if (not isinstance(args, dict) or set(args) != SCHEMAS[tool]
            or any(not isinstance(v, str) for v in args.values())):
        return result("invalid_arguments")
    rule = policy.tools[tool]
    if (not isinstance(attributes, Attributes)
            or not isinstance(attributes.origin, str)
            or attributes.origin not in ORIGIN_LEVELS):
        return result("missing_or_invalid_origin")
    if ORIGIN_LEVELS[attributes.origin] < ORIGIN_LEVELS[rule.minimum_origin]:
        return result("insufficient_origin")
    if rule.minimum_confidence is not None:
        score = attributes.confidence
        if (type(score) not in (int, float) or not 0 <= score <= 1
                or not math.isfinite(score)):
            return result("missing_or_invalid_confidence")
        if score < rule.minimum_confidence:
            return result("insufficient_confidence")
    if tool == "send_email":
        address = args["destinataire"]
        if address.count("@") != 1 or len(address) > 254:
            return result("invalid_recipient")
        local, domain = address.split("@")
        if (not 1 <= len(local) <= 64 or not _domain(domain.lower())
                or not all(re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+", atom)
                           for atom in local.split("."))):
            return result("invalid_recipient")
        domain = domain.lower()
        if not any(domain == allowed or (rule.allow_subdomains
                   and domain.endswith("." + allowed)) for allowed in rule.allowed_domains):
            return result("recipient_not_allowed")
    if tool == "write_file":
        path = args["chemin"]
        if (not path.startswith("/") or path.startswith("//") or path.endswith("/")
                or "\\" in path or path != posixpath.normpath(path)
                or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF
                       for c in path)):
            return result("invalid_path")
        if not path.startswith(rule.allowed_directory):
            return result("path_not_allowed")
    if tool in ("restart_equipment", "read_log") and not args["equipement"].strip():
        return result("invalid_arguments")
    return result("allowed")


class DefaultProvider:
    """No causal attribution: conservative reads, unknown action attributes."""
    mode = "unconfigured"

    def reset(self):
        pass

    def observe(self, fragment):
        pass

    def attributes(self, tool, args):
        return Attributes("externe") if tool in ("read_log", "search_document") else Attributes()


@dataclass(frozen=True)
class AuditEntry:
    task_generation: int
    tool: str
    provider_mode: str
    decision: Decision


class AuthorizationSession:
    """Trusted provider implements mode, reset, observe and attributes(tool, args).

    A provider instance belongs to one session; do not share mutable providers
    between agents. Providers are trusted host code, never model-selected.
    """
    def __init__(self, policy, provider=None):
        self.policy = policy
        self.provider = provider if provider is not None else DefaultProvider()
        if not isinstance(self.provider.mode, str) or not self.provider.mode:
            raise ValueError("provider mode must be a nonempty string")
        self.mode = self.provider.mode
        self.generation = 0
        self._audit = []
        self._failed = False
        self.reset()

    @property
    def audit(self):
        return tuple(self._audit)

    def reset(self):
        self.generation += 1
        self._audit.clear()
        self._failed = True
        try:
            self.provider.reset()
        except Exception:
            return
        self._failed = False

    def observe(self, fragment):
        if not self._failed:
            try:
                self.provider.observe(fragment)
            except Exception:
                self._failed = True

    def verify(self, tool, args):
        if not self._failed:
            try:
                # Schema validation also occurs in decide; only strings reach providers.
                if not isinstance(args, dict) or any(not isinstance(v, str) for v in args.values()):
                    attributes = Attributes()
                else:
                    attributes = self.provider.attributes(tool, MappingProxyType(dict(args)))
            except Exception:
                self._failed = True
        if self._failed:
            decision = Decision(False, "attribute_provider_error", self.policy.version, self.policy.sha256)
        else:
            decision = decide(self.policy, tool, args, attributes)
        self._audit.append(AuditEntry(self.generation, tool, self.mode, decision))
        return None if decision.allowed else decision.reason
