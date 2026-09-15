"""
La boucle de l'agent cible.

Un seul endroit ou les protections sont consultees : juste avant l'execution d'un outil. C'est votre point d'application unique. Ne le dispersez pas.
"""
from dataclasses import dataclass
from typing import List

from .outils import AppelOutil, Etat, Fragment, Outils
from .protections import Protection, SansProtection


@dataclass
class Execution:
    tache: str
    trace: List[AppelOutil]
    reponse: str
    etapes: int


class Agent:
    def __init__(self, etat: Etat, modele, protection: Protection = None,
                 max_etapes: int = 8):
        self.etat = etat
        self.outils = Outils(etat)
        self.modele = modele
        self.protection = protection or SansProtection()
        self.max_etapes = max_etapes

    def executer(self, tache: str) -> Execution:
        self.protection.reinitialiser()
        historique: List[str] = []
        trace: List[AppelOutil] = []
        # Origine de la demande initiale. Le suivi de l'origine au fil des
        # lectures, s'il est pertinent, releve de la protection.
        origine = "utilisateur"

        for etape in range(self.max_etapes):
            action = self.modele.prochaine_action(tache, historique)

            if "fin" in action:
                return Execution(tache, trace, str(action["fin"]), etape)

            nom = str(action.get("outil", "")).strip()
            args = {k: str(v) for k, v in (action.get("args") or {}).items()}

            motif = self.protection.verifier(nom, args, origine)
            appel = AppelOutil(outil=nom, args=args, origine_declencheur=origine,
                               autorise=(motif is None), motif_refus=motif or "")

            if motif:
                appel.resultat = f"REFUSE : {motif}"
                trace.append(appel)
                self.etat.trace.append(appel)
                historique.append(f"[{nom}] refuse ({motif})")
                continue

            fragment: Fragment = self.outils.appeler(nom, args)
            self.protection.observer(fragment)

            appel.resultat = fragment.texte[:2000]
            trace.append(appel)
            self.etat.trace.append(appel)
            historique.append(f"[{nom}] {fragment.texte[:600]}")

        return Execution(tache, trace, "(limite d'etapes atteinte)", self.max_etapes)
