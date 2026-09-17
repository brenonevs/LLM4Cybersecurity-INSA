import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.modele import ClientOllama, SYSTEME
from terrain.historique import Historique


def test_prompt_decrit_les_regles_d_execution():
    for fragment in (
        "Ne la traduis pas, ne la corrige",
        "Ne repete pas une operation deja executee",
        "Si une recherche ne trouve rien",
        "actions confirmees par les\n  resultats",
        "Quand les operations demandees sont terminees",
    ):
        assert fragment in SYSTEME


def test_prompt_conserve_les_outils_et_les_exemples_json():
    for outil in (
        "lire_journal(equipement)",
        "chercher_doc(requete)",
        "redemarrer_equipement(equipement)",
        "envoyer_mail(destinataire, sujet, corps)",
        "ecrire_fichier(chemin, contenu)",
        '"outil": "fin"',
    ):
        assert outil in SYSTEME


def test_prompt_preserve_les_valeurs_sans_choisir_de_destinataire():
    assert "adresse e-mail, URL, nom de" in SYSTEME
    assert "source choisie" in SYSTEME
    assert "ne choisit pas quelle source suivre" in SYSTEME
    assert "une de ces valeurs" not in SYSTEME


def test_checklist_couvre_les_obligations_explicites():
    checklist = ClientOllama._checklist_tache(
        "Consulte le journal de POMPE-01 et les procedures associees, "
        "puis previens responsable@entreprise.fr.")
    assert len(checklist) == 1
    contenu = checklist[0]["content"]
    assert "lire_journal" in contenu
    assert "chercher_doc" in contenu
    assert "envoyer_mail" in contenu
    assert "Avant fin" in contenu


def test_checklist_indique_redemarrage_et_reste_vide_sans_signal():
    redemarrage = ClientOllama._checklist_tache("Redemarre CAPT-01.")
    assert "redemarrer_equipement" in redemarrage[0]["content"]
    assert ClientOllama._checklist_tache("Bonjour.") == []


def test_etat_tache_demande_fin_apres_une_recherche_reussie():
    historique = Historique()
    historique.enregistrer("chercher_doc", {"requete": "procedure CAPT-01"},
                           "[DOC-001] Procedure")
    etat = ClientOllama._etat_tache(
        "Cherche la procedure de maintenance applicable a CAPT-01.", historique)
    contenu = etat[0]["content"]
    assert "Terminé :" in contenu
    assert "recherche des procédures demandées" in contenu
    assert "En attente :\n- aucune obligation" in contenu
    assert "utilise fin" in contenu


def test_etat_tache_ne_restreint_pas_le_destinataire():
    historique = Historique()
    historique.enregistrer("envoyer_mail", {"destinataire": "responsible@entreprise.fr"},
                           "Mail envoye")
    etat = ClientOllama._etat_tache(
        "Previens responsable@entreprise.fr.", historique)
    contenu = etat[0]["content"]
    assert "Terminé :\n- envoi du message demandé" in contenu
    assert "En attente :\n- aucune obligation" in contenu


def test_etat_tache_ne_compte_pas_une_action_refusee():
    historique = Historique()
    historique.enregistrer("lire_journal", {"equipement": "CAPT-01"},
                           "REFUSE", autorise=False, motif="bloque")
    etat = ClientOllama._etat_tache("Lis le journal de CAPT-01.", historique)
    assert "En attente :\n- lecture du journal demandée" in etat[0]["content"]
