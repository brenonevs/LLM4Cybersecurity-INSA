"""Local Ollama embedding evaluation, separate from agent authorization."""
import json
from dataclasses import dataclass
from urllib import request

from .classification import ClassificationMetrics
from .embedding_dataset import DEVELOPMENT, VALIDATION, EmbeddingExample


def _input(example: EmbeddingExample) -> str:
    return f"Technician task: {example.task}\nRead text: {example.text}"


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


@dataclass(frozen=True)
class EmbeddingResult:
    example: EmbeddingExample
    attack_similarity: float
    legitimate_similarity: float
    predicted_unfavorable: bool


def evaluate(client: OllamaEmbeddings, split="development"):
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
        attacks = [vectors[item.id] for item in references if item.unfavorable]
        legitimate = [vectors[item.id] for item in references if not item.unfavorable]
        attack_score = _mean_similarity(vectors[example.id], attacks)
        legitimate_score = _mean_similarity(vectors[example.id], legitimate)
        predicted = attack_score > legitimate_score
        metrics.add(example.unfavorable, predicted)
        results.append(EmbeddingResult(example, attack_score, legitimate_score, predicted))
    return results, metrics
