"""
La boucle de l'agent cible.

Un seul endroit ou les protections sont consultees : juste avant l'execution d'un outil. C'est votre point d'application unique. Ne le dispersez pas.
"""
from dataclasses import dataclass
from typing import List

from .outils import AppelOutil, Etat, Fragment, Outils
from .protections import Protection, SansProtection
from .historique import Historique


@dataclass
class Execution:
    tache: str
    trace: List[AppelOutil]
    reponse: str
    etapes: int


class Agent:
    def __init__(self, etat: Etat, modele, protection: Protection = None,
                 max_etapes: int = 8, journal=None, cas="execution"):
        self.etat = etat
        self.outils = Outils(etat)
        self.modele = modele
        self.protection = protection or SansProtection()
        self.max_etapes = max_etapes
        self.journal, self.cas = journal, cas

    def execute(self, tache: str) -> Execution:
        if self.journal:
            self.journal.start(self.cas, tache, self.max_etapes)
        debut_trace = len(self.etat.trace)
        try:
            return self._execute(tache)
        except BaseException as erreur:
            if self.journal:
                self.journal.log("execution_erreur", type=type(erreur).__name__,
                                   message=str(erreur))
                self.journal.finish("interruption" if isinstance(erreur, KeyboardInterrupt)
                                      else "erreur",
                                      len(self.etat.trace) - debut_trace, str(erreur))
            raise

    def _execute(self, tache: str) -> Execution:
        self.protection.reset()
        historique = Historique()
        trace: List[AppelOutil] = []
        # Origine de la demande initiale. Le suivi de l'origine au fil des
        # lectures, s'il est pertinent, releve de la protection.
        origine = "utilisateur"

        for etape in range(self.max_etapes):
            if self.journal:
                self.journal.etape = etape + 1
                self.journal.log("etape_debut", tache=tache, historique=historique,
                                   echanges=historique.echanges)
                self.journal.announce_step(etape + 1)
            action = self.modele.next_action(tache, historique)
            if self.journal:
                self.journal.log("decision", action=action)
                self.journal.announce_decision(action)

            if "fin" in action:
                if self.journal:
                    self.journal.finish("erreur_format" if action.get("_parse")
                                          else "fin_modele", len(trace), str(action["fin"]))
                return Execution(tache, trace, str(action["fin"]), etape)

            name = str(action.get("outil", "")).strip()
            args = {k: str(v) for k, v in (action.get("args") or {}).items()}

            motif = self.protection.verify(name, args, origine)
            appel = AppelOutil(outil=name, args=args, origine_declencheur=origine,
                               autorise=(motif is None), motif_refus=motif or "")

            if self.journal:
                self.journal.log("outil_decision", outil=name, args=args,
                                   autorise=appel.autorise, motif=appel.motif_refus)
                self.journal.announce_tool(name, args, appel.autorise, appel.motif_refus)
            if motif:
                appel.resultat = f"REFUSE : {motif}"
                trace.append(appel)
                self.etat.trace.append(appel)
                historique.record(name, args, appel.resultat, autorise=False, motif=motif)
                if self.journal:
                    self.journal.announce_result(name, appel.resultat)
                continue

            fragment: Fragment = self.outils.call(name, args)
            self.protection.observe(fragment)

            appel.resultat = fragment.texte[:2000]
            trace.append(appel)
            self.etat.trace.append(appel)
            historique.record(name, args, fragment.texte)
            if self.journal:
                self.journal.log("outil_resultat", outil=name, args=args,
                                   texte_complet=fragment.texte, origine=fragment.origine,
                                   source=fragment.source, observation=historique[-1])
                self.journal.announce_result(name, fragment.texte)

        if self.journal:
            self.journal.finish("limite_etapes", len(trace), "(limite d'etapes atteinte)")
        return Execution(tache, trace, "(limite d'etapes atteinte)", self.max_etapes)
