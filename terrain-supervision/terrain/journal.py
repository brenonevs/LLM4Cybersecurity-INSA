"""Human-readable execution report. It is never sent back to the model."""
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def lire_evenements(chemin):
    """Read legacy JSON/JSONL logs created before the readable report format."""
    texte = Path(chemin).read_text(encoding="utf-8")
    decodeur = json.JSONDecoder()
    evenements, indice = [], 0
    while indice < len(texte):
        while indice < len(texte) and texte[indice].isspace():
            indice += 1
        if indice >= len(texte):
            break
        objet, indice = decodeur.raw_decode(texte, indice)
        evenements.append(objet)
    return evenements


def _shorten(text, limit=100):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _readable_args(args, limit=120):
    if not args:
        return ""
    return _shorten(", ".join(f"{key}={_shorten(value, 40)}"
                    for key, value in args.items()), limit)


def _human_date(value):
    """Render an ISO timestamp as a date intended for a person to read."""
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return moment.astimezone(timezone.utc).strftime("%d %B %Y, %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def _execution_type(case):
    name = str(case or "")
    if name.startswith("calibration:") or name == "attaque":
        return "ATTACK"
    if name.startswith("T") and len(name) <= 4:
        return "LEGITIMATE TASK"
    if name.startswith("diagnostic") or name.startswith("demo:"):
        return "TEST"
    return "EXECUTION"


class Journal:
    """Write an English report organized around campaigns, executions, and steps."""
    def __init__(self, path):
        path = Path(path).expanduser()
        if not path.is_absolute() and path.parent == Path("."):
            path = Path(__file__).resolve().parents[1] / "logs" / path.name
        if path.suffix == ".jsonl":
            path = path.with_suffix(".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        self.chemin = path.resolve()
        self.fichier = self.chemin.open("a", encoding="utf-8")
        self.evenements = []
        self.campagne = uuid4().hex
        self.execution = self.derniere_execution = self.etape = self.max_etapes = None
        self.cas = self.tipo = None
        self.progresso_fase = self.progresso_indice = self.progresso_total = None
        self.campanha_indice = self.campanha_total = None

    def _write(self, text=""):
        self.fichier.write(text + "\n")
        self.fichier.flush()

    def _heading(self, title):
        self._write()
        self._write("=" * 88)
        self._write(title)
        self._write("=" * 88)

    def _label(self, label, value):
        self._write(f"{label}: {value}")

    def _block(self, label, text):
        self._write(f"{label}:")
        for line in str(text or "(empty)").splitlines() or ["(empty)"]:
            self._write(f"  {line}")

    def _messages(self, messages):
        labels = {
            "system": "SYSTEM INSTRUCTIONS",
            "assistant": "PREVIOUS MODEL RESPONSE",
        }
        self._write(f"MODEL INPUT — {len(messages)} message(s)")
        for index, message in enumerate(messages, 1):
            content = str(message.get("content", ""))
            if message.get("role") == "user":
                if content.startswith("Technician request:"):
                    label = "ORIGINAL TECHNICIAN TASK"
                elif content.startswith("Tool result:"):
                    label = "TOOL RESULT PROVIDED TO MODEL"
                elif content.startswith("Checklist of explicit request requirements:"):
                    label = "TASK CHECKLIST"
                elif content.startswith("Current task state,"):
                    label = "TASK STATE"
                else:
                    label = "USER MESSAGE"
            else:
                label = labels.get(message.get("role"), f"MESSAGE ({message.get('role', '?')})")
            self._block(f"[{index}] {label}", content)

    def _sources(self, sources):
        self._write("Sources visible in this result:")
        if not sources:
            self._write("  (none)")
            return
        for source in sources:
            self._write(
                "  - {key} | kind={kind} | field={field} | origin={origin} | actor={actor}".format(
                    key=source.get("key", "?"), kind=source.get("kind", "?"),
                    field=source.get("field", "?"), origin=source.get("origin", "?"),
                    actor=source.get("actor", "?")))

    def preparar_progresso(self, phase, index, total, campaign_index=None, campaign_total=None):
        self.progresso_fase = phase
        self.progresso_indice = index
        self.progresso_total = total
        self.campanha_indice = campaign_index
        self.campanha_total = campaign_total

    def _progress_line(self):
        if self.progresso_indice is None or self.progresso_total is None:
            return None
        line = f"{self.progresso_fase or self.tipo or 'EXECUTION'} {self.progresso_indice}/{self.progresso_total}"
        if self.campanha_indice is not None and self.campanha_total is not None:
            line += f" | campaign {self.campanha_indice}/{self.campanha_total}"
        return line

    def noter(self, evenement, **donnees):
        entry = {
            "version": 3,
            "date_utc": datetime.now(timezone.utc).isoformat(),
            "campagne": self.campagne,
            "execution": self.execution,
            "etape": self.etape,
            "evenement": evenement,
            **donnees,
        }
        self.evenements.append(entry)
        self._write_event(entry)

    def _write_event(self, event):
        name = event["evenement"]
        if name == "campagne_debut":
            self._heading("CAMPAIGN START")
            labels = {
                "date_utc": "Date and time (UTC)",
                "commande": "Command",
                "modele": "Model provider",
                "ollama_modele": "Ollama model",
                "protections": "Protections",
                "corpus_version": "Corpus version",
                "graine": "Corpus seed",
                "official_calibration_version": "Official calibration version",
                "historique_version": "History version",
                "limite_resultat_modele": "Per-result model limit",
                "budget_resultats_modele": "Model result budget",
                "systeme_version": "System prompt version",
            }
            for key, label in labels.items():
                if key in event:
                    self._label(label, _human_date(event[key]) if key == "date_utc" else event[key])
        elif name == "execution_debut":
            self._heading(f"{self.tipo}: {event['cas']}")
            self._label("Execution ID", event["execution"])
            if self._progress_line():
                self._label("Progress", self._progress_line())
            self._block("Technician task", event["tache"])
            self._label("Maximum steps", event["max_etapes"])
        elif name == "etape_debut":
            self._write()
            self._write(f"--- STEP {event['etape']}/{self.max_etapes} ---")
        elif name == "modele_requete":
            self._write("MODEL REQUEST")
            self._label("Endpoint", event["url"])
            request = event["charge"]
            self._label("Model", request.get("model", "?"))
            options = request.get("options", {})
            if options:
                self._label("Options", ", ".join(f"{key}={value}" for key, value in options.items()))
            self._label("Structured output", "enabled" if request.get("format") else "disabled")
            self._messages(request.get("messages", []))
        elif name == "modele_reponse":
            self._write("MODEL OUTPUT (RAW RESPONSE)")
            response = event["reponse"]
            self._block("Exact response returned by the model",
                        response.get("message", {}).get("content", ""))
            metadata = [f"{key}={response[key]}" for key in
                        ("done_reason", "prompt_eval_count", "eval_count", "total_duration")
                        if key in response]
            if metadata:
                self._label("Response metadata", ", ".join(metadata))
        elif name == "decision":
            self._write("MODEL DECISION")
            action = event["action"]
            if "fin" in action:
                self._block("Final response", action["fin"])
            else:
                self._label("Tool", action.get("outil", "?"))
                for key, value in (action.get("args") or {}).items():
                    self._block(f"Argument {key}", value)
        elif name == "outil_decision":
            self._write("TOOL AUTHORIZATION")
            self._label("Tool", event["outil"])
            self._label("Status", "ALLOWED" if event["autorise"] else "REFUSED")
            if event.get("motif"):
                self._block("Reason", event["motif"])
        elif name == "outil_resultat":
            self._write("TOOL RESULT")
            self._label("Tool", event["outil"])
            self._label("Aggregate origin", event.get("origine", "?"))
            self._label("Aggregate source", event.get("source", "?"))
            self._block("Full result", event.get("texte_complet", ""))
            self._sources(event.get("sources", []))
        elif name == "execution_fin":
            self._write("EXECUTION END")
            self._label("Reason", event["raison"])
            self._label("Tool calls", event["appels"])
            self._block("Final response", event["reponse"])
        elif name == "calibration_verdict":
            self._write("CALIBRATION ATTACK VERDICT")
            self._label("Case", event["cas"])
            self._label("Intended objective", event["objectif_prevu"])
            self._label("Intended objective reached", event["objectif_prevu_atteint"])
            self._label("Any prohibited effect", event["verdict"]["reussie"])
            self._label("Prohibited effects", ", ".join(event["verdict"]["objectifs_atteints"]) or "none")
        elif name == "tache_verdict":
            self._write("LEGITIMATE TASK VERDICT")
            self._label("Case", event["cas"])
            self._label("Completed correctly", event["reussie"])
        elif name == "attaque_verdict":
            self._write("ATTACK VERDICT")
            self._label("Case", event["cas"])
            self._label("Any prohibited effect", event["verdict"]["reussie"])
            self._label("Prohibited effects", ", ".join(event["verdict"]["objectifs_atteints"]) or "none")
        elif name in ("modele_erreur", "execution_erreur"):
            self._write("ERROR")
            self._label("Type", event["type"])
            self._block("Message", event["message"])
        elif name == "campagne_fin":
            self._heading("CAMPAIGN END")
            self._label("Reason", event["raison"])
        else:
            self._write(f"EVENT: {name}")

    def commencer(self, cas, tache, max_etapes):
        self.execution = uuid4().hex
        self.derniere_execution = self.execution
        self.etape, self.max_etapes = None, max_etapes
        self.cas, self.tipo = cas, _execution_type(cas)
        self.noter("execution_debut", cas=cas, tache=tache, max_etapes=max_etapes)
        progress = self._progress_line()
        print(f"[journal] -------- {self.tipo} | start{f' | {progress}' if progress else ''} --------")
        print(f"[journal] case={cas} | execution={self.execution[:8]}")
        print(f"[journal]   task: {_shorten(tache, 140)}")

    def annoncer_etape(self, number):
        progress = self._progress_line()
        print(f"[journal] [{self.tipo or 'EXECUTION'}] step {number}/{self.max_etapes or '?'}"
              f"{f' | {progress}' if progress else ''}")

    def annoncer_decision(self, action):
        if "fin" in action:
            print("[journal]   decision: fin")
            return
        tool = str(action.get("outil", "")).strip() or "?"
        args = _readable_args(action.get("args") or {})
        print(f"[journal]   decision: {tool}({args})" if args else f"[journal]   decision: {tool}()")

    def annoncer_outil(self, tool, args, allowed, reason=""):
        print(f"[journal]   tool: {tool} | {'allowed' if allowed else 'REFUSED'}"
              f"{f' | {_shorten(reason, 80)}' if reason else ''}")

    def annoncer_resultat(self, tool, text):
        print(f"[journal]   result: {_shorten(text, 120)}")

    def terminer(self, reason, calls, response):
        self.noter("execution_fin", raison=reason, appels=calls, reponse=response)
        progress = self._progress_line()
        print(f"[journal] -------- {self.tipo or 'EXECUTION'} | end"
              f"{f' | {progress}' if progress else ''} --------")
        print(f"[journal] case={self.cas} | reason={reason} | tool calls={calls}")
        if response:
            print(f"[journal]   response: {_shorten(response, 140)}")
        self.execution = self.etape = self.max_etapes = None
        self.cas = self.tipo = None

    def fermer(self):
        self.fichier.close()
