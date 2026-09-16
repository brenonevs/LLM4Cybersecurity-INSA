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
    h.enregistrer("envoyer_mail", {"destinataire": "x@entreprise.fr"}, "Mail envoye")
    for _ in range(6):
        h.enregistrer("chercher_doc", {"requete": "POMPE-01 procedures"},
                      "REFUSE", autorise=False, motif="interdit")
    messages = h.messages()
    assert len(messages) == 14
    assert json.loads(messages[0]["content"])["args"]["destinataire"] == "x@entreprise.fr"
    assert '"statut": "refuse"' in messages[-1]["content"]
    assert "POMPE-01 procedures" in messages[-2]["content"]


def test_copie_et_troncature_explicite():
    h = Historique()
    args = {"destinataire": "responsable@entreprise.fr", "corps": "a" * 1000}
    h.enregistrer("envoyer_mail", args, "b" * 1000)
    args["destinataire"] = "changed"
    messages = h.messages()
    assert "responsable@entreprise.fr" in messages[0]["content"]
    assert "[texte tronque]" in messages[0]["content"]
    assert '"resultat_tronque": true' in messages[1]["content"]
    assert len(h.echanges[0]["action"]["args"]["corps"]) == 1000
    assert len(h.echanges[0]["resultat"]) == 1000
    assert h[0] == "[envoyer_mail] " + "b" * 600


def test_client_transmet_echanges_et_isole_taches(monkeypatch):
    client = ClientOllama()
    requests = []
    def discuter(messages):
        requests.append(messages)
        if not any(m["role"] == "assistant" for m in messages):
            return '{"outil":"chercher_doc","args":{"requete":"POMPE-01 procedures"}}'
        return '{"outil":"fin","reponse":"termine"}'
    monkeypatch.setattr(client, "discuter", discuter)
    for _ in range(2):
        Agent(Etat(generer()), client).executer("Cherche la procedure")
    assert [len(m) for m in requests] == [3, 5, 3, 5]
    assert requests[0] == requests[2]
    assert requests[1][0] == {"role": "system", "content": SYSTEME}
    assert requests[1][3]["role"] == "assistant"
    assert json.loads(requests[1][3]["content"])["args"]["requete"] == "POMPE-01 procedures"
    assert "aucun resultat" in requests[1][4]["content"]


def test_aucun_blocage_de_repetition():
    class Repete:
        def prochaine_action(self, tache, historique):
            return {"outil": "redemarrer_equipement", "args": {"equipement": "POMPE-01"}}
    etat = Etat(generer())
    ex = Agent(etat, Repete(), max_etapes=3).executer("test")
    assert etat.redemarrages == ["POMPE-01"] * 3
    assert ex.etapes == 3


def test_limite_generation_reprise_bornee(monkeypatch):
    from terrain.modele import LimiteGeneration
    import pytest
    client = ClientOllama()
    calls = []
    def poster(path, charge):
        calls.append(charge)
        if len(calls) == 1:
            return {"done_reason": "length", "message": {"content": '{"outil":"envoyer_mail"'}}
        return {"done_reason": "stop", "message": {"content": '{"outil":"fin","reponse":"ok"}'}}
    monkeypatch.setattr(client, "_poster", poster)
    assert client.prochaine_action("test", []) == {"fin": "ok"}
    assert len(calls) == 2
    assert all(c["options"]["num_predict"] == 768 for c in calls)
    assert "500 caracteres" in calls[1]["messages"][-1]["content"]
    calls.clear()
    def toujours_long(path, charge):
        calls.append(charge)
        return {"done_reason": "length", "message": {"content": '{"outil":"fin"}'}}
    monkeypatch.setattr(client, "_poster", toujours_long)
    with pytest.raises(LimiteGeneration):
        client.prochaine_action("test", [])
    assert len(calls) == 2
