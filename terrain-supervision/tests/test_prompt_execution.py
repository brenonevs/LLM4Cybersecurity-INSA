import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from terrain.modele import SYSTEME


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
