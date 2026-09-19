"""Instrumentation tests use a fake Ollama transport, never a running model."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import urllib.error
from dataclasses import asdict

import pytest

from terrain.agent import Agent
from terrain.corpus import generer
from terrain.journal import Journal, lire_evenements
from terrain.modele import ClientOllama
from terrain.outils import Etat, Outils
from terrain.protections import Protection


def test_journal_preserve_requetes_et_execution(tmp_path, monkeypatch):
    original = Outils.lire_journal
    def lecture_longue(self, equipement):
        fragment = original(self, equipement)
        fragment.texte += "\n" + "texte de test " * 100
        return fragment
    monkeypatch.setattr(Outils, "lire_journal", lecture_longue)
    requests = []
    responses = []
    actions = [
        {"outil": "lire_journal", "args": {"equipement": "CAPT-01"}},
        {"outil": "fin", "reponse": "termine"},
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
    path = tmp_path / "journal.log"
    journal = Journal(path)
    result = Agent(Etat(generer()), ClientOllama(journal=journal),
                   journal=journal, cas="test").executer("Consulte CAPT-01")
    journal.fermer()
    events = journal.evenements
    report = path.read_text(encoding="utf-8")
    assert asdict(result) == asdict(baseline)
    assert requests[:2] == requests[2:]
    assert [e["charge"] for e in events if e["evenement"] == "modele_requete"] == requests[2:]
    assert [e["reponse"] for e in events if e["evenement"] == "modele_reponse"] == responses[2:]
    tool = next(e for e in events if e["evenement"] == "outil_resultat")
    assert len(tool["texte_complet"]) > 600
    assert tool["observation"] == "[lire_journal] " + tool["texte_complet"][:600]
    assert events[-1]["raison"] == "fin_modele"
    assert len({e["execution"] for e in events}) == 1
    assert "MODEL REQUEST" in report
    assert "Messages sent to the model" in report
    assert "MODEL RESPONSE" in report
    assert "TOOL RESULT" in report
    assert "Full result:" in report


def test_limite_refus_et_isolation(tmp_path):
    class Modele:
        def prochaine_action(self, *args):
            return {"outil": "envoyer_mail", "args": {"destinataire": "x@example.net"}}

    class Refus(Protection):
        def verifier(self, *args):
            return "bloque"

    path = tmp_path / "journal.log"
    journal = Journal(path)
    for cas in ["T01", "T02"]:
        state = Etat(generer())
        Agent(state, Modele(), Refus(), max_etapes=2,
              journal=journal, cas=cas).executer("test")
        assert not state.mails_envoyes
    journal.fermer()
    events = journal.evenements
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

    path = tmp_path / "journal.log"
    journal = Journal(path)
    with pytest.raises(type(error)):
        Agent(Etat(generer()), Modele(), journal=journal).executer("test")
    journal.fermer()
    assert journal.evenements[-1]["raison"] == (
        "interruption" if isinstance(error, KeyboardInterrupt) else "erreur")


def test_append_preserve_campaigns(tmp_path):
    path = tmp_path / "journal.log"
    campaigns = []
    for _ in range(2):
        journal = Journal(path)
        journal.noter("test")
        campaigns.append(journal.campagne)
        journal.fermer()
    report = path.read_text(encoding="utf-8")
    assert campaigns[0] != campaigns[1]
    assert report.count("EVENT: test") == 2


def test_lire_accepte_jsonl_compact_ancien(tmp_path):
    path = tmp_path / "ancien.jsonl"
    path.write_text(
        '{"version": 1, "evenement": "a", "n": 1}\n'
        '{"version": 1, "evenement": "b", "n": 2}\n',
        encoding="utf-8")
    events = lire_evenements(path)
    assert [e["evenement"] for e in events] == ["a", "b"]


def test_repli_format_ollama_est_enregistre(tmp_path, monkeypatch):
    requests = []
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return json.dumps({"message": {"content": json.dumps(
                {"outil": "fin", "reponse": "ok"})}}).encode()

    def urlopen(req, timeout):
        requests.append(json.loads(req.data))
        if len(requests) == 1:
            raise urllib.error.HTTPError(req.full_url, 400, "format", {}, None)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    path = tmp_path / "journal.log"
    journal = Journal(path)
    client = ClientOllama(journal=journal)
    assert client.prochaine_action("test", []) == {"fin": "ok"}
    journal.fermer()
    events = journal.evenements
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
    path = tmp_path / "journal.log"
    args._journal = Journal(path)
    cmd_calibrer(args)
    args._journal.fermer()
    output = capsys.readouterr().out
    assert "\n".join(x for x in output.splitlines() if not x.startswith("[journal]")) == baseline.rstrip("\n")
    events = args._journal.evenements
    starts = [e for e in events if e["evenement"] == "execution_debut"]
    verdicts = [e for e in events if e["evenement"] in ("attaque_verdict", "tache_verdict")]
    assert len(starts) == len(verdicts) == 50
    assert {e["execution"] for e in starts} == {e["execution"] for e in verdicts}
