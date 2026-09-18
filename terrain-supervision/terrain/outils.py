"""
Etat du systeme et les cinq outils de l'agent.

Chaque resultat d'tool est un Fragment qui indique de quelle source il
provient. Rien n'exploite cette information : le terrain est livre vulnerable.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .corpus import Corpus, DOMAINES_INTERNES

ORIGINES = ["systeme", "utilisateur", "interne", "externe"]


@dataclass
class Fragment:
    texte: str
    origine: str = "externe"
    source: str = "?"


@dataclass
class AppelOutil:
    tool: str
    args: Dict[str, Any]
    origine_declencheur: str = "systeme"
    autorise: bool = True
    motif_refus: str = ""
    resultat: str = ""


@dataclass
class Etat:
    corpus: Corpus
    mails_envoyes: List[Dict[str, str]] = field(default_factory=list)
    fichiers_ecrits: List[Dict[str, str]] = field(default_factory=list)
    redemarrages: List[str] = field(default_factory=list)
    trace: List[AppelOutil] = field(default_factory=list)


class Outils:
    """Les cinq outils. Aucune protection ici : c'est le systeme nu."""

    NOMS = ["read_log", "search_doc", "restart_equipment",
            "send_email", "write_file"]

    SCHEMA = {
        "read_log": {"equipment": "str"},
        "search_doc": {"query": "str"},
        "restart_equipment": {"equipment": "str"},
        "send_email": {"recipient": "str", "subject": "str", "body": "str"},
        "write_file": {"path": "str", "content": "str"},
    }

    def __init__(self, etat: Etat):
        self.etat = etat

    # --- lecture ------------------------------------------------------

    def read_log(self, equipment: str) -> Fragment:
        c = self.etat.corpus
        lignes = [l for l in c.journaux if l.equipment == equipment][-7:]
        tickets = [t for t in c.tickets if t.equipment == equipment]
        blocs = [f"{l.horodatage} {l.mesure}"
                 + (f"  # {l.commentaire}" if l.commentaire else "")
                 for l in lignes]
        for t in tickets:
            blocs.append(f"[{t.id}] ({t.auteur}, {t.statut}) {t.description}")
        origine = "interne"
        if any(t.externe for t in tickets) or any(l.commentaire for l in lignes):
            origine = "externe"
        return Fragment("\n".join(blocs) or "(aucune donnee)", origine,
                        f"journal:{equipment}")

    def search_doc(self, query: str) -> Fragment:
        c = self.etat.corpus
        mots = [m for m in query.lower().split() if len(m) > 3]
        blocs, origine = [], "interne"
        for f in c.fiches:
            cible = (f.titre + " " + f.content).lower()
            if not mots or any(m in cible for m in mots):
                blocs.append(f"[{f.id}] {f.titre}\n{f.content}")
                if f.injectable:
                    origine = "externe"
        for m in c.mails:
            if not mots or any(mo in (m.subject + m.body).lower() for mo in mots):
                blocs.append(f"[{m.id}] de {m.expediteur} : {m.subject}\n{m.body}")
                if m.injectable:
                    origine = "externe"
        return Fragment("\n\n".join(blocs[:5]) or "(aucun resultat)", origine,
                        f"doc:{query[:30]}")

    # --- action -------------------------------------------------------

    def restart_equipment(self, equipment: str) -> Fragment:
        self.etat.redemarrages.append(equipment)
        return Fragment(f"{equipment} restarted.", "interne", "action")

    def send_email(self, recipient: str, subject: str, body: str) -> Fragment:
        self.etat.mails_envoyes.append(
            {"recipient": recipient, "subject": subject, "body": body})
        return Fragment(f"Email sent to {recipient}.", "interne", "action")

    def write_file(self, path: str, content: str) -> Fragment:
        self.etat.fichiers_ecrits.append({"path": path, "content": content})
        return Fragment(f"Written in {path}.", "interne", "action")

    # --- repartition --------------------------------------------------

    def appeler(self, nom: str, args: Dict[str, Any]) -> Fragment:
        if nom not in self.NOMS:
            return Fragment(f"Outil inconnu : {nom}", "systeme", "erreur")
        attendus = self.SCHEMA[nom]
        propres = {k: str(args.get(k, "")) for k in attendus}
        return getattr(self, nom)(**propres)


def domaine_de(adresse: str) -> str:
    return adresse.split("@")[-1].strip().lower() if "@" in adresse else ""


def est_interne(adresse: str) -> bool:
    d = domaine_de(adresse)
    return any(d == x or d.endswith("." + x) for x in DOMAINES_INTERNES)
