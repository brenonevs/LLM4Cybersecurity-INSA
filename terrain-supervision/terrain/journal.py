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


def _parse_json_value(text):
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    if isinstance(value, (dict, list)):
        return value
    return None


def _render_value(value, indent=0):
    """Show structured model text with its original paragraphs and lists."""
    pad = "  " * indent
    if isinstance(value, dict):
        if not value:
            return [f"{pad}(empty)"]
        lines = []
        for key, item in value.items():
            if isinstance(item, str) and "\n" in item:
                lines.append(f"{pad}{key}:")
                lines.extend(f"{pad}  {line}" for line in item.splitlines())
            elif isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.extend(_render_value(item, indent + 1))
            else:
                lines.append(f"{pad}{key}: {item}")
        return lines
    if isinstance(value, list):
        if not value:
            return [f"{pad}(empty)"]
        lines = []
        for item in value:
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}-")
                lines.extend(_render_value(item, indent + 1))
            else:
                rendered = str(item)
                if "\n" in rendered:
                    lines.append(f"{pad}-")
                    lines.extend(f"{pad}  {line}" for line in rendered.splitlines())
                else:
                    lines.append(f"{pad}- {rendered}")
        return lines
    return [f"{pad}{value}"]


def _pretty_content(text):
    """Keep the sent text, expanding one-line JSON into readable sections."""
    original = str(text or "")
    stripped = original.strip()
    prefix = ""
    payload = stripped
    marker = "Tool result: "
    if stripped.startswith(marker):
        prefix = "Tool result"
        payload = stripped[len(marker):].strip()
    parsed = _parse_json_value(payload)
    if parsed is None:
        return original
    lines = _render_value(parsed)
    if prefix:
        return prefix + "\n" + "\n".join(lines)
    return "\n".join(lines)


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

    def _rule(self, char, title):
        self._write()
        self._write(char * 88)
        self._write(title)
        self._write(char * 88)

    def _heading(self, title):
        self._rule("=", title)

    def _step_heading(self, title):
        self._rule("#", title)

    def _section(self, title):
        self._rule("-", title)

    def _subsection(self, title):
        self._write()
        self._write(title)
        self._write("." * len(title))

    def _label(self, label, value):
        self._write(f"{label}: {value}")

    def _block(self, label, text):
        self._write(f"{label}:")
        for line in str(text or "(empty)").splitlines() or ["(empty)"]:
            self._write(f"  {line}")

    def _indented(self, text):
        for line in str(text or "(empty)").splitlines() or ["(empty)"]:
            self._write(f"  {line}")

    def _messages(self, messages):
        labels = {
            "system": "SYSTEM INSTRUCTIONS",
            "assistant": "PREVIOUS MODEL RESPONSE",
        }
        self._subsection(f"MODEL INPUT — {len(messages)} message(s)")
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
            self._subsection(f"[{index}] {label}")
            self._indented(_pretty_content(content))

    def _sources(self, sources):
        self._subsection("Sources visible in this result")
        if not sources:
            self._write("  (none)")
            return
        for source in sources:
            self._write("  {key}".format(key=source.get("key", "?")))
            self._write("    kind: {kind}".format(kind=source.get("kind", "?")))
            self._write("    field: {field}".format(field=source.get("field", "?")))
            self._write("    type: {content_type}".format(
                content_type=source.get("content_type", "?")))
            self._write("    origin: {origin}".format(origin=source.get("origin", "?")))
            self._write("    actor: {actor}".format(actor=source.get("actor", "?")))
            self._write()

    def _axis_b_observations(self, observations):
        if not observations:
            return
        self._section("Trust calculation")
        self._write("AXIS B EVIDENCE ASSESSMENT")
        counts = {}
        for item in observations:
            update = item.get("trust_update", "none")
            counts[update] = counts.get(update, 0) + 1
        summary = ", ".join(
            f"{update} x{count}" if count > 1 else update
            for update, count in counts.items())
        self._label("Fields assessed", len(observations))
        self._label("Updates in this result", summary or "none")
        for item in observations:
            self._subsection(item.get("source_key", "?"))
            self._label("  Author", item.get("author_id", "?"))
            self._label("  Category", item.get("record_kind", "?"))
            self._label("  Content type", item.get("content_type", "not recorded"))
            if "content" in item:
                self._subsection("  Exact field content evaluated")
                self._indented(_pretty_content(str(item["content"])))
            self._subsection("  Assessment")
            self._label("    Result", item.get("result", "?"))
            self._label("    Severity", item.get("severity", "?"))
            weight = item.get("weight", 0)
            self._label("    Weight", f"{weight:g}" if isinstance(weight, (int, float)) else weight)
            self._label("    Reasons", ", ".join(item.get("reasons") or []) or "none")
            lexical_checks = item.get("lexical_checks", [])
            if lexical_checks:
                self._subsection("  Lexical analysis")
                self._write("    The exact field content above was normalized for case, Unicode, and spacing.")
                for check in lexical_checks:
                    status = "MATCHED" if check.get("matched") else "not matched"
                    self._write(f"    - {check.get('name', '?')}: {status}")
            elif item.get("content_type") in {"timestamp", "measure", "status", "email_address"}:
                self._subsection("  Lexical analysis")
                self._write("    Not run: the declared structured type was validated first.")
            signals = item.get("signals", [])
            self._subsection("  Evidence")
            if signals:
                self._write("    Beta evidence after duplicate removal:")
                for signal in signals:
                    self._write("      - {kind}: weight={weight:g}; origin={origin}".format(
                        **signal))
            else:
                self._write("    Beta evidence after duplicate removal: none")
            semantic = item.get("semantic")
            if semantic:
                self._subsection("  Semantic analysis")
                self._write(
                    "    semantic observation ({protocol}): category={category}; "
                    "strength={score:.2f}; candidate={candidate}".format(**semantic))
                self._write(
                    "    matched concepts: " +
                    (", ".join(semantic["matched_concepts"]) or "none"))
                self._write("    contextual reasons: " +
                            (", ".join(semantic["reasons"]) or "none"))
                self._write(f"    closest reference: {semantic['reference']}")
                self._write("    semantic result: included only through the evidence list above")
                self._subsection("  Syntactic analysis")
                if semantic.get("candidate"):
                    self._write("    Contextual analysis identified a candidate. Any syntactic signal is listed in Evidence above.")
                else:
                    self._write("    No standalone syntactic signal was emitted. The current design only emits syntactic evidence when contextual analysis identifies a risky candidate.")
            embedding = item.get("embedding")
            if embedding:
                self._subsection("  Embedding")
                self._write(
                    "    embedding observation ({protocol}): category={category}; "
                    "attack={attack_similarity:.3f}; legitimate={legitimate_similarity:.3f}; "
                    "margin={margin:.3f}; qualified={qualified}; support={support_weight:g}".format(
                        **embedding))
                if embedding["support_weight"]:
                    self._write("    embedding result: included only through the evidence list above")
                else:
                    self._write("    embedding result: recorded without a beta change")
            self._subsection("  Trust calculation")
            self._write(
                "    Alpha: {alpha_before} -> {alpha_after}".format(**item))
            self._write(
                "    Beta: {beta_before} -> {beta_after}".format(**item))
            self._write(f"    Applied update: {item['trust_update']}")
            if item.get("recent_risk_update") not in {None, "disabled"}:
                self._write(
                    "    Recent risk: {recent_risk_before:.2f} -> "
                    "{recent_risk_after:.2f} ({recent_risk_update})".format(**item))
            if item.get("version"):
                self._write(f"    Content version (SHA-256): {item['version']}")

    def _combined_risks(self, risks):
        if not risks:
            return
        self._section("Cross-field risk correlation")
        self._write("AXIS B COMBINED RISK")
        for risk in risks:
            self._subsection(risk.get("category", "combined risk"))
            self._label("  Scope", risk.get("scope", "?"))
            self._label("  Activated", risk.get("activated", False))
            self._label("  Components", ", ".join(risk.get("components", [])) or "none")
            self._write("  Fields involved:")
            for key in risk.get("source_keys", []):
                self._write(f"    - {key}")
            self._write("  Source categories:")
            for source in risk.get("source_categories", []):
                self._write("    - {author}/{category}".format(**source))

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
                "trust_authorization": "Trust authorization",
                "trust_decay_factor": "Trust decay factor",
                "trust_recent_risk": "Recent-risk memory",
                "trust_recent_risk_recovery": "Recent-risk recovery",
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
            self._step_heading(f"STEP {event['etape']}/{self.max_etapes}")
        elif name == "modele_requete":
            self._section("Model call")
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
            self._section("Model response")
            self._write("MODEL OUTPUT (RAW RESPONSE)")
            response = event["reponse"]
            content = response.get("message", {}).get("content", "")
            self._subsection("Exact response returned by the model")
            self._indented(_pretty_content(content))
            metadata = [f"{key}={response[key]}" for key in
                        ("done_reason", "prompt_eval_count", "eval_count", "total_duration")
                        if key in response]
            if metadata:
                self._label("Response metadata", ", ".join(metadata))
        elif name == "decision":
            self._section("Decision")
            self._write("MODEL DECISION")
            action = event["action"]
            if "fin" in action:
                self._block("Final response", action["fin"])
            else:
                self._label("Tool", action.get("outil", "?"))
                for key, value in (action.get("args") or {}).items():
                    self._block(f"Argument {key}", value)
        elif name == "outil_decision":
            self._section("Tool authorization")
            self._write("TOOL AUTHORIZATION")
            self._label("Tool", event["outil"])
            self._label("Status", "ALLOWED" if event["autorise"] else "REFUSED")
            trust = event.get("trust_authorization")
            if trust:
                self._label("Required trust", f"{trust['threshold']:.2f}")
                self._label("Negative-evidence gate",
                            "ACTIVE" if trust["negative_evidence_gate"] else "NOT TRIGGERED")
                if trust.get("recent_risk_enabled"):
                    self._label("Recent-risk memory",
                                "ACTIVE" if trust.get("recent_risk_gate") else "CLEAR")
                effective = trust["effective_trust"]
                self._label("Effective trust",
                            "not applied" if effective is None else f"{effective:.2f}")
                self._write("Sources considered:")
                for source in trust["sources"]:
                    self._write("  - {author}/{category}: {trust:.2f}".format(**source))
                if trust.get("recent_risk_sources"):
                    self._write("Recent-risk sources:")
                    for source in trust["recent_risk_sources"]:
                        self._write("  - {author}/{category}: risk={risk:.2f}, "
                                    "recent trust={trust:.2f}".format(**source))
                if trust.get("combined_risk_gate"):
                    self._label("Combined task risk", "ACTIVE")
                if trust.get("combined_risks"):
                    self._write("Combined correlations considered:")
                    for risk in trust["combined_risks"]:
                        self._write("  - {category}: scope={scope}; active={activated}".format(
                            **risk))
            if event.get("motif"):
                self._block("Reason", event["motif"])
        elif name == "outil_resultat":
            self._section("Tool result")
            self._write("TOOL RESULT")
            self._label("Tool", event["outil"])
            self._label("Aggregate origin", event.get("origine", "?"))
            self._label("Aggregate source", event.get("source", "?"))
            self._block("Full result", event.get("texte_complet", ""))
            self._sources(event.get("sources", []))
            self._axis_b_observations(event.get("axis_b_observations", []))
            self._combined_risks(event.get("axis_b_combined_risks", []))
        elif name == "axis_b_episode_step":
            self._write("AXIS B CONTINUOUS EPISODE STEP")
            self._label("Step", event["label"])
            self._axis_b_observations([event["observation"]])
        elif name == "classification_case":
            self._write(f"CLASSIFICATION CASE: {event['case_id']}")
            self._label("Expected class", event["expected"])
            self._label("Outcome", event["outcome"])
            if event.get("injected_content"):
                self._block("Injected content", event["injected_content"])
            if event.get("task"):
                self._block("Legitimate task", event["task"])
            observations = event.get("semantic_observations", [])
            self._subsection("Semantic comparison (observation only)")
            if not observations:
                self._write("  (no text evidence was read)")
            for observation in observations:
                self._subsection(observation.get("source_key", "?"))
                self._write(
                    "  assessment={assessment_result}".format(**observation))
                self._write(
                    "  semantic={semantic_category} ({semantic_score:.2f}); "
                    "candidate={semantic_candidate}".format(**observation))
                self._write("  assessment reasons: " +
                            (", ".join(observation["assessment_reasons"]) or "none"))
                self._write("  Evidence")
                signals = observation["beta_signals"]
                if signals:
                    self._write("    beta evidence after duplicate removal:")
                    for signal in signals:
                        self._write("      - {kind}: weight={weight:g}; origin={origin}".format(
                            **signal))
                else:
                    self._write("    beta evidence after duplicate removal: none")
                self._write("  Semantic analysis")
                self._write("    concepts: " +
                            (", ".join(observation["matched_concepts"]) or "none"))
                self._write("    contextual reasons: " +
                            (", ".join(observation["semantic_reasons"]) or "none"))
                embedding = observation.get("embedding")
                if embedding:
                    self._write("  Embedding")
                    self._write(
                        "    embedding observation ({protocol}): category={category}; "
                        "attack={attack_similarity:.3f}; legitimate={legitimate_similarity:.3f}; "
                        "margin={margin:.3f}; qualified={qualified}; support={support_weight:g}".format(
                            **embedding))
                self._block("  Evidence text", observation["content"])
        elif name == "classification_summary":
            self._heading("AXIS B CLASSIFICATION SUMMARY")
            self._label("True positives", event["true_positive"])
            self._label("False positives", event["false_positive"])
            self._label("True negatives", event["true_negative"])
            self._label("False negatives", event["false_negative"])
            self._label("Recall", f"{event['recall']:.2%}")
            self._label("Precision", f"{event['precision']:.2%}")
            self._label("False-positive rate", f"{event['false_positive_rate']:.2%}")
            self._label("False-negative rate", f"{event['false_negative_rate']:.2%}")
            self._label("Semantic protocol", event.get("semantic_protocol", "not recorded"))
            self._label("False negatives with semantic candidate",
                        event.get("false_negative_semantic_candidates", "not recorded"))
            self._label("Legitimate semantic candidates",
                        event.get("legitimate_semantic_candidates", "not recorded"))
        elif name == "trust_lifecycle_summary":
            self._heading("AXIS B TRUST-LIFECYCLE SUMMARY")
            self._label("Initial legitimate warm-up", event["warmup_count"])
            self._label("Recovery observations measured", event["recovery_observations"])
            self._label("Decay factor", event["decay_factor"])
            self._label("Recent-risk recovery", event["recent_risk_recovery"])
            self._label("Embedding support", event["embedding_support"])
            classification = event["classification"]
            self._subsection("Detection metrics")
            self._write("  TP={true_positive}; FP={false_positive}; TN={true_negative}; "
                        "FN={false_negative}; precision={precision:.2%}; recall={recall:.2%}".format(
                            **classification))
            execution = event["execution"]
            self._subsection("Official execution metrics")
            self._write("  Attacks prevented: {attacks_prevented}/{attacks_total}".format(**execution))
            self._write("  Legitimate tasks completed: {legitimate_completed}/"
                        "{legitimate_total}".format(**execution))
            self._subsection("Patient-attacker lifecycle metrics")
            for record in event["lifecycle"]:
                self._write(
                    "  - {payload}: severity={severity}; detected={detected}; "
                    "risk_activated={risk_activated}; initially_blocked={initially_blocked}; "
                    "risk_clear_after={risk_clear_after}; tools_release_after="
                    "{tools_release_after}".format(**record))
            self._subsection("Split-attack correlation metrics")
            for record in event.get("cross_field", []):
                self._write(
                    "  - {case}: blocked_in_task={blocked_in_task}; "
                    "combined_risk_cleared_after_task={combined_risk_cleared_after_task}; "
                    "source_risk_blocks_next_task={source_risk_blocks_next_task}; "
                    "beta={beta_by_source}; "
                    "recent_risk={recent_risk_by_source}".format(**record))
        elif name == "recidivism_summary":
            self._heading("AXIS B RECIDIVISM EXPERIMENT")
            self._label("Initial legitimate warm-up", event["warmup_count"])
            self._label("Recent-risk recovery", event["recent_risk_recovery"])
            self._write("Risk escalation: first incident=1.0; later incidents=+0.5; cap=3.0")
            for scenario in event["scenarios"]:
                self._subsection(
                    f"{scenario['scenario']} / {scenario['payload']} — "
                    f"attacks={scenario['occurrences']}; "
                    f"recovery between={scenario['recovery_between']}")
                self._write("  attack | severity | alpha | beta | trust | "
                            "risk before -> after | email")
                for row in scenario["rows"]:
                    self._write(
                        "  {occurrence:6d} | {severity:8s} | {alpha:5.1f} | "
                        "{beta:4.1f} | {trust:.3f} | {risk_before:.2f} -> "
                        "{risk_after:.2f} ({risk_update}) | {email}".format(
                            **row, email="ALLOW" if row["email_allowed"] else "BLOCK"))
        elif name == "execution_fin":
            self._section("Execution result")
            self._write("EXECUTION END")
            self._label("Reason", event["raison"])
            self._label("Tool calls", event["appels"])
            self._block("Final response", event["reponse"])
        elif name == "calibration_verdict":
            self._section("Verdict")
            self._write("CALIBRATION ATTACK VERDICT")
            self._label("Case", event["cas"])
            self._label("Intended objective", event["objectif_prevu"])
            self._label("Intended objective reached", event["objectif_prevu_atteint"])
            self._label("Any prohibited effect", event["verdict"]["reussie"])
            self._label("Prohibited effects", ", ".join(event["verdict"]["objectifs_atteints"]) or "none")
        elif name == "tache_verdict":
            self._section("Verdict")
            self._write("LEGITIMATE TASK VERDICT")
            self._label("Case", event["cas"])
            self._label("Completed correctly", event["reussie"])
        elif name == "attaque_verdict":
            self._section("Verdict")
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
