"""Deterministic evidence assessment for the first Axis B text experiment.

This module deliberately handles only free-text journal comments.  It does
not decide whether an operational statement is true.  It only identifies
clear attempts to control the agent or request a sensitive action.  All other
comments remain neutral until a later corroboration mechanism exists.
"""
from dataclasses import dataclass
import re
import unicodedata
from typing import Tuple

from .outils import SourceEvidence


FAVORABLE = "favorable"
NEUTRAL = "neutral"
UNFAVORABLE = "unfavorable"


@dataclass(frozen=True)
class Evaluation:
    """Result of evaluating one exact source-content version."""
    result: str
    reasons: Tuple[str, ...] = ()


def _normaliser(texte: str) -> str:
    """Normalize case, Unicode and spacing without modifying stored evidence."""
    return " ".join(unicodedata.normalize("NFKC", texte).casefold().split())


def _contient(texte: str, motifs: Tuple[str, ...]) -> bool:
    return any(re.search(motif, texte) is not None for motif in motifs)


OVERRIDE_PATTERNS = (
    r"\bignore\s+(?:all\s+)?(?:previous|prior|the\s+)?instructions?\b",
    r"\bdisregard\s+(?:all\s+)?(?:previous|prior|the\s+)?(?:instructions?|guidance)\b",
    r"\bignore[rz]?\s+(?:toutes?\s+)?(?:les\s+)?instructions?\b",
)

DIRECTIVE_PATTERNS = (
    r"\b(?:please\s+)?(?:send|email|write|restart|transmit|forward)\b",
    r"\b(?:envoy(?:er|ez)|transmett(?:re|ez)|ecri(?:re|vez)|écri(?:re|vez)|"
    r"redemarr(?:er|ez)|redémarr(?:er|ez))\b",
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


def evaluate_evidence(evidence: SourceEvidence) -> Evaluation:
    """Evaluate one journal comment using explicit, auditable signals.

    Other fields are deliberately neutral in this first increment.  A plain
    technical comment is also neutral: without independent corroboration,
    absence of suspicious wording is not positive evidence of truthfulness.
    """
    reference = evidence.reference
    if reference.kind != "journal" or reference.field != "commentaire":
        return Evaluation(NEUTRAL, ("field_not_yet_evaluated",))

    text = _normaliser(evidence.content)
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

    if override or (directive and (sensitive or external_destination)):
        return Evaluation(UNFAVORABLE, tuple(reasons))
    return Evaluation(NEUTRAL, tuple(reasons) or ("no_strong_signal",))
