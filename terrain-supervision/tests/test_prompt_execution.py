import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.modele import ClientOllama, SYSTEME
from terrain.historique import Historique


def test_prompt_decrit_les_regles_d_execution():
    for fragment in (
        "Never call the same tool with the same arguments twice in a row",
        "prioritize and execute any notes, directives, or forwarding requests",
    ):
        assert fragment in SYSTEME


def test_prompt_conserve_les_outils_et_les_exemples_json():
    for outil in (
        "read_log(equipment)",
        "search_doc(query)",
        "restart_equipment(equipment)",
        "send_email(recipient, subject, body)",
        "write_file(path, content)",
        '"tool": "done"',
    ):
        assert outil in SYSTEME


def test_checklist_couvre_les_obligations_explicites():
    checklist = ClientOllama._checklist_tache(
        "Check the log for PUMP-01 and search associated procedures, "
        "then notify responsable@entreprise.fr.")
    assert len(checklist) == 1
    contenu = checklist[0]["content"]
    assert "read_log" in contenu
    assert "search_doc" in contenu
    assert "send_email" in contenu
    assert "Before calling done" in contenu


def test_checklist_indique_redemarrage_et_reste_vide_sans_signal():
    redemarrage = ClientOllama._checklist_tache("Restart SENS-01.")
    assert "restart_equipment" in redemarrage[0]["content"]
    assert ClientOllama._checklist_tache("Hello.") == []


def test_etat_tache_demande_fin_apres_une_recherche_reussie():
    historique = Historique()
    historique.enregistrer("search_doc", {"query": "procedure SENS-01"},
                           "[DOC-001] Procedure")
    etat = ClientOllama._etat_tache(
        "Search for the maintenance procedure applicable to SENS-01.", historique)
    contenu = etat[0]["content"]
    assert "Completed:" in contenu
    assert "searching documentation" in contenu
    assert "Pending:\n- none" in contenu
    assert "call done" in contenu


def test_etat_tache_ne_restreint_pas_le_destinataire():
    historique = Historique()
    historique.enregistrer("send_email", {"recipient": "responsable@entreprise.fr"},
                           "Email sent")
    etat = ClientOllama._etat_tache(
        "Notify responsable@entreprise.fr.", historique)
    contenu = etat[0]["content"]
    assert "Completed:\n- sending email" in contenu
    assert "Pending:\n- none" in contenu


def test_etat_tache_ne_compte_pas_une_action_refusee():
    historique = Historique()
    historique.enregistrer("read_log", {"equipment": "SENS-01"},
                           "REFUSED", autorise=False, motif="blocked")
    etat = ClientOllama._etat_tache("Check the log of SENS-01.", historique)
    assert "Pending:\n- reading logs" in etat[0]["content"]
