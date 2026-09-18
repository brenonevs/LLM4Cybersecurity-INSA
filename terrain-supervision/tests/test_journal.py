"""Instrumentation tests use a fake Ollama transport, never a running model."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import urllib.error
from dataclasses import asdict

# pyrefly: ignore [missing-import]
import pytest

from terrain.agent import Agent
from terrain.corpus import generer
from terrain.journal import Journal
from terrain.modele import ClientOllama
from terrain.outils import Etat, Outils
from terrain.protections import Protection


def lire(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_journal_preserve_requetes_et_execution(tmp_path, monkeypatch):
    original = Outils.read_log
    def lecture_longue(self, equipment):
        fragment = original(self, equipment)
        fragment.texte += "\n" + "texte de test " * 100
        return fragment
    monkeypatch.setattr(Outils, "read_log", lecture_longue)
    requests = []
    responses = []
    actions = [
        {"tool": "read_log", "args": {"equipment": "CAPT-01"}},
        {"tool": "done", "response": "termine"},
    ]

    class Reponse:
        def __init__(self, data):
            self.data = data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps(self.data).encode()

    def urlopen(req, timeout):
        requests.append(json.loads(req.data))
        data = {"message": {"content": json.dumps(actions[(len(requests)-1) % 2])},
                "eval_count": 10}
        responses.append(data)
        return Reponse(data)

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    baseline = Agent(Etat(generer()), ClientOllama()).executer("Consulte CAPT-01")
    path = tmp_path / "journal.jsonl"
    journal = Journal(path)
    result = Agent(Etat(generer()), ClientOllama(journal=journal),
                   journal=journal, cas="test").executer("Consulte CAPT-01")
    journal.fermer()
    events = lire(path)
    assert asdict(result) == asdict(baseline)
    assert requests[:2] == requests[2:]
    assert [e["charge"] for e in events if e["evenement"] == "modele_requete"] == requests[2:]
    assert [e["reponse"] for e in events if e["evenement"] == "modele_reponse"] == responses[2:]
    tool = next(e for e in events if e["evenement"] == "outil_resultat")
    assert len(tool["texte_complet"]) > 600
    assert tool["observation"] == "[read_log] " + tool["texte_complet"][:600]
    assert events[-1]["raison"] == "fin_modele"
    assert len({e["execution"] for e in events}) == 1


def test_limite_refus_et_isolation(tmp_path):
    class Modele:
        def prochaine_action(self, *args):
            return {"tool": "send_email", "args": {"recipient": "x@example.net"}}

    class Refus(Protection):
        def verifier(self, *args):
            return "bloque"

    path = tmp_path / "journal.jsonl"
    journal = Journal(path)
    for cas in ["T01", "T02"]:
        state = Etat(generer())
        Agent(state, Modele(), Refus(), max_etapes=2,
              journal=journal, cas=cas).executer("test")
        assert not state.mails_envoyes
    journal.fermer()
    events = lire(path)
    ends = [e for e in events if e["evenement"] == "execution_fin"]
    assert [e["raison"] for e in ends] == ["limite_etapes"] * 2
    assert len({e["execution"] for e in ends}) == 2
    decisions = [e for e in events if e["evenement"] == "outil_decision"]
    assert all(not e["autorise"] and e["motif"] == "bloque" for e in decisions)


@pytest.mark.parametrize("error", [ValueError("test"), KeyboardInterrupt()])
def test_erreurs_ne_sont_pas_masquees(tmp_path, error):
    class Modele:
        def prochaine_action(self, *args):
            raise error

    path = tmp_path / "journal.jsonl"
    journal = Journal(path)
    with pytest.raises(type(error)):
        Agent(Etat(generer()), Modele(), journal=journal).executer("test")
    journal.fermer()
    assert lire(path)[-1]["raison"] == (
        "interruption" if isinstance(error, KeyboardInterrupt) else "erreur")


def test_append_preserve_campagnes(tmp_path):
    path = tmp_path / "journal.jsonl"
    for _ in range(2):
        journal = Journal(path)
        journal.noter("test")
        journal.fermer()
    events = lire(path)
    assert len(events) == 2
    assert events[0]["campagne"] != events[1]["campagne"]


def test_repli_format_ollama_est_enregistre(tmp_path, monkeypatch):
    requests = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"message": {"content": json.dumps(
                {"tool": "done", "response": "ok"})}}).encode()

    def urlopen(req, timeout):
        requests.append(json.loads(req.data))
        if len(requests) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "format", {}, None)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    path = tmp_path / "journal.jsonl"
    journal = Journal(path)
    client = ClientOllama(journal=journal)
    assert client.prochaine_action("test", []) == {"done": "ok"}
    journal.fermer()
    events = lire(path)
    assert isinstance(requests[0]["format"], dict)
    assert requests[1]["format"] == "json"
    assert len([e for e in events if e["evenement"] == "modele_requete"]) == 2
    assert any(e["evenement"] == "modele_erreur" for e in events)


def test_calibration_cli_preserve_resultats(tmp_path, capsys):
    from argparse import Namespace
    from run import cmd_calibrer
    args = Namespace(modele="simulateur", protections="aucune")
    cmd_calibrer(args)
    baseline = capsys.readouterr().out
    path = tmp_path / "journal.jsonl"
    args._journal = Journal(path)
    cmd_calibrer(args)
    args._journal.fermer()
    output = capsys.readouterr().out
    assert "\n".join(x for x in output.splitlines() if not x.startswith("[journal]")) == baseline.rstrip("\n")
    events = lire(path)
    starts = [e for e in events if e["evenement"] == "execution_debut"]
    verdicts = [e for e in events if e["evenement"] in ("attaque_verdict", "tache_verdict")]
    assert len(starts) == len(verdicts) == 50
    assert {e["execution"] for e in starts} == {e["execution"] for e in verdicts}
