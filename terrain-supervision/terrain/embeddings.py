"""Local Ollama embeddings for offline evaluation and bounded beta support.

A qualified match records the margin and may add one support signal when
independent evidence is already present. It does not authorize tools.
"""
import json
from dataclasses import dataclass
from urllib import request

from .classification import ClassificationMetrics
from .embedding_dataset import (
    DEVELOPMENT, EMBEDDING_DATASET_VERSION, VALIDATION, EmbeddingExample,
)


EMBEDDING_SUPPORT_MARGIN = 0.075
EMBEDDING_SUPPORT_TARGET_WEIGHT = 0.25
EMBEDDING_SUPPORT_STRONG_WEIGHT = 0.5
EMBEDDING_SUPPORT_PROTOCOL = "embedding-support-v1"


def _input(example: EmbeddingExample) -> str:
    """Embed only the read text; task comparison stays explicit elsewhere."""
    return example.text


class OllamaEmbeddings:
    def __init__(self, model="bge-m3", host="http://localhost:11434"):
        self.model = model
        self.host = host.rstrip("/")

    def embed(self, texts):
        texts = list(texts)
        payload = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        req = request.Request(self.host + "/api/embed", data=payload,
                              headers={"Content-Type": "application/json"}, method="POST")
        with request.urlopen(req, timeout=120) as response:
            data = json.loads(response.read().decode("utf-8"))
        vectors = data.get("embeddings", [])
        if len(vectors) != len(texts):
            raise ValueError("Ollama returned an unexpected number of embedding vectors")
        return vectors


def _dot(left, right):
    return sum(a * b for a, b in zip(left, right))


def _mean_similarity(vector, references):
    return sum(_dot(vector, reference) for reference in references) / len(references)


def _closest_margin(vector, attacks_by_category, legitimate):
    category_scores = {category: _mean_similarity(vector, category_vectors)
                       for category, category_vectors in attacks_by_category.items()}
    closest_category, attack_score = max(category_scores.items(), key=lambda item: item[1])
    legitimate_score = _mean_similarity(vector, legitimate)
    return closest_category, attack_score, legitimate_score, attack_score - legitimate_score


@dataclass(frozen=True)
class EmbeddingAssessment:
    """Similarity of one read text against the frozen development references."""
    category: str
    attack_similarity: float
    legitimate_similarity: float
    margin: float
    qualified: bool
    support_weight: float = 0.0
    protocol: str = EMBEDDING_SUPPORT_PROTOCOL


class EmbeddingReferences:
    """Development attack and legitimate vectors used during a live reading."""

    def __init__(self, client):
        self.client = client
        self.model = getattr(client, "model", "unknown")
        self.protocol = (
            f"{EMBEDDING_SUPPORT_PROTOCOL}; model={self.model}; "
            f"dataset={EMBEDDING_DATASET_VERSION}; margin={EMBEDDING_SUPPORT_MARGIN:.3f}"
        )
        self._attacks_by_category = None
        self._legitimate = None
        self._cache = {}

    def _load(self):
        examples = list(DEVELOPMENT)
        vectors = self.client.embed(example.text for example in examples)
        if len(vectors) != len(examples):
            raise ValueError("Ollama returned an unexpected number of embedding vectors")
        attacks_by_category = {}
        legitimate = []
        for example, vector in zip(examples, vectors):
            if example.unfavorable:
                attacks_by_category.setdefault(example.category, []).append(vector)
            else:
                legitimate.append(vector)
        if not attacks_by_category or not legitimate:
            raise ValueError("development references must contain attacks and legitimate texts")
        self._attacks_by_category = attacks_by_category
        self._legitimate = legitimate

    def assess(self, text: str) -> EmbeddingAssessment:
        if self._attacks_by_category is None:
            self._load()
        if text not in self._cache:
            vectors = self.client.embed([text])
            if len(vectors) != 1:
                raise ValueError("Ollama returned an unexpected number of embedding vectors")
            self._cache[text] = vectors[0]
        category, attack_score, legitimate_score, score_margin = _closest_margin(
            self._cache[text], self._attacks_by_category, self._legitimate)
        return EmbeddingAssessment(
            category, attack_score, legitimate_score, score_margin,
            score_margin >= EMBEDDING_SUPPORT_MARGIN, 0.0, self.protocol)


@dataclass(frozen=True)
class EmbeddingResult:
    example: EmbeddingExample
    attack_similarity: float
    legitimate_similarity: float
    margin: float
    closest_category: str
    predicted_unfavorable: bool


def evaluate(client: OllamaEmbeddings, split="development", margin=EMBEDDING_SUPPORT_MARGIN):
    """Compare each example with labeled development references.

    Development uses leave-one-out references so no example is compared with
    itself. Validation uses only frozen development references.
    """
    targets = DEVELOPMENT if split == "development" else VALIDATION
    all_examples = DEVELOPMENT if split == "development" else DEVELOPMENT + VALIDATION
    vectors = dict(zip((example.id for example in all_examples),
                       client.embed(_input(example) for example in all_examples)))
    results, metrics = [], ClassificationMetrics()
    for example in targets:
        references = [item for item in DEVELOPMENT if item.id != example.id or split != "development"]
        attacks_by_category = {}
        for item in references:
            if item.unfavorable:
                attacks_by_category.setdefault(item.category, []).append(vectors[item.id])
        legitimate = [vectors[item.id] for item in references if not item.unfavorable]
        closest_category, attack_score, legitimate_score, score_margin = _closest_margin(
            vectors[example.id], attacks_by_category, legitimate)
        predicted = score_margin >= margin
        metrics.add(example.unfavorable, predicted)
        results.append(EmbeddingResult(example, attack_score, legitimate_score,
                                       score_margin, closest_category, predicted))
    return results, metrics
