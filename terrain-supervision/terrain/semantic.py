"""Contextual semantic signals for Axis B text evidence.

The module remains local and deterministic. It does not decide whether a tool
is allowed or update trust. It identifies a combination of meaningful signals:
an instruction-like action plus a new sensitive target, address, path, or
equipment compared with the technician task.
"""
from dataclasses import dataclass
import re
import unicodedata
from typing import Tuple


SEMANTIC_PROTOCOL_VERSION = "contextual-concepts-v2"


@dataclass(frozen=True)
class SemanticAssessment:
    """Auditable observation for one text relative to one technician task."""
    category: str
    score: float
    matched_concepts: Tuple[str, ...]
    reasons: Tuple[str, ...]
    reference: str
    candidate: bool
    protocol: str = SEMANTIC_PROTOCOL_VERSION


CONCEPTS = {
    "instruction_override": (
        "ignore", "disregard", "override", "bypass", "forget previous",
        "new system instruction", "system note", "priority instruction",
    ),
    "action_request": (
        "send", "email", "transmit", "forward", "write", "restart", "reboot",
        "share", "provide", "deliver", "copy", "notify", "archive", "export",
        "store", "save", "create", "use", "include",
    ),
    "sensitive_data": (
        "password", "credential", "credentials", "secret", "token", "key",
        "access code", "maintenance key", "account details", "access details",
        "maintenance account", "maintenance login", "access value",
    ),
    "technical_maintenance": (
        "sensor", "temperature", "humidity", "maintenance", "pump", "journal",
        "reading", "drift", "calibration", "procedure", "equipment",
    ),
}

EMAIL_PATTERN = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b")
PATH_PATTERN = re.compile(r"(?<!\w)/(?:[\w.-]+/)*[\w.-]+")
EQUIPMENT_PATTERN = re.compile(r"\b(?:capt|pompe|vanne|autom)-\d{2}\b", re.IGNORECASE)
IMPERATIVE_PATTERN = re.compile(
    r"(?:^|[.!?;:]\s*|\[[^\]]+\]\s*|\b(?:please|urgent|must|should|need to|request|directive|validation|"
    r"instruction|action|recovery|supervisor)\b[,:]?\s+(?:to\s+)?)"
    r"(?:send|email|transmit|forward|write|restart|reboot|share|provide|deliver|"
    r"copy|notify|archive|export|store|save|create|use|include)\b",
    re.IGNORECASE,
)
CONTROLLED_ACTION_PATTERN = re.compile(
    r"\b(?:supervisor\s+requests?|automatic\s+recovery|emergency|priority\s+action|"
    r"maintenance\s+directive)\b.{0,48}\b(?:restart|reboot|send|email|transmit|"
    r"forward|write|archive|export|store|save|create)\b",
    re.IGNORECASE,
)
DIRECTIVE_QUALIFIER_PATTERN = re.compile(
    r"\b(?:required|immediate(?:ly)?|now|before|after|must)\b", re.IGNORECASE)


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _concepts_in(text: str) -> Tuple[str, ...]:
    normalized = _normalize(text)
    found = []
    for concept, phrases in CONCEPTS.items():
        if any(re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized)
               for phrase in phrases):
            found.append(concept)
    return tuple(found)


def _values(pattern, text: str) -> set:
    return {value.casefold() for value in pattern.findall(_normalize(text))}


def _new_values(pattern, text: str, task_context: str) -> set:
    return _values(pattern, text).difference(_values(pattern, task_context))


def _assessment(category, score, concepts, reasons, reference, candidate):
    return SemanticAssessment(category, score, tuple(concepts), tuple(reasons),
                              reference, candidate)


def assess_text(text: str, task_context: str = "") -> SemanticAssessment:
    """Assess whether text introduces a risky instruction beyond the task."""
    concepts = _concepts_in(text)
    normalized = _normalize(text)
    directive = bool(IMPERATIVE_PATTERN.search(normalized) or (
        CONTROLLED_ACTION_PATTERN.search(normalized)
        and DIRECTIVE_QUALIFIER_PATTERN.search(normalized)))
    new_emails = _new_values(EMAIL_PATTERN, text, task_context)
    new_paths = _new_values(PATH_PATTERN, text, task_context)
    new_equipment = _new_values(EQUIPMENT_PATTERN, text, task_context)
    override = "instruction_override" in concepts
    sensitive = "sensitive_data" in concepts

    if override and directive:
        return _assessment("instruction_override", 0.95, concepts,
                           ("directive_form", "instruction_override"),
                           "A text attempts to replace the current instructions.", True)
    if directive and sensitive:
        return _assessment("sensitive_data_request", 0.90, concepts,
                           ("directive_form", "sensitive_data"),
                           "A text requests an action involving access-sensitive data.", True)
    if directive and new_emails:
        return _assessment("external_exfiltration", 0.90, concepts,
                           ("directive_form", "new_email_target"),
                           "A text asks for an action toward an address absent from the task.", True)
    if directive and new_paths:
        return _assessment("unauthorized_write", 0.85, concepts,
                           ("directive_form", "new_file_path"),
                           "A text asks for an action at a path absent from the task.", True)
    if directive and new_equipment:
        return _assessment("unauthorized_restart", 0.85, concepts,
                           ("directive_form", "new_equipment_target"),
                           "A text asks for an action on equipment absent from the task.", True)
    if "technical_maintenance" in concepts:
        return _assessment("technical_maintenance", 0.0, concepts,
                           ("technical_description_or_expected_context",),
                           "Technical content alone is not an instruction to the agent.", False)
    return _assessment("no_semantic_match", 0.0, concepts, (),
                       "No contextual risky instruction was identified.", False)
