"""Evidence assessment for Axis B.

Natural-language values use the same text assessment regardless of where they
were read.  Structured measurements are assessed against their declared
format first.  A format anomaly is evidence of reduced reliability, not proof
that the source is malicious.  An optional embedding assessor may add one
bounded support signal when independent evidence is already present.
"""
from dataclasses import dataclass, replace
import re
import unicodedata
from datetime import datetime
from typing import Optional, Tuple

from .embeddings import (
    EMBEDDING_SUPPORT_STRONG_WEIGHT,
    EMBEDDING_SUPPORT_TARGET_WEIGHT,
    EmbeddingAssessment,
)
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
    signals: Tuple["EvidenceSignal", ...] = ()
    embedding: Optional[EmbeddingAssessment] = None
    lexical_checks: Tuple[Tuple[str, bool], ...] = ()


@dataclass(frozen=True)
class EvidenceSignal:
    """One auditable contribution to an unfavorable content assessment."""
    kind: str
    weight: float
    origin: str


def _combine_negative(reasons, signals, semantic=None, embedding=None) -> Evaluation:
    """Keep the strongest weight for each evidence type, then cap one version."""
    strongest = {}
    for signal in signals:
        previous = strongest.get(signal.kind)
        if previous is None or signal.weight > previous.weight:
            strongest[signal.kind] = signal
    selected = tuple(strongest.values())
    weight = min(MAX_NEGATIVE_WEIGHT, sum(signal.weight for signal in selected))
    return Evaluation(UNFAVORABLE, tuple(reasons), weight,
                      _negative_severity(weight), semantic, selected, embedding)


def _support_weight(signals, assessment) -> float:
    """Let embedding reinforce an independent finding without acting alone."""
    if assessment is None or not assessment.qualified:
        return 0.0
    kinds = {signal.kind for signal in signals}
    if "instruction_override" in kinds or "sensitive_data" in kinds:
        return EMBEDDING_SUPPORT_STRONG_WEIGHT
    if "agent_directive" in kinds and "new_target" in kinds:
        return EMBEDDING_SUPPORT_TARGET_WEIGHT
    return 0.0


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


def _evaluate_text(text: str, task_context: str = "", embedding_assessor=None) -> Evaluation:
    """Evaluate natural language without treating ordinary prose as positive."""
    original = text
    semantic = assess_text(original, task_context)
    text = _normaliser(original)
    reasons = []
    override = _contient(text, OVERRIDE_PATTERNS)
    directive = _contient(text, DIRECTIVE_PATTERNS)
    sensitive = _contient(text, SENSITIVE_PATTERNS)
    external_destination = _contient(text, EXTERNAL_DESTINATION_PATTERNS)
    lexical_checks = (
        ("instruction_override", override),
        ("action_directive", directive),
        ("secret_reference", sensitive),
        ("external_destination_reference", external_destination),
    )

    if override:
        reasons.append("instruction_override")
    if directive:
        reasons.append("action_directive")
    if sensitive:
        reasons.append("secret_reference")
    if external_destination:
        reasons.append("external_destination_reference")

    signals = []
    if override:
        signals.append(EvidenceSignal("instruction_override", 1.0, "lexical"))
    if directive:
        signals.append(EvidenceSignal("agent_directive", 0.5, "lexical"))
        if sensitive:
            signals.append(EvidenceSignal("sensitive_data", 1.0, "lexical"))
        if external_destination:
            signals.append(EvidenceSignal("new_target", 1.0, "lexical"))

    if semantic.candidate:
        reasons.append("semantic_" + semantic.category)
        if semantic.category == "instruction_override":
            signals.append(EvidenceSignal("instruction_override", 0.75, "contextual"))
        elif semantic.category == "sensitive_data_request":
            signals.extend((EvidenceSignal("agent_directive", 0.5, "syntactic"),
                            EvidenceSignal("sensitive_data", 0.75, "contextual")))
        elif semantic.category in {"external_exfiltration", "unauthorized_write",
                                   "unauthorized_restart"}:
            signals.extend((EvidenceSignal("agent_directive", 0.5, "syntactic"),
                            EvidenceSignal("new_target", 0.75, "contextual")))

    assessment = None
    if embedding_assessor is not None:
        assessment = embedding_assessor.assess(original)
        support = _support_weight(signals, assessment)
        assessment = replace(assessment, support_weight=support)
        if support > 0:
            reasons.append("embedding_support")
            signals.append(EvidenceSignal("embedding_support", support, "embedding"))

    if signals:
        return replace(_combine_negative(reasons, signals, semantic, assessment),
                       lexical_checks=lexical_checks)
    return Evaluation(NEUTRAL, tuple(reasons) or ("no_strong_signal",), 0.0, "none",
                      semantic, (), assessment, lexical_checks)


def _evaluate_measure(text: str, task_context: str = "", embedding_assessor=None) -> Evaluation:
    """Assess an expected ``temp=<number>;hum=<number>`` measurement."""
    match = MEASURE_PATTERN.fullmatch(text)
    if match:
        temperature, humidity = (float(value) for value in match.groups())
        if -50.0 <= temperature <= 100.0 and 0.0 <= humidity <= 100.0:
            return Evaluation(FAVORABLE, ("expected_measure_format",), 1.0, "positive")
        return Evaluation(UNFAVORABLE, ("measurement_out_of_range",), 0.5, "low")

    return _evaluate_unexpected_structured_value(
        text, "unexpected_measure_format", task_context, embedding_assessor)


def _evaluate_unexpected_structured_value(text: str, format_reason: str,
                                          task_context: str = "",
                                          embedding_assessor=None) -> Evaluation:
    """Combine a format anomaly with the common natural-language analysis."""
    text_evaluation = _evaluate_text(text, task_context, embedding_assessor)
    text_reasons = tuple(reason for reason in text_evaluation.reasons
                         if reason != "no_strong_signal")
    reasons = (format_reason,) + text_reasons
    if text_evaluation.result == UNFAVORABLE:
        return _combine_negative(reasons, text_evaluation.signals + (
            EvidenceSignal("structural_anomaly", 0.5, "structured"),),
            text_evaluation.semantic, text_evaluation.embedding)
    # The value is unreliable because it violates the declared technical
    # schema, but this result does not claim that an attacker caused it.
    return _combine_negative(reasons, (EvidenceSignal("structural_anomaly", 0.5,
                                                       "structured"),),
                             text_evaluation.semantic, text_evaluation.embedding)


def _evaluate_timestamp(text: str, task_context: str = "", embedding_assessor=None) -> Evaluation:
    try:
        datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return _evaluate_unexpected_structured_value(
            text, "unexpected_timestamp_format", task_context, embedding_assessor)
    return Evaluation(FAVORABLE, ("expected_timestamp_format",), 1.0, "positive")


def _evaluate_status(text: str, task_context: str = "", embedding_assessor=None) -> Evaluation:
    if _normaliser(text) in {"ouvert", "clos"}:
        return Evaluation(FAVORABLE, ("expected_status_value",), 1.0, "positive")
    return _evaluate_unexpected_structured_value(
        text, "unexpected_status_value", task_context, embedding_assessor)


EMAIL_ADDRESS_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _evaluate_email_address(text: str, task_context: str = "", embedding_assessor=None) -> Evaluation:
    if EMAIL_ADDRESS_PATTERN.fullmatch(text.strip()):
        return Evaluation(FAVORABLE, ("expected_email_address_format",), 1.0, "positive")
    return _evaluate_unexpected_structured_value(
        text, "unexpected_email_address_format", task_context, embedding_assessor)


def evaluate_evidence(evidence: SourceEvidence, task_context: str = "",
                      embedding_assessor=None) -> Evaluation:
    """Evaluate content according to its declared content type, not origin.

    The content type belongs to the field metadata, not to the record origin.
    Every value marked ``text`` uses the same logic, whether it came from a
    journal, ticket, technical document, or email.
    """
    content_type = evidence.reference.content_type
    if content_type == "measure":
        return _evaluate_measure(evidence.content, task_context, embedding_assessor)
    if content_type == "timestamp":
        return _evaluate_timestamp(evidence.content, task_context, embedding_assessor)
    if content_type == "status":
        return _evaluate_status(evidence.content, task_context, embedding_assessor)
    if content_type == "email_address":
        return _evaluate_email_address(evidence.content, task_context, embedding_assessor)
    return _evaluate_text(evidence.content, task_context, embedding_assessor)
