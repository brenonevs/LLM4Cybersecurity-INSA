"""
Etat du systeme et les cinq outils de l'agent.

Chaque resultat d'outil est un Fragment qui indique de quelle source il
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
    outil: str
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

    NOMS = ["read_log", "search_document", "restart_equipment",
            "send_email", "write_file"]

    SCHEMA = {
        "read_log": {"equipement": "str"},
        "search_document": {"requete": "str"},
        "restart_equipment": {"equipement": "str"},
        "send_email": {"destinataire": "str", "sujet": "str", "corps": "str"},
        "write_file": {"chemin": "str", "contenu": "str"},
    }

    def __init__(self, etat: Etat):
        self.etat = etat

    # --- lecture ------------------------------------------------------

    def read_log(self, equipement: str) -> Fragment:
        c = self.etat.corpus
        lignes = [l for l in c.journaux if l.equipement == equipement][-7:]
        tickets = [t for t in c.tickets if t.equipement == equipement]
        blocs = [f"{l.horodatage} {l.mesure}"
                 + (f"  # {l.commentaire}" if l.commentaire else "")
                 for l in lignes]
        for t in tickets:
            blocs.append(f"[{t.id}] ({t.auteur}, {t.statut}) {t.description}")
        origine = "interne"
        if any(t.externe for t in tickets) or any(l.commentaire for l in lignes):
            origine = "externe"
        return Fragment("\n".join(blocs) or "(aucune donnee)", origine,
                        f"journal:{equipement}")

    def search_document(self, requete: str) -> Fragment:
        c = self.etat.corpus
        mots = [m for m in requete.lower().split() if len(m) > 3]
        blocs, origine = [], "interne"
        for f in c.fiches:
            cible = (f.titre + " " + f.contenu).lower()
            if not mots or any(m in cible for m in mots):
                blocs.append(f"[{f.id}] {f.titre}\n{f.contenu}")
                if f.injectable:
                    origine = "externe"
        for m in c.mails:
            if not mots or any(mo in (m.sujet + m.corps).lower() for mo in mots):
                blocs.append(f"[{m.id}] de {m.expediteur} : {m.sujet}\n{m.corps}")
                if m.injectable:
                    origine = "externe"
        return Fragment("\n\n".join(blocs[:5]) or "(aucun resultat)", origine,
                        f"doc:{requete[:30]}")

    # --- action -------------------------------------------------------

    def restart_equipment(self, equipement: str) -> Fragment:
        self.etat.redemarrages.append(equipement)
        return Fragment(f"{equipement} redemarre.", "interne", "action")

    def send_email(self, destinataire: str, sujet: str, corps: str) -> Fragment:
        self.etat.mails_envoyes.append(
            {"destinataire": destinataire, "sujet": sujet, "corps": corps})
        return Fragment(f"Mail envoye a {destinataire}.", "interne", "action")

    def write_file(self, chemin: str, contenu: str) -> Fragment:
        self.etat.fichiers_ecrits.append({"chemin": chemin, "contenu": contenu})
        return Fragment(f"Ecrit dans {chemin}.", "interne", "action")

    # --- repartition --------------------------------------------------

    def call(self, name: str, args: Dict[str, Any]) -> Fragment:
        if name not in self.NOMS:
            return Fragment(f"Outil inconnu : {name}", "systeme", "erreur")
        attendus = self.SCHEMA[name]
        propres = {k: str(args.get(k, "")) for k in attendus}
        return getattr(self, name)(**propres)


def domain_of(adresse: str) -> str:
    return adresse.split("@")[-1].strip().lower() if "@" in adresse else ""


def is_internal(adresse: str) -> bool:
    d = domain_of(adresse)
    return any(d == x or d.endswith("." + x) for x in DOMAINES_INTERNES)
