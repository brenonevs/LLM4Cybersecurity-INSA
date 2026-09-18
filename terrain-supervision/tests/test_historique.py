import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.historique import Historique
from terrain.agent import Agent
from terrain.corpus import generer
from terrain.modele import ClientOllama, SYSTEME
from terrain.outils import Etat


def test_conserve_actions_anciennes_et_refus():
    h = Historique()
    h.enregistrer("send_email", {"recipient": "x@entreprise.fr"}, "Email sent")
    for _ in range(6):
        h.enregistrer("search_doc", {"query": "PUMP-01 procedures"},
                      "REFUSED", autorise=False, motif="forbidden")
    messages = h.messages()
    assert len(messages) == 14
    assert json.loads(messages[0]["content"])["args"]["recipient"] == "x@entreprise.fr"
    assert '"status": "refused"' in messages[-1]["content"]
    assert "PUMP-01 procedures" in messages[-2]["content"]


def test_copie_et_troncature_explicite():
    h = Historique()
    args = {"recipient": "responsable@entreprise.fr", "body": "a" * 1000}
    h.enregistrer("send_email", args, "b" * 1000)
    args["recipient"] = "changed"
    messages = h.messages()
    assert "responsable@entreprise.fr" in messages[0]["content"]
    assert "[text truncated]" in messages[0]["content"]
    assert '"result_truncated": true' in messages[1]["content"]
    assert len(h.echanges[0]["action"]["args"]["body"]) == 1000
    assert len(h.echanges[0]["resultat"]) == 1000
    assert h[0] == "[send_email] " + "b" * 600


def test_client_transmet_echanges_et_isole_taches(monkeypatch):
    client = ClientOllama()
    requests = []
    def discuter(messages):
        requests.append(messages)
        if not any(m["role"] == "assistant" for m in messages):
            return '{"tool":"search_doc","args":{"query":"PUMP-01 procedures"}}'
        return '{"tool":"done","response":"finished"}'
    monkeypatch.setattr(client, "discuter", discuter)
    for _ in range(2):
        Agent(Etat(generer()), client).executer("Search for the procedure")
    assert [len(m) for m in requests] == [4, 6, 4, 6]
    assert requests[0] == requests[2]
    assert requests[1][0] == {"role": "system", "content": SYSTEME}
    assert requests[1][3]["role"] == "assistant"
    assert json.loads(requests[1][3]["content"])["args"]["query"] == "PUMP-01 procedures"
    assert "DOC-001" in requests[1][4]["content"] or "result" in requests[1][4]["content"]
    assert "call done" in requests[1][5]["content"]


def test_aucun_blocage_de_repetition():
    class Repete:
        def prochaine_action(self, tache, historique):
            return {"tool": "restart_equipment", "args": {"equipment": "PUMP-01"}}
    etat = Etat(generer())
    ex = Agent(etat, Repete(), max_etapes=3).executer("test")
    assert etat.redemarrages == ["PUMP-01"] * 3
    assert ex.etapes == 3


def test_limite_generation_reprise_bornee(monkeypatch):
    from terrain.modele import LimiteGeneration
    # pyrefly: ignore [missing-import]
    import pytest
    client = ClientOllama()
    calls = []
    def poster(path, charge):
        calls.append(charge)
        if len(calls) == 1:
            return {"done_reason": "length", "message": {"content": '{"tool":"send_email"'}}
        return {"done_reason": "stop", "message": {"content": '{"tool":"done","response":"ok"}'}}
    monkeypatch.setattr(client, "_poster", poster)
    assert client.prochaine_action("test", []) == {"done": "ok"}
    assert len(calls) == 2
    assert all(c["options"]["num_predict"] == 768 for c in calls)
    assert "500 caracteres" in calls[1]["messages"][-1]["content"]
    calls.clear()
    def toujours_long(path, charge):
        calls.append(charge)
        return {"done_reason": "length", "message": {"content": '{"tool":"done"}'}}
    monkeypatch.setattr(client, "_poster", toujours_long)
    with pytest.raises(LimiteGeneration):
        client.prochaine_action("test", [])
    assert len(calls) == 2
