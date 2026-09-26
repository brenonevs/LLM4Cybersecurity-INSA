"""
Etat du systeme et les cinq outils de l'agent.

Chaque resultat d'outil est un Fragment qui indique de quelle source il
provient. Rien n'exploite cette information : le terrain est livre vulnerable.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from .corpus import Corpus, DOMAINES_INTERNES

ORIGINES = ["systeme", "utilisateur", "interne", "externe"]


@dataclass(frozen=True)
class SourceReference:
    """One corpus field that contributed data to a tool result.

    `key` is stable across executions with the same corpus. Axis B will use it
    as the identity whose confidence is recorded over time. `actor` describes
    the declared producer of that field; it is metadata, not a trust decision.
    """
    key: str
    kind: str
    record_id: str
    field: str
    origin: str
    actor: str
    content_type: str = "text"

    def as_dict(self) -> Dict[str, str]:
        return {
            "key": self.key,
            "kind": self.kind,
            "record_id": self.record_id,
            "field": self.field,
            "origin": self.origin,
            "actor": self.actor,
            "content_type": self.content_type,
        }


@dataclass(frozen=True)
class SourceEvidence:
    """One exact corpus value paired with the metadata that identifies it.

    Fragment.texte remains the combined text shown to the model.  Axis B uses
    this structure to distinguish the individual value of one source field
    from the rest of that combined result.
    """
    reference: SourceReference
    content: str


@dataclass
class Fragment:
    texte: str
    origine: str = "externe"
    source: str = "?"
    sources: List[SourceReference] = field(default_factory=list)
    evidences: List[SourceEvidence] = field(default_factory=list)


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
        lignes = [(i, l) for i, l in enumerate(c.journaux)
                  if l.equipement == equipement][-7:]
        tickets = [t for t in c.tickets if t.equipement == equipement]
        blocs = [f"{l.horodatage} {l.mesure}"
                 + (f"  # {l.commentaire}" if l.commentaire else "")
                 for _, l in lignes]
        sources, evidences = [], []
        for i, ligne in lignes:
            author = c.authors[ligne.author_id]
            reference = SourceReference(
                f"journal:{i}:horodatage", "journal", str(i), "horodatage",
                author.origin, author.id, "timestamp")
            sources.append(reference)
            evidences.append(SourceEvidence(reference, ligne.horodatage))
            reference = SourceReference(
                f"journal:{i}:mesure", "journal", str(i), "mesure",
                author.origin, author.id, "measure")
            sources.append(reference)
            evidences.append(SourceEvidence(reference, ligne.mesure))
            if ligne.commentaire:
                reference = SourceReference(
                    f"journal:{i}:commentaire", "journal", str(i), "commentaire",
                    author.origin, author.id)
                sources.append(reference)
                evidences.append(SourceEvidence(reference, ligne.commentaire))
        for t in tickets:
            author = c.authors[t.author_id]
            blocs.append(f"[{t.id}] ({t.author_id}, {t.statut}) {t.description}")
            reference = SourceReference(
                f"ticket:{t.id}:statut", "ticket", t.id, "statut",
                author.origin, author.id, "status")
            sources.append(reference)
            evidences.append(SourceEvidence(reference, t.statut))
            reference = SourceReference(
                f"ticket:{t.id}:description", "ticket", t.id, "description",
                author.origin, author.id)
            sources.append(reference)
            evidences.append(SourceEvidence(reference, t.description))
        origine = "externe" if any(source.origin == "externe" for source in sources) else "interne"
        return Fragment("\n".join(blocs) or "(aucune donnee)", origine,
                        f"journal:{equipement}", sources, evidences)

    def search_document(self, requete: str) -> Fragment:
        c = self.etat.corpus
        mots = [m for m in requete.lower().split() if len(m) > 3]
        blocs, evidences, origine = [], [], "interne"
        for f in c.fiches:
            cible = (f.titre + " " + f.contenu).lower()
            if not mots or any(m in cible for m in mots):
                author = c.authors[f.author_id]
                title_reference = SourceReference(
                    f"fiche:{f.id}:titre", "fiche", f.id, "titre",
                    author.origin, author.id, "text")
                content_reference = SourceReference(
                    f"fiche:{f.id}:contenu", "fiche", f.id, "contenu",
                    author.origin, author.id)
                blocs.append((f"[{f.id}] {f.titre}\n{f.contenu}",
                              (title_reference, content_reference)))
                evidences.extend((SourceEvidence(title_reference, f.titre),
                                  SourceEvidence(content_reference, f.contenu)))
                if author.origin == "externe":
                    origine = "externe"
        for m in c.mails:
            if not mots or any(mo in (m.sujet + m.corps).lower() for mo in mots):
                author = c.authors[m.author_id]
                sender_reference = SourceReference(
                    f"mail:{m.id}:expediteur", "mail", m.id, "expediteur",
                    author.origin, author.id, "email_address")
                subject_reference = SourceReference(
                    f"mail:{m.id}:sujet", "mail", m.id, "sujet",
                    author.origin, author.id, "text")
                body_reference = SourceReference(
                    f"mail:{m.id}:corps", "mail", m.id, "corps",
                    author.origin, author.id)
                blocs.append((f"[{m.id}] de {m.expediteur} : {m.sujet}\n{m.corps}",
                              (sender_reference, subject_reference, body_reference)))
                evidences.extend((SourceEvidence(sender_reference, m.expediteur),
                                  SourceEvidence(subject_reference, m.sujet),
                                  SourceEvidence(body_reference, m.corps)))
                if author.origin == "externe":
                    origine = "externe"
        visibles = blocs[:5]
        visible_references = {reference for _, references in visibles for reference in references}
        return Fragment("\n\n".join(texte for texte, _ in visibles) or "(aucun resultat)",
                        origine, f"doc:{requete[:30]}",
                        [reference for _, references in visibles for reference in references],
                        [evidence for evidence in evidences
                         if evidence.reference in visible_references])

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
