"""Journal JSONL optionnel. Observation uniquement, jamais reinjecte au modele."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def read_events(chemin):
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


def _shorten(texte, limite=100):
    texte = " ".join(str(texte).split())
    if len(texte) <= limite:
        return texte
    return texte[: limite - 1] + "…"


def _readable_args(args, limite=120):
    if not args:
        return ""
    parts = []
    for cle, valeur in args.items():
        parts.append(f"{cle}={_shorten(valeur, 40)}")
    return _shorten(", ".join(parts), limite)


def _execution_type(cas):
    nome = str(cas or "")
    if nome.startswith("calibration:") or nome == "attaque":
        return "ATAQUE"
    if nome.startswith("T") and len(nome) <= 4:
        return "TAREFA LEGITIMA"
    if nome.startswith("diagnostic") or nome.startswith("demo:"):
        return "TESTE"
    return "EXECUCAO"


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
        self.max_etapes = None
        self.cas = None
        self.tipo = None
        self.progresso_fase = None
        self.progresso_indice = None
        self.progresso_total = None
        self.campanha_indice = None
        self.campanha_total = None

    def prepare_progress(self, fase, indice, total, campanha_indice=None, campanha_total=None):
        self.progresso_fase = fase
        self.progresso_indice = indice
        self.progresso_total = total
        self.campanha_indice = campanha_indice
        self.campanha_total = campanha_total

    def _progress_line(self):
        if self.progresso_indice is None or self.progresso_total is None:
            return None
        fase = self.progresso_fase or self.tipo or "EXECUCAO"
        linha = f"{fase} {self.progresso_indice}/{self.progresso_total}"
        if self.campanha_indice is not None and self.campanha_total is not None:
            linha += f" | campanha {self.campanha_indice}/{self.campanha_total}"
        return linha

    def log(self, evenement, **donnees):
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

    def start(self, cas, tache, max_etapes):
        self.execution = uuid4().hex
        self.derniere_execution = self.execution
        self.etape = None
        self.max_etapes = max_etapes
        self.cas = cas
        self.tipo = _execution_type(cas)
        self.log("execution_debut", cas=cas, tache=tache, max_etapes=max_etapes)
        progresso = self._progress_line()
        if progresso:
            print(f"[journal] -------- {self.tipo} | debut | {progresso} --------")
        else:
            print(f"[journal] -------- {self.tipo} | debut --------")
        print(f"[journal] cas={cas} | execution={self.execution[:8]}")
        print(f"[journal]   pedido: {_shorten(tache, 140)}")

    def announce_step(self, numero):
        total = self.max_etapes if self.max_etapes is not None else "?"
        tipo = self.tipo or "EXECUCAO"
        progresso = self._progress_line()
        if progresso:
            print(f"[journal] [{tipo}] etape {numero}/{total} | {progresso}")
        else:
            print(f"[journal] [{tipo}] etape {numero}/{total}")

    def announce_decision(self, action):
        if "fin" in action:
            print("[journal]   decision: fin")
            return
        outil = str(action.get("outil", "")).strip() or "?"
        args = _readable_args(action.get("args") or {})
        detail = f"{outil}({args})" if args else f"{outil}()"
        print(f"[journal]   decision: {detail}")

    def announce_tool(self, outil, args, autorise, motif=""):
        if autorise:
            print(f"[journal]   outil: {outil} | ok")
        else:
            print(f"[journal]   outil: {outil} | REFUS | {_shorten(motif, 80)}")

    def announce_result(self, outil, texte):
        print(f"[journal]   resultat: {_shorten(texte, 120)}")

    def finish(self, raison, appels, reponse):
        self.log("execution_fin", raison=raison, appels=appels, reponse=reponse)
        tipo = self.tipo or "EXECUCAO"
        progresso = self._progress_line()
        if progresso:
            print(f"[journal] -------- {tipo} | fin | completos {progresso} --------")
        else:
            print(f"[journal] -------- {tipo} | fin --------")
        print(f"[journal] cas={self.cas} | raison={raison} | appels={appels}")
        if reponse:
            print(f"[journal]   reponse: {_shorten(reponse, 140)}")
        self.execution = None
        self.etape = None
        self.max_etapes = None
        self.cas = None
        self.tipo = None

    def close(self):
        self.fichier.close()
