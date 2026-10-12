"""Local dependency-parser observations for Axis B text evidence.

The parser identifies grammatical action requests; it never authorizes a tool
and never decides that a text is malicious by itself.  Its output is combined
with lexical and contextual evidence in ``evaluation.py``.
"""
from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Optional, Tuple


SYNTAX_PROTOCOL_VERSION = "spacy-dependency-v1"
SPACY_MODEL = "en_core_web_sm"

ACTION_VERBS = {
    "send", "email", "forward", "write", "restart", "reboot", "transmit",
    "share", "provide", "deliver", "copy", "notify", "archive", "export",
    "store", "save", "create", "use", "include",
}
EMAIL_PATTERN = re.compile(r"\b[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}\b", re.IGNORECASE)
PATH_PATTERN = re.compile(r"(?<!\w)/(?:[\w.-]+/)*[\w.-]+")
EQUIPMENT_PATTERN = re.compile(r"\b(?:capt|pompe|vanne|autom)-\d{2}\b", re.IGNORECASE)


@dataclass(frozen=True)
class SyntacticAssessment:
    """Auditable grammatical structure of one text field."""
    available: bool
    protocol: str
    action_verb: Optional[str] = None
    imperative: bool = False
    negated: bool = False
    passive: bool = False
    object_text: Optional[str] = None
    target: Optional[str] = None
    target_kind: Optional[str] = None
    candidate: bool = False
    reasons: Tuple[str, ...] = ()


@lru_cache(maxsize=1)
def _pipeline():
    """Load the pinned local English parser only when text is assessed."""
    try:
        import spacy
    except ImportError:
        return None
    try:
        return spacy.load(SPACY_MODEL)
    except OSError:
        return None


def _is_imperative(sentence, root) -> bool:
    """Recognize English commands while excluding declarative/passive clauses."""
    children = tuple(root.children)
    if any(child.dep_ in {"nsubj", "nsubjpass", "csubj"} for child in children):
        return False
    # English imperative verbs conventionally have the base form VB and no
    # expressed subject; spaCy keeps this invariant for "Do not restart".
    if root.pos_ in {"VERB", "AUX"} and root.tag_ == "VB":
        return True
    # At the beginning of a sentence, the small English model may tag a
    # capitalized imperative such as "Forward the report" as a proper noun.
    # Its dependency root and action lemma remain usable, so recognize this
    # narrow parser ambiguity without accepting descriptive clauses.
    first_word = next((token for token in sentence if not token.is_punct), None)
    return (root == first_word and root.dep_ == "ROOT"
            and root.text.casefold() in ACTION_VERBS)


def _target(sentence, root):
    """Return a destination only when it belongs to the action clause."""
    for token in sentence:
        linked_to_root = token == root or root in tuple(token.ancestors)
        if not linked_to_root:
            continue
        value = token.text
        if token.like_email or EMAIL_PATTERN.fullmatch(value):
            return value, "email"
        if EQUIPMENT_PATTERN.fullmatch(value):
            return value, "equipment"
    text = sentence.text
    if PATH_PATTERN.search(text):
        return PATH_PATTERN.search(text).group(0), "path"
    return None, None


def assess_text(text: str) -> SyntacticAssessment:
    """Assess English imperative action structure with a local spaCy parser.

    When the optional model is unavailable, return an explicit non-candidate
    observation.  The Axis B evaluator retains its deterministic rule-based
    behavior rather than failing open or crashing a tool-reading operation.
    """
    nlp = _pipeline()
    if nlp is None:
        return SyntacticAssessment(
            False, SYNTAX_PROTOCOL_VERSION, reasons=("parser_unavailable",))

    document = nlp(text)
    for sentence in document.sents:
        root = sentence.root
        lemma = root.lemma_.casefold()
        if lemma not in ACTION_VERBS:
            continue
        children = tuple(root.children)
        negated = any(child.dep_ == "neg" for child in children)
        passive = any(child.dep_ in {"nsubjpass", "auxpass"} for child in children)
        imperative = _is_imperative(sentence, root)
        object_token = next((child for child in children
                             if child.dep_ in {"dobj", "obj", "attr"}), None)
        target, target_kind = _target(sentence, root)
        candidate = imperative and not negated and not passive
        reasons = []
        if imperative:
            reasons.append("imperative_action")
        if negated:
            reasons.append("negated_action")
        if passive:
            reasons.append("passive_description")
        if target_kind:
            reasons.append(f"action_target_{target_kind}")
        return SyntacticAssessment(
            True, SYNTAX_PROTOCOL_VERSION, lemma, imperative, negated, passive,
            None if object_token is None else object_token.text, target,
            target_kind, candidate, tuple(reasons))

    return SyntacticAssessment(
        True, SYNTAX_PROTOCOL_VERSION, reasons=("no_controlled_action_structure",))
