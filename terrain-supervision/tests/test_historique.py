import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.historique import Historique
from terrain.agent import Agent
from terrain.corpus import generate
from terrain.modele import ClientOllama, SYSTEME
from terrain.outils import Etat


def test_preserves_old_actions_and_denials():
    h = Historique()
    h.record("send_email", {"destinataire": "x@entreprise.fr"}, "Mail envoye")
    for _ in range(6):
        h.record("search_document", {"requete": "POMPE-01 procedures"},
                      "REFUSE", autorise=False, motif="interdit")
    messages = h.messages()
    assert len(messages) == 14
    assert json.loads(messages[0]["content"])["args"]["destinataire"] == "x@entreprise.fr"
    assert '"statut": "refuse"' in messages[-1]["content"]
    assert "POMPE-01 procedures" in messages[-2]["content"]


def test_explicit_copy_and_truncation():
    h = Historique()
    args = {"destinataire": "responsable@entreprise.fr", "corps": "a" * 1300}
    h.record("send_email", args, "b" * 1300)
    args["destinataire"] = "changed"
    messages = h.messages()
    assert "responsable@entreprise.fr" in messages[0]["content"]
    assert "[texte tronque]" in messages[0]["content"]
    assert '"resultat_tronque": true' in messages[1]["content"]
    assert len(h.echanges[0]["action"]["args"]["corps"]) == 1300
    assert len(h.echanges[0]["resultat"]) == 1300
    assert h[0] == "[send_email] " + "b" * 600


def test_first_result_can_use_1200_characters():
    h = Historique()
    h.record("read_log", {"equipement": "POMPE-01"}, "x" * 1000)
    resultat = json.loads(h.messages()[1]["content"].split(": ", 1)[1])
    assert len(resultat["resultat"]) == 1000
    assert resultat["resultat_tronque"] is False
    assert resultat["limite_resultat_modele"] == 1200


def test_total_budget_distributes_across_eight_results():
    h = Historique()
    for i in range(8):
        h.record("search_document", {"requete": str(i)}, "x" * 1000)
    resultats = [json.loads(m["content"].split(": ", 1)[1])
                 for m in h.messages()[1::2]]
    assert all(len(r["resultat"]) == 600 for r in resultats)
    assert all(r["resultat_tronque"] for r in resultats)
    assert sum(len(r["resultat"]) for r in resultats) == 4800


def test_client_passes_exchanges_and_isolates_tasks(monkeypatch):
    client = ClientOllama()
    requests = []
    def chat(messages):
        requests.append(messages)
        if not any(m["role"] == "assistant" for m in messages):
            return '{"outil":"search_document","args":{"requete":"POMPE-01 procedures"}}'
        return '{"outil":"fin","reponse":"termine"}'
    monkeypatch.setattr(client, "chat", chat)
    for _ in range(2):
        Agent(Etat(generate()), client).execute("Cherche la procedure")
    assert [len(m) for m in requests] == [4, 6, 4, 6]
    assert requests[0] == requests[2]
    assert requests[1][0] == {"role": "system", "content": SYSTEME}
    assert requests[1][3]["role"] == "assistant"
    assert json.loads(requests[1][3]["content"])["args"]["requete"] == "POMPE-01 procedures"
    assert '"statut": "execute"' in requests[1][4]["content"]
    assert "Next expected action" not in requests[1][5]["content"]
    assert not any("explicit operational directive" in m["content"] for m in requests[1])


def test_no_repetition_blocking():
    class Repete:
        def next_action(self, tache, historique):
            return {"outil": "restart_equipment", "args": {"equipement": "POMPE-01"}}
    etat = Etat(generate())
    ex = Agent(etat, Repete(), max_etapes=3).execute("test")
    assert etat.redemarrages == ["POMPE-01"]
    assert len(ex.trace) == 3
    assert ex.etapes == 2


def test_bounded_generation_retry_limit(monkeypatch):
    from terrain.modele import LimiteGeneration
    import pytest
    client = ClientOllama()
    calls = []
    def post(path, charge):
        calls.append(charge)
        if len(calls) == 1:
            return {"done_reason": "length", "message": {"content": '{"outil":"send_email"'}}
        return {"done_reason": "stop", "message": {"content": '{"outil":"fin","reponse":"ok"}'}}
    monkeypatch.setattr(client, "_post", post)
    assert client.next_action("test", []) == {"fin": "ok"}
    assert len(calls) == 2
    assert all(c["options"]["num_predict"] == 768 for c in calls)
    assert "500 characters" in calls[1]["messages"][-1]["content"]
    calls.clear()
    def always_long(path, charge):
        calls.append(charge)
        return {"done_reason": "length", "message": {"content": '{"outil":"fin"}'}}
    monkeypatch.setattr(client, "_post", always_long)
    with pytest.raises(LimiteGeneration):
        client.next_action("test", [])
    assert len(calls) == 2
