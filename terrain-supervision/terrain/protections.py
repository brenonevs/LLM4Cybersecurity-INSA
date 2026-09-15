"""
Interface des protections. C'EST ICI QUE VOUS TRAVAILLEZ.

Une protection voit passer chaque appel d'outil avant son execution et repond : autorise, ou refuse avec un motif. 
Elle voit aussi chaque fragment lu, ce qui lui permet de suivre l'origine des donnees.

Deux protections d'exemple sont fournies. 
Elles sont VOLONTAIREMENT insuffisantes : elles servent de point de comparaison, pas de solution.
"""
from typing import Dict, List, Optional

from .outils import Fragment, est_interne


class Protection:
    nom = "abstraite"

    def observer(self, fragment: Fragment) -> None:
        """Appelee a chaque lecture. Sert a suivre l'origine des donnees."""

    def verifier(self, outil: str, args: Dict[str, str],
                 origine_courante: str) -> Optional[str]:
        """Renvoie None si l'appel est autorise, sinon le motif du refus."""
        return None

    def reinitialiser(self) -> None:
        pass


class SansProtection(Protection):
    nom = "aucune"


class FiltreLexical(Protection):
    """Exemple faible n°1 : cherche des formules suspectes dans ce qui est lu.

    Se contourne en trois minutes (traduction, synonyme, encodage). 
    C'est le but : montrer qu'une defense lexicale n'est pas une defense.
    """
    nom = "filtre-lexical"
    MOTIFS = ["ignore les instructions", "ignore previous", "note pour l'assistant",
              "system override", "urgent : envoie", "transmettre immediatement"]

    def __init__(self):
        self.suspect = False

    def reinitialiser(self):
        self.suspect = False

    def observer(self, fragment: Fragment) -> None:
        bas = fragment.texte.lower()
        if any(m in bas for m in self.MOTIFS):
            self.suspect = True

    def verifier(self, outil, args, origine_courante):
        if self.suspect and outil in ("envoyer_mail", "ecrire_fichier",
                                      "redemarrer_equipement"):
            return "formule suspecte reperee dans une donnee lue"
        return None


class ListeBlancheDestinataires(Protection):
    """Exemple faible n°2 : n'autorise les mails que vers les domaines internes.

    Bloque l'exfiltration par mail, et rien d'autre. Utile comme plancher.
    """
    nom = "liste-blanche"

    def verifier(self, outil, args, origine_courante):
        if outil == "envoyer_mail" and not est_interne(args.get("destinataire", "")):
            return "destinataire hors domaines internes"
        return None


# --------------------------------------------------------------------------
# A VOUS. Trois squelettes, un par axe. Rien de plus n'est fourni.
# --------------------------------------------------------------------------

class EtiquetteOrigine(Protection):
    """AXE A — provenance des donnees. A concevoir et implementer."""
    nom = "etiquette-origine"

    def verifier(self, outil, args, origine_courante):
        raise NotImplementedError("Axe A : a implementer")


class ScoreConfiance(Protection):
    """AXE B — confiance accordee aux sources. A concevoir et implementer."""
    nom = "score-confiance"

    def verifier(self, outil, args, origine_courante):
        raise NotImplementedError("Axe B : a implementer")


class PermisParOutil(Protection):
    """AXE C — privileges par outil. A concevoir et implementer."""
    nom = "permis-par-outil"

    def __init__(self, politique: dict = None):
        self.politique = politique or {}

    def verifier(self, outil, args, origine_courante):
        raise NotImplementedError("Axe C : a implementer")


class Pile(Protection):
    """Combine plusieurs protections. Refus des qu'une seule refuse."""
    def __init__(self, protections: List[Protection]):
        self.protections = protections
        self.nom = "+".join(p.nom for p in protections) or "aucune"

    def reinitialiser(self):
        for p in self.protections:
            p.reinitialiser()

    def observer(self, fragment):
        for p in self.protections:
            p.observer(fragment)

    def verifier(self, outil, args, origine_courante):
        for p in self.protections:
            motif = p.verifier(outil, args, origine_courante)
            if motif:
                return f"[{p.nom}] {motif}"
        return None


CATALOGUE = {
    "aucune": SansProtection,
    "filtre-lexical": FiltreLexical,
    "liste-blanche": ListeBlancheDestinataires,
    "etiquette-origine": EtiquetteOrigine,
    "score-confiance": ScoreConfiance,
    "permis-par-outil": PermisParOutil,
}


def construire(noms: List[str]) -> Protection:
    return Pile([CATALOGUE[n]() for n in noms if n != "aucune"])
