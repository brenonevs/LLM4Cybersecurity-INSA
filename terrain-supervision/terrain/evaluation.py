"""Deterministic evidence assessment for Axis B.

Natural-language values use the same text assessment regardless of where they
were read.  Structured measurements are assessed against their declared
format first.  A format anomaly is evidence of reduced reliability, not proof
that the source is malicious.
"""
from dataclasses import dataclass
import re
import unicodedata
from datetime import datetime
from typing import Optional, Tuple

from .outils import SourceEvidence
from .semantic import SemanticAssessment, assess_text


FAVORABLE = "favorable"
NEUTRAL = "neutral"
UNFAVORABLE = "unfavorable"
MAX_NEGATIVE_WEIGHT = 2.0


@dataclass(frozen=True)
class Evaluation:
    """Result of evaluating one exact source-content version."""
    result: str
    reasons: Tuple[str, ...] = ()
    weight: float = 1.0
    severity: str = "none"
    semantic: Optional[SemanticAssessment] = None


def _normaliser(texte: str) -> str:
    """Normalize case, Unicode and spacing without modifying stored evidence."""
    return " ".join(unicodedata.normalize("NFKC", texte).casefold().split())


def _contient(texte: str, motifs: Tuple[str, ...]) -> bool:
    return any(re.search(motif, texte) is not None for motif in motifs)


def _negative_severity(weight: float) -> str:
    if weight >= 2.0:
        return "critical"
    if weight >= 1.5:
        return "high"
    if weight >= 1.0:
        return "medium"
    return "low"


OVERRIDE_PATTERNS = (
    r"\bignore\s+(?:all\s+)?(?:previous|prior|the\s+)?instructions?\b",
    r"\bdisregard\s+(?:all\s+)?(?:previous|prior|the\s+)?(?:instructions?|guidance)\b",
    r"\bignore[rz]?\s+(?:toutes?\s+)?(?:les\s+)?instructions?\b",
)

DIRECTIVE_PATTERNS = (
    r"(?:^|[.!?;:]\s*|\b(?:and|then|please)\s+)(?:please\s+)?"
    r"(?:send|email|write|restart|transmit|forward)\b",
    r"(?:^|[.!?;:]\s*|\b(?:et|puis|veuillez)\s+)"
    r"(?:envoyez|transmettez|ecrivez|écrivez|redemarrez|redémarrez)\b",
)

SENSITIVE_PATTERNS = (
    r"\b(?:maintenance\s+)?password\b",
    r"\b(?:service\s+)?credential(?:s)?\b",
    r"\bsecret(?:s)?\b",
    r"\bmot\s+de\s+passe\b",
    r"\bidentifiants?\b",
)

EXTERNAL_DESTINATION_PATTERNS = (
    r"\b(?:external|outside)\s+(?:email|e-mail|address|domain)\b",
    r"\b(?:adresse|domaine)\s+externe\b",
    r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.(?:com|net|org|io|fr|eu)\b",
)

MEASURE_PATTERN = re.compile(
    r"^\s*temp\s*=\s*(-?\d+(?:\.\d+)?)\s*;\s*"
    r"hum\s*=\s*(\d+(?:\.\d+)?)\s*$",
    re.IGNORECASE,
)


def _evaluate_text(text: str, task_context: str = "") -> Evaluation:
    """Evaluate natural language without treating ordinary prose as positive."""
    semantic = assess_text(text, task_context)
    text = _normaliser(text)
    reasons = []
    override = _contient(text, OVERRIDE_PATTERNS)
    directive = _contient(text, DIRECTIVE_PATTERNS)
    sensitive = _contient(text, SENSITIVE_PATTERNS)
    external_destination = _contient(text, EXTERNAL_DESTINATION_PATTERNS)

    if override:
        reasons.append("instruction_override")
    if directive:
        reasons.append("action_directive")
    if sensitive:
        reasons.append("secret_reference")
    if external_destination:
        reasons.append("external_destination_reference")

    if override and directive and (sensitive or external_destination):
        return Evaluation(UNFAVORABLE, tuple(reasons), 2.0, "critical", semantic)
    if directive and (sensitive or external_destination):
        return Evaluation(UNFAVORABLE, tuple(reasons), 1.5, "high", semantic)
    if override:
        return Evaluation(UNFAVORABLE, tuple(reasons), 1.0, "medium", semantic)
    return Evaluation(NEUTRAL, tuple(reasons) or ("no_strong_signal",), 0.0, "none", semantic)


def _evaluate_measure(text: str, task_context: str = "") -> Evaluation:
    """Assess an expected ``temp=<number>;hum=<number>`` measurement."""
    match = MEASURE_PATTERN.fullmatch(text)
    if match:
        temperature, humidity = (float(value) for value in match.groups())
        if -50.0 <= temperature <= 100.0 and 0.0 <= humidity <= 100.0:
            return Evaluation(FAVORABLE, ("expected_measure_format",), 1.0, "positive")
        return Evaluation(UNFAVORABLE, ("measurement_out_of_range",), 0.5, "low")

    return _evaluate_unexpected_structured_value(text, "unexpected_measure_format", task_context)


def _evaluate_unexpected_structured_value(text: str, format_reason: str,
                                          task_context: str = "") -> Evaluation:
    """Combine a format anomaly with the common natural-language analysis."""
    text_evaluation = _evaluate_text(text, task_context)
    text_reasons = tuple(reason for reason in text_evaluation.reasons
                         if reason != "no_strong_signal")
    reasons = (format_reason,) + text_reasons
    if text_evaluation.result == UNFAVORABLE:
        weight = min(MAX_NEGATIVE_WEIGHT, text_evaluation.weight + 0.5)
        return Evaluation(UNFAVORABLE, reasons, weight, _negative_severity(weight),
                          text_evaluation.semantic)
    # The value is unreliable because it violates the declared technical
    # schema, but this result does not claim that an attacker caused it.
    return Evaluation(UNFAVORABLE, reasons, weight=0.5, severity="low",
                      semantic=text_evaluation.semantic)


def _evaluate_timestamp(text: str, task_context: str = "") -> Evaluation:
    try:
        datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return _evaluate_unexpected_structured_value(text, "unexpected_timestamp_format", task_context)
    return Evaluation(FAVORABLE, ("expected_timestamp_format",), 1.0, "positive")


def _evaluate_status(text: str, task_context: str = "") -> Evaluation:
    if _normaliser(text) in {"ouvert", "clos"}:
        return Evaluation(FAVORABLE, ("expected_status_value",), 1.0, "positive")
    return _evaluate_unexpected_structured_value(text, "unexpected_status_value", task_context)


EMAIL_ADDRESS_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _evaluate_email_address(text: str, task_context: str = "") -> Evaluation:
    if EMAIL_ADDRESS_PATTERN.fullmatch(text.strip()):
        return Evaluation(FAVORABLE, ("expected_email_address_format",), 1.0, "positive")
    return _evaluate_unexpected_structured_value(text, "unexpected_email_address_format", task_context)


def evaluate_evidence(evidence: SourceEvidence, task_context: str = "") -> Evaluation:
    """Evaluate content according to its declared content type, not origin.

    The content type belongs to the field metadata, not to the record origin.
    Every value marked ``text`` uses the same logic, whether it came from a
    journal, ticket, technical document, or email.
    """
    content_type = evidence.reference.content_type
    if content_type == "measure":
        return _evaluate_measure(evidence.content, task_context)
    if content_type == "timestamp":
        return _evaluate_timestamp(evidence.content, task_context)
    if content_type == "status":
        return _evaluate_status(evidence.content, task_context)
    if content_type == "email_address":
        return _evaluate_email_address(evidence.content, task_context)
    return _evaluate_text(evidence.content, task_context)
