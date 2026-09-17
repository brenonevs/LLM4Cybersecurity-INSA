"""Journal JSONL optionnel. Observation uniquement, jamais reinjecte au modele."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def lire_evenements(chemin):
    texte = Path(chemin).read_text(encoding="utf-8")
    decodeur = json.JSONDecoder()
    evenements = []
    indice = 0
    while indice < len(texte):
        while indice < len(texte) and texte[indice].isspace():
            indice += 1
        if indice >= len(texte):
            break
        objet, fin = decodeur.raw_decode(texte, indice)
        evenements.append(objet)
        indice = fin
    return evenements


class Journal:
    def __init__(self, chemin):
        chemin = Path(chemin).expanduser()
        if not chemin.is_absolute() and chemin.parent == Path("."):
            chemin = Path(__file__).resolve().parents[1] / "logs" / chemin.name
        chemin.parent.mkdir(parents=True, exist_ok=True)
        self.chemin = chemin.resolve()
        self.fichier = self.chemin.open("a", encoding="utf-8")
        self.campagne = uuid4().hex
        self.execution = None
        self.derniere_execution = None
        self.etape = None

    def noter(self, evenement, **donnees):
        entree = {
            "version": 2,
            "date_utc": datetime.now(timezone.utc).isoformat(),
            "campagne": self.campagne,
            "execution": self.execution,
            "etape": self.etape,
            "evenement": evenement,
            **donnees,
        }
        self.fichier.write(json.dumps(entree, ensure_ascii=False, indent=2))
        self.fichier.write("\n\n")
        self.fichier.flush()

    def commencer(self, cas, tache, max_etapes):
        self.execution = uuid4().hex
        self.derniere_execution = self.execution
        self.etape = None
        self.noter("execution_debut", cas=cas, tache=tache, max_etapes=max_etapes)
        print(f"[journal] {cas} | execution={self.execution[:8]} | debut")

    def terminer(self, raison, appels, reponse):
        self.noter("execution_fin", raison=raison, appels=appels, reponse=reponse)
        print(f"[journal] fin={raison} | appels={appels}")
        self.execution = None
        self.etape = None

    def fermer(self):
        self.fichier.close()
