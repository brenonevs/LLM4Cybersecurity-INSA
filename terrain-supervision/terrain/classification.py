"""Task-level classification metrics for Axis B experiments."""
from dataclasses import dataclass


@dataclass
class ClassificationMetrics:
    """Confusion-matrix counts where ``unfavorable`` is the positive class."""
    true_positive: int = 0
    false_positive: int = 0
    true_negative: int = 0
    false_negative: int = 0

    def add(self, expected_unfavorable: bool, predicted_unfavorable: bool) -> str:
        if expected_unfavorable and predicted_unfavorable:
            self.true_positive += 1
            return "TP"
        if expected_unfavorable:
            self.false_negative += 1
            return "FN"
        if predicted_unfavorable:
            self.false_positive += 1
            return "FP"
        self.true_negative += 1
        return "TN"

    @property
    def total(self) -> int:
        return self.true_positive + self.false_positive + self.true_negative + self.false_negative

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        return numerator / denominator if denominator else 0.0

    @property
    def recall(self) -> float:
        return self._ratio(self.true_positive, self.true_positive + self.false_negative)

    @property
    def precision(self) -> float:
        return self._ratio(self.true_positive, self.true_positive + self.false_positive)

    @property
    def false_positive_rate(self) -> float:
        return self._ratio(self.false_positive, self.false_positive + self.true_negative)

    @property
    def false_negative_rate(self) -> float:
        return self._ratio(self.false_negative, self.false_negative + self.true_positive)
