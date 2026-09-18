"""
La boucle de l'agent cible.

Un seul endroit ou les protections sont consultees : juste avant l'execution d'un tool. C'est votre point d'application unique. Ne le dispersez pas.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .outils import AppelOutil, Etat, Fragment, Outils
from .protections import Protection, SansProtection
from .historique import Historique


@dataclass
class Execution:
    tache: str                                              #Instruction inicial
    trace: List[AppelOutil]                                 #Trilha de execuções
    response: str                                            #Resposta final
    etapes: int                                             #Número de etapas
    journal: List[Dict[str, Any]] = field(default_factory=list) #Detalhes das iterações e pensamentos

"""
Construtor do Agente:
Recebe 
    Etat (memória do agente, ele anotará o que faz)
    Modele (O modelo em si, Ollama)
    Protection (As barreiras implementadas, caso none ele ficará vulnerável)
    max_etapes (Limite de execuções, por segurança para não travar o sistema)
"""
class Agent:
    def __init__(self, etat: Etat, modele, protection: Protection = None,
                 max_etapes: int = 8, journal=None, cas="execution"):
        self.etat = etat
        self.outils = Outils(etat)
        self.modele = modele
        self.protection = protection or SansProtection()
        self.max_etapes = max_etapes
        self.journal, self.cas = journal, cas

    """
    Recebe uma tache, reinicia a memória da proteção, o histórico (O que foi lido pelo LLM) e o trace (as ações) 
    """
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
        journal_local: List[Dict[str, Any]] = []
        # Origine de la demande initiale. Le suivi de l'origine au fil des
        # lectures, s'il est pertinent, releve de la protection.
        origine = "utilisateur"

        # Loop de execução
        for etape in range(self.max_etapes):
            if self.journal:
                self.journal.etape = etape + 1

            # O modelo recebe o objetivo (tache) e o histórico (memória do agente) 
            # e decide a próxima ação.
            action = self.modele.prochaine_action(tache, historique)
            reponse_brute = getattr(self.modele, "derniere_reponse", "")

            # If model decides to finish execution, return result and stop
            if "done" in action:
                res_done = str(action.get("done", action.get("response", "done")))
                if self.journal:
                    self.journal.terminer("fin_modele", len(trace), res_done)
                journal_local.append({
                    "etape": etape + 1,
                    "reponse_brute": reponse_brute,
                    "messages_recus": getattr(self.modele, "derniers_messages", []),
                    "action": action,
                    "tool": "done",
                    "args": {},
                    "autorise": True,
                    "motif_refus": "",
                    "resultat": res_done,
                })
                return Execution(tache, trace, res_done, etape, journal_local)

            # Extract tool name and arguments
            nom = str(action.get("tool", "")).strip()
            args = {k: str(v) for k, v in (action.get("args") or {}).items()}

            # Passa pelo mecanismo de proteção para verificar se a ação é permitida
            motif = self.protection.verifier(nom, args, origine)
            if self.journal:
                self.journal.noter("outil_decision", outil=nom, args=args,
                                   autorise=(motif is None), motif=motif)

            appel = AppelOutil(tool=nom, args=args, origine_declencheur=origine,
                               autorise=(motif is None), motif_refus=motif or "")

            # Se a ação for negada, adiciona ao histórico e ao trace e continua para a próxima iteração
            if motif:
                if self.journal:
                    self.journal.noter("outil_refus", outil=nom, args=args, motif=motif)
                appel.resultat = f"REFUSE : {motif}"
                trace.append(appel)
                self.etat.trace.append(appel)
                historique.enregistrer(nom, args, appel.resultat, autorise=False, motif=motif)
                journal_local.append({
                    "etape": etape + 1,
                    "reponse_brute": reponse_brute,
                    "messages_recus": getattr(self.modele, "derniers_messages", []),
                    "action": action,
                    "tool": nom,
                    "args": args,
                    "autorise": False,
                    "motif_refus": motif,
                    "resultat": appel.resultat,
                })
                continue

            # Executa a ferramenta
            fragment: Fragment = self.outils.appeler(nom, args)
            # Observa o fragmento para atualizar a memória do agente
            self.protection.observer(fragment)

            if self.journal:
                self.journal.noter("outil_resultat", outil=nom, args=args,
                                   texte_complet=fragment.texte,
                                   observation=f"[{nom}] {fragment.texte[:600]}")

            # Adiciona o resultado ao trace e ao histórico
            appel.resultat = fragment.texte[:2000]
            trace.append(appel)
            self.etat.trace.append(appel)
            historique.enregistrer(nom, args, fragment.texte, autorise=True, motif="")
            journal_local.append({
                "etape": etape + 1,
                "reponse_brute": reponse_brute,
                "messages_recus": getattr(self.modele, "derniers_messages", []),
                "action": action,
                "tool": nom,
                "args": args,
                "autorise": True,
                "motif_refus": "",
                "resultat": fragment.texte,
            })

        # Se o loop terminar sem retornar, significa que atingiu o limite de etapas
        if self.journal:
            self.journal.terminer("limite_etapes", len(trace), "(limite d'etapes atteinte)")
        return Execution(tache, trace, "(limite d'etapes atteinte)", self.max_etapes, journal_local)
