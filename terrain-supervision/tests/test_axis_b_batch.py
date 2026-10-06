"""Tests for the temporary Axis B batch runner."""
import sys
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_axis_b_batch_runs_each_variant_with_a_separate_log(monkeypatch, capsys):
    import run

    created_logs, runs = [], []
    progress = []

    class FakeProgress:
        def __init__(self, **kwargs):
            progress.append(("init", kwargs))

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def set_postfix_str(self, value):
            progress.append(("label", value))

        def update(self, value):
            progress.append(("update", value))

    class FakeJournal:
        def __init__(self, path):
            self.chemin = Path(path)
            self.events = []
            created_logs.append(path)

        def noter(self, event, **fields):
            self.events.append((event, fields))

        def fermer(self):
            pass

    def fake_calibration(args):
        runs.append((args.commande, args.protections,
                     args.embedding_support, args.trust_authorization))

    monkeypatch.setattr(run, "Journal", FakeJournal)
    monkeypatch.setattr(run, "cmd_calibrer", fake_calibration)
    monkeypatch.setitem(sys.modules, "tqdm", Namespace(tqdm=FakeProgress))

    run.cmd_axis_b_batch(Namespace(
        batch_prefix="temporary-axis-b.log",
        modele="ollama",
        ollama_modele="llama3.1:8b",
        protections="aucune",
        embedding_support=False,
        trust_authorization=False,
        _journal=None,
    ))

    assert runs == [
        ("axis-b-batch:baseline", "aucune", False, False),
        ("axis-b-batch:observational", "score-confiance", False, False),
        ("axis-b-batch:embedding-observational", "score-confiance", True, False),
        ("axis-b-batch:trust-authorization", "score-confiance", False, True),
        ("axis-b-batch:trust-authorization-embedding", "score-confiance", True, True),
    ]
    assert created_logs == [
        "temporary-axis-b-01-baseline.log",
        "temporary-axis-b-02-observational.log",
        "temporary-axis-b-03-embedding-observational.log",
        "temporary-axis-b-04-trust-authorization.log",
        "temporary-axis-b-05-trust-authorization-embedding.log",
    ]
    output = capsys.readouterr().out
    assert "AXIS B BATCH — five calibration campaigns" in output
    assert progress[0] == ("init", {
        "total": 5, "desc": "Axis B batch", "unit": "campaign", "dynamic_ncols": True,
    })
    assert [event for event in progress if event[0] == "update"] == [("update", 1)] * 5
