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

    def executer(self, tache: str) -> Execution:
        if self.journal:
            self.journal.commencer(self.cas, tache, self.max_etapes)
        debut_trace = len(self.etat.trace)
        try:
            return self._executer(tache)
        except BaseException as erreur:
            if self.journal:
                self.journal.noter("execution_erreur", type=type(erreur).__name__,
                                   message=str(erreur))
                self.journal.terminer("interruption" if isinstance(erreur, KeyboardInterrupt)
                                      else "erreur",
                                      len(self.etat.trace) - debut_trace, str(erreur))
            raise

    def _executer(self, tache: str) -> Execution:
        self.protection.reinitialiser()
        historique = Historique()
        trace: List[AppelOutil] = []
        # Origine de la demande initiale. Le suivi de l'origine au fil des
        # lectures, s'il est pertinent, releve de la protection.
        origine = "utilisateur"

        for etape in range(self.max_etapes):
            if self.journal:
                self.journal.etape = etape + 1
                self.journal.noter("etape_debut", tache=tache, historique=historique,
                                   echanges=historique.echanges)
                self.journal.annoncer_etape(etape + 1)
            action = self.modele.prochaine_action(tache, historique)
            if self.journal:
                self.journal.noter("decision", action=action)
                self.journal.annoncer_decision(action)

            if "fin" in action:
                if self.journal:
                    self.journal.terminer("erreur_format" if action.get("_parse")
                                          else "fin_modele", len(trace), str(action["fin"]))
                return Execution(tache, trace, str(action["fin"]), etape)

            nom = str(action.get("outil", "")).strip()
            args = {k: str(v) for k, v in (action.get("args") or {}).items()}

            # Stop repeated calls against the same target. For emails and files,
            # changing only the body or content does not create a new target.
            deja_appele = False
            for appel_precedent in trace:
                if appel_precedent.outil != nom:
                    continue
                if nom == "read_log" and (
                        appel_precedent.args.get("equipement") == args.get("equipement")):
                    deja_appele = True
                elif nom == "search_document" and (
                        appel_precedent.args.get("requete") == args.get("requete")):
                    deja_appele = True
                elif nom == "write_file" and (
                        appel_precedent.args.get("chemin") == args.get("chemin")):
                    deja_appele = True
                elif nom == "send_email" and (
                        appel_precedent.args.get("destinataire") == args.get("destinataire")):
                    deja_appele = True
                elif appel_precedent.args == args:
                    deja_appele = True

            if deja_appele:
                motif = (
                    "System error: You have already performed this action on this target. "
                    "You MUST NOT repeat it. Immediately output a DIFFERENT tool call or "
                    "{\"fin\": \"finished\"}."
                )
                appel = AppelOutil(outil=nom, args=args, origine_declencheur=origine,
                                   autorise=False, motif_refus=motif)
            else:
                motif = self.protection.verifier(nom, args, origine)
                appel = AppelOutil(outil=nom, args=args, origine_declencheur=origine,
                                   autorise=(motif is None), motif_refus=motif or "")

            if self.journal:
                self.journal.noter("outil_decision", outil=nom, args=args,
                                   autorise=appel.autorise, motif=appel.motif_refus)
                self.journal.annoncer_outil(nom, args, appel.autorise, appel.motif_refus)
            if motif:
                appel.resultat = f"REFUSE : {motif}"
                trace.append(appel)
                self.etat.trace.append(appel)
                historique.enregistrer(nom, args, appel.resultat, autorise=False, motif=motif)
                if self.journal:
                    self.journal.annoncer_resultat(nom, appel.resultat)
                if len(trace) >= 2 and not trace[-1].autorise and not trace[-2].autorise:
                    message = "done: auto-terminated after consecutive refusals"
                    if self.journal:
                        self.journal.terminer("limite_etapes", len(trace), message)
                    return Execution(tache, trace, message, etape)
                continue

            fragment: Fragment = self.outils.appeler(nom, args)
            self.protection.observer(fragment)

            appel.resultat = fragment.texte[:2000]
            trace.append(appel)
            self.etat.trace.append(appel)
            historique.enregistrer(nom, args, fragment.texte)
            if self.journal:
                self.journal.noter("outil_resultat", outil=nom, args=args,
                                   texte_complet=fragment.texte, origine=fragment.origine,
                                   source=fragment.source,
                                   sources=[source.as_dict() for source in fragment.sources],
                                   observation=historique[-1])
                self.journal.annoncer_resultat(nom, fragment.texte)

        if self.journal:
            self.journal.terminer("limite_etapes", len(trace), "(limite d'etapes atteinte)")
        return Execution(tache, trace, "(limite d'etapes atteinte)", self.max_etapes)
