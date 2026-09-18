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
        journal: List[Dict[str, Any]] = []
        # Origine de la demande initiale. Le suivi de l'origine au fil des
        # lectures, s'il est pertinent, releve de la protection.
        origine = "utilisateur"

        # Loop de execução
        for etape in range(self.max_etapes):
            # O modelo recebe o objetivo (tache) e o histórico (memória do agente) 
            # e decide a próxima ação.
            action = self.modele.prochaine_action(tache, historique)
            reponse_brute = getattr(self.modele, "derniere_reponse", "")

            # Se o modelo decidir finalizar a execução, ele retorna o resultado e finaliza o agente
            if "done" in action:
                journal.append({
                    "etape": etape + 1,
                    "reponse_brute": reponse_brute,
                    "messages_recus": getattr(self.modele, "derniers_messages", []),
                    "action": action,
                    "tool": "done",
                    "args": {},
                    "autorise": True,
                    "motif_refus": "",
                    "resultat": str(action.get("done", action.get("response", "termine"))),
                })
                return Execution(tache, trace, str(action["done"]), etape, journal)

            nom = str(action.get("tool", "")).strip()
            args = {k: str(v) for k, v in (action.get("args") or {}).items()}

            if trace and trace[-1].tool == nom and trace[-1].args == args:
                motif = "System error: You just called this tool with these exact arguments. Try a different tool or call 'done'."
                appel = AppelOutil(tool=nom, args=args, origine_declencheur=origine,
                                   autorise=False, motif_refus=motif)
            else:
                motif = self.protection.verifier(nom, args, origine)
                appel = AppelOutil(tool=nom, args=args, origine_declencheur=origine,
                                   autorise=(motif is None), motif_refus=motif or "")

            # Se a ação for negada, adiciona ao histórico e ao trace e continua para a próxima iteração
            if motif:
                appel.resultat = f"REFUSE : {motif}"
                trace.append(appel)
                self.etat.trace.append(appel)
                historique.append(f"[{nom}] refuse ({motif})")
                journal.append({
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

            # Adiciona o resultado ao trace e ao histórico
            appel.resultat = fragment.texte[:2000]
            trace.append(appel)
            self.etat.trace.append(appel)
            historique.append(f"[{nom}] {fragment.texte[:600]}")
            journal.append({
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
        return Execution(tache, trace, "(limite d'etapes atteinte)", self.max_etapes, journal)
