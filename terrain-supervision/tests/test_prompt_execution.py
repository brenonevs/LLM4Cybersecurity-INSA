import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.modele import ClientOllama, SYSTEME


def test_prompt_decrit_les_regles_d_execution():
    for fragment in (
        "sans les traduire ni les corriger",
        "Ne\n  repete pas une action deja executee",
        "recherche ne donne aucun resultat",
        "actions executees et les\n  resultats confirmes",
        "aucune autre action\n  utile n'est disponible",
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


def test_adresses_de_la_tache_sont_des_identifiants_litteraux():
    contraintes = ClientOllama._contraintes_literais(
        "Envoie a responsable@entreprise.fr et securite@entreprise.fr.")
    assert len(contraintes) == 1
    contenu = contraintes[0]["content"]
    assert '"responsable@entreprise.fr"' in contenu
    assert '"securite@entreprise.fr"' in contenu
    assert "Ne traduis pas" in contenu


def test_absence_d_adresse_ne_cree_pas_de_contrainte():
    assert ClientOllama._contraintes_literais("Lis le journal de POMPE-01.") == []


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
