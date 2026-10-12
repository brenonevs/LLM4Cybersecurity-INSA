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
            return [f"{pad}(vide)"]
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
            return [f"{pad}(vide)"]
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
        prefix = "Résultat de l’outil"
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
        months = ("janvier", "février", "mars", "avril", "mai", "juin",
                  "juillet", "août", "septembre", "octobre", "novembre", "décembre")
        utc = moment.astimezone(timezone.utc)
        return f"{utc.day:02d} {months[utc.month - 1]} {utc.year}, {utc:%H:%M} UTC"
    except (TypeError, ValueError):
        return str(value)


def _execution_type(case):
    name = str(case or "")
    if name.startswith("calibration:") or name == "attaque":
        return "ATTAQUE"
    if name.startswith("T") and len(name) <= 4:
        return "TÂCHE LÉGITIME"
    if name.startswith("diagnostic") or name.startswith("demo:"):
        return "TEST"
    return "EXÉCUTION"


_SOURCE_KIND_LABELS = {
    "journal": "Entrée de journal",
    "ticket": "Ticket de maintenance",
    "fiche": "Document de procédure",
    "mail": "Courriel",
}

_SOURCE_FIELD_LABELS = {
    "horodatage": "Horodatage",
    "mesure": "Mesure",
    "commentaire": "Commentaire",
    "statut": "Statut",
    "description": "Description",
    "titre": "Titre",
    "contenu": "Contenu",
    "expediteur": "Adresse de l’expéditeur",
    "sujet": "Objet",
    "corps": "Corps du message",
}

_SOURCE_ORIGIN_LABELS = {
    "interne": "interne",
    "externe": "externe",
    "systeme": "système",
    "utilisateur": "utilisateur",
}

_SOURCE_CONTENT_TYPE_LABELS = {
    "timestamp": "horodatage",
    "measure": "mesure",
    "status": "statut",
    "email_address": "adresse e-mail",
    "text": "texte",
}


def _source_kind_label(kind):
    return _SOURCE_KIND_LABELS.get(str(kind), str(kind or "enregistrement inconnu"))


def _source_field_label(field):
    return _SOURCE_FIELD_LABELS.get(str(field), str(field or "champ inconnu"))


def _source_origin_label(origin):
    return _SOURCE_ORIGIN_LABELS.get(str(origin), str(origin or "inconnue"))


def _source_content_type_label(content_type):
    return _SOURCE_CONTENT_TYPE_LABELS.get(
        str(content_type), str(content_type or "non déclaré"))


def _oui_non(value):
    return "oui" if value else "non"


def _motif_lisible_en_francais(motif):
    """Translate Axis B authorization reasons for people reading the journal.

    The original reason is retained in the event structure and may still be
    supplied to the model as tool feedback. This function affects only the
    human-facing report and terminal summary.
    """
    text = str(motif or "")
    prefix = ""
    if text.startswith("[score-confiance] "):
        prefix = "[score-confiance] "
        text = text[len(prefix):]
    if text.startswith("Recent risk ") and " remains active;" in text:
        risk, _, source = text[len("Recent risk "):].partition(" remains active; ")
        source = source.removeprefix("sensitive tools stay blocked until it is cleared for ")
        return (f"{prefix}Le risque récent {risk} reste actif. Les outils sensibles "
                f"restent bloqués jusqu’à sa disparition pour {source}")
    if text.startswith("Effective trust ") and " is below the required " in text:
        trust, _, tail = text[len("Effective trust "):].partition(" is below the required ")
        threshold, _, source = tail.partition("; limiting source is ")
        return (f"{prefix}La confiance effective {trust} est inférieure au seuil requis "
                f"de {threshold}. La source limitante est {source}")
    if text.startswith("A cross-source combined risk remains active"):
        return (f"{prefix}Un risque combiné entre plusieurs sources reste actif "
                "pour cette tâche. Les outils sensibles restent bloqués.")
    return str(motif or "")


def _source_title(source):
    """Return a reader-facing identity for one source field or record."""
    kind = _source_kind_label(source.get("kind", source.get("record_kind")))
    record_id = source.get("record_id")
    if record_id is None:
        key = str(source.get("source_key", source.get("key", "")))
        parts = key.split(":", 2)
        if len(parts) == 3:
            record_id = parts[1]
            field = parts[2]
            source = {**source, "kind": parts[0], "field": field}
            kind = _source_kind_label(parts[0])
    field = source.get("field")
    label = f"{kind} #{record_id}" if record_id not in {None, ""} else kind
    return label if not field else f"{label} — {_source_field_label(field)}"


class Journal:
    """Écrit un rapport lisible en français, sans le renvoyer au modèle."""
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
        for line in str(text or "(vide)").splitlines() or ["(vide)"]:
            self._write(f"  {line}")

    def _indented(self, text):
        for line in str(text or "(vide)").splitlines() or ["(vide)"]:
            self._write(f"  {line}")

    def _messages(self, messages):
        labels = {
            "system": "INSTRUCTIONS SYSTÈME",
            "assistant": "RÉPONSE PRÉCÉDENTE DU MODÈLE",
        }
        self._subsection(f"ENTRÉE DU MODÈLE — {len(messages)} message(s)")
        for index, message in enumerate(messages, 1):
            content = str(message.get("content", ""))
            if message.get("role") == "user":
                if content.startswith("Technician request:"):
                    label = "TÂCHE ORIGINALE DU TECHNICIEN"
                elif content.startswith("Tool result:"):
                    label = "RÉSULTAT D’OUTIL FOURNI AU MODÈLE"
                elif content.startswith("Checklist of explicit request requirements:"):
                    label = "LISTE DES EXIGENCES DE LA TÂCHE"
                elif content.startswith("Current task state,"):
                    label = "ÉTAT ACTUEL DE LA TÂCHE"
                else:
                    label = "MESSAGE UTILISATEUR"
            else:
                label = labels.get(message.get("role"), f"MESSAGE ({message.get('role', '?')})")
            self._subsection(f"[{index}] {label}")
            self._indented(_pretty_content(content))

    def _sources(self, sources):
        self._subsection("Sources de données dans ce résultat d’outil")
        if not sources:
            self._write("  Aucune métadonnée de source n’a été renvoyée avec ce résultat.")
            return
        records = {}
        for source in sources:
            record_key = (
                source.get("kind", "?"),
                source.get("record_id", "?"),
                source.get("origin", "?"),
                source.get("actor", "?"),
            )
            records.setdefault(record_key, []).append(source)

        self._write(
            "  Cette section identifie les enregistrements du corpus qui ont fourni "
            "le résultat présenté au modèle. Chaque ligne ci-dessous correspond à un "
            "champ d’un enregistrement, et non à un nouvel auteur ou à un nouvel appel d’outil.")
        self._label("  Champs source", len(sources))
        self._label("  Enregistrements d’origine", len(records))
        self._write(
            "  Les identifiants techniques sont conservés uniquement pour la traçabilité. "
            "Par exemple, journal:1822:mesure désigne le champ Mesure de l’entrée de journal n°1822.")

        for (kind, record_id, origin, actor), fields in records.items():
            record_title = (
                f"{_source_kind_label(kind)} #{record_id}"
                if record_id not in {None, "", "?"} else _source_kind_label(kind))
            self._subsection(f"  {record_title}")
            self._label("    Auteur déclaré", actor)
            self._label("    Origine déclarée", _source_origin_label(origin))
            self._write("    Champs transmis au modèle :")
            for source in fields:
                field = _source_field_label(source.get("field"))
                data_type = _source_content_type_label(source.get("content_type"))
                self._write(f"      - {field} ({data_type})")
            identifiers = ", ".join(str(source.get("key", "?")) for source in fields)
            self._write(f"    Identifiant(s) technique(s) du champ : {identifiers}")

    def _axis_b_observations(self, observations):
        if not observations:
            return
        self._section("Calcul de confiance")
        self._write("ÉVALUATION DES ÉLÉMENTS DE PREUVE — AXE B")
        counts = {}
        for item in observations:
            update = item.get("trust_update", "none")
            counts[update] = counts.get(update, 0) + 1
        summary = ", ".join(
            f"{update} x{count}" if count > 1 else update
            for update, count in counts.items())
        self._label("Champs évalués", len(observations))
        self._label("Mises à jour dans ce résultat", summary or "aucune")
        for item in observations:
            self._subsection(_source_title(item))
            self._label("  Auteur déclaré", item.get("author_id", "?"))
            self._label("  Type d’enregistrement", _source_kind_label(item.get("record_kind")))
            self._label("  Format de données", _source_content_type_label(
                item.get("content_type", "non enregistré")))
            self._label("  Identifiant technique du champ", item.get("source_key", "?"))
            if "content" in item:
                self._subsection("  Contenu exact du champ évalué")
                self._indented(_pretty_content(str(item["content"])))
            self._subsection("  Évaluation")
            self._label("    Résultat", item.get("result", "?"))
            self._label("    Sévérité", item.get("severity", "?"))
            weight = item.get("weight", 0)
            self._label("    Poids", f"{weight:g}" if isinstance(weight, (int, float)) else weight)
            self._label("    Raisons", ", ".join(item.get("reasons") or []) or "aucune")
            lexical_checks = item.get("lexical_checks", [])
            if lexical_checks:
                self._subsection("  Analyse lexicale")
                self._write("    Le contenu exact ci-dessus a été normalisé pour la casse, Unicode et les espaces.")
                for check in lexical_checks:
                    status = "DÉTECTÉ" if check.get("matched") else "non détecté"
                    self._write(f"    - {check.get('name', '?')}: {status}")
            elif item.get("content_type") in {"timestamp", "measure", "status", "email_address"}:
                self._subsection("  Analyse lexicale")
                self._write("    Non exécutée : le type structuré déclaré a été validé en premier.")
            signals = item.get("signals", [])
            self._subsection("  Éléments de preuve")
            if signals:
                self._write("    Éléments pris en compte pour β après déduplication :")
                for signal in signals:
                    self._write("      - {kind}: weight={weight:g}; origin={origin}".format(
                        **signal))
            else:
                self._write("    Éléments pris en compte pour β après déduplication : aucun")
            semantic = item.get("semantic")
            if semantic:
                self._subsection("  Analyse sémantique et contextuelle")
                self._write(
                    "    observation sémantique ({protocol}) : catégorie={category}; "
                    "force={score:.2f}; candidat={candidate}".format(**semantic))
                self._write(
                    "    concepts détectés : " +
                    (", ".join(semantic["matched_concepts"]) or "aucun"))
                self._write("    raisons contextuelles : " +
                            (", ".join(semantic["reasons"]) or "aucune"))
                self._write(f"    référence la plus proche : {semantic['reference']}")
                self._write("    résultat sémantique : pris en compte uniquement par les éléments de preuve ci-dessus")
            syntactic = item.get("syntactic")
            if syntactic:
                self._subsection("  Analyse syntaxique")
                self._write(
                    "    analyseur ({protocol}) : disponible={available}; "
                    "candidat={candidate}".format(
                        **{**syntactic, "available": _oui_non(syntactic.get("available")),
                           "candidate": _oui_non(syntactic.get("candidate"))}))
                if syntactic.get("available"):
                    self._write(
                        "    verbe d’action={action_verb}; impératif={imperative}; "
                        "négation={negated}; voix passive={passive}".format(
                            **{**syntactic, "imperative": _oui_non(syntactic.get("imperative")),
                               "negated": _oui_non(syntactic.get("negated")),
                               "passive": _oui_non(syntactic.get("passive"))}))
                    self._write(
                        "    objet={object}; cible={target}; type de cible={target_kind}".format(
                            **syntactic))
                self._write("    raisons syntaxiques : " +
                            (", ".join(syntactic.get("reasons", [])) or "aucune"))
            embedding = item.get("embedding")
            if embedding:
                self._subsection("  Embedding")
                self._write(
                    "    observation d’embedding ({protocol}) : catégorie={category}; "
                    "attaque={attack_similarity:.3f}; légitime={legitimate_similarity:.3f}; "
                    "marge={margin:.3f}; qualifié={qualified}; soutien={support_weight:g}".format(
                        **{**embedding, "qualified": _oui_non(embedding.get("qualified"))}))
                if embedding["support_weight"]:
                    self._write("    résultat de l’embedding : pris en compte uniquement par les éléments de preuve ci-dessus")
                else:
                    self._write("    résultat de l’embedding : enregistré sans modification de β")
            self._subsection("  Calcul de confiance")
            self._write(
                "    Alpha : {alpha_before} -> {alpha_after}".format(**item))
            self._write(
                "    Bêta : {beta_before} -> {beta_after}".format(**item))
            self._write(f"    Mise à jour appliquée : {item['trust_update']}")
            if item.get("recent_risk_update") not in {None, "disabled"}:
                self._write(
                    "    Risque récent : {recent_risk_before:.2f} -> "
                    "{recent_risk_after:.2f} ({recent_risk_update})".format(**item))
            if item.get("version"):
                self._write(f"    Version du contenu (SHA-256) : {item['version']}")

    def _combined_risks(self, risks):
        if not risks:
            return
        self._section("Corrélation de risque entre champs")
        self._write("RISQUE COMBINÉ — AXE B")
        for risk in risks:
            self._subsection(risk.get("category", "risque combiné"))
            self._label("  Portée", risk.get("scope", "?"))
            self._label("  Activé", _oui_non(risk.get("activated", False)))
            self._label("  Composants", ", ".join(risk.get("components", [])) or "aucun")
            self._write("  Champs concernés :")
            for key in risk.get("source_keys", []):
                self._write(f"    - {key}")
            self._write("  Catégories de sources :")
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
        line = f"{self.progresso_fase or self.tipo or 'EXÉCUTION'} {self.progresso_indice}/{self.progresso_total}"
        if self.campanha_indice is not None and self.campanha_total is not None:
            line += f" | campagne {self.campanha_indice}/{self.campanha_total}"
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
            self._heading("DÉBUT DE LA CAMPAGNE")
            labels = {
                "date_utc": "Date et heure (UTC)",
                "commande": "Commande",
                "modele": "Fournisseur de modèle",
                "ollama_modele": "Modèle Ollama",
                "protections": "Protections",
                "corpus_version": "Version du corpus",
                "graine": "Graine du corpus",
                "official_calibration_version": "Version de la calibration officielle",
                "historique_version": "Version de l’historique",
                "limite_resultat_modele": "Limite par résultat de modèle",
                "budget_resultats_modele": "Budget de résultats du modèle",
                "systeme_version": "Version des instructions système",
                "trust_authorization": "Autorisation par confiance",
                "trust_decay_factor": "Facteur de décroissance de confiance",
                "trust_recent_risk": "Mémoire de risque récent",
                "trust_recent_risk_recovery": "Réduction du risque récent",
            }
            for key, label in labels.items():
                if key in event:
                    self._label(label, _human_date(event[key]) if key == "date_utc" else event[key])
        elif name == "execution_debut":
            self._heading(f"{self.tipo}: {event['cas']}")
            self._label("Identifiant d’exécution", event["execution"])
            if self._progress_line():
                self._label("Progression", self._progress_line())
            self._block("Tâche du technicien", event["tache"])
            self._label("Nombre maximal d’étapes", event["max_etapes"])
        elif name == "etape_debut":
            self._step_heading(f"ÉTAPE {event['etape']}/{self.max_etapes}")
        elif name == "modele_requete":
            self._section("Appel au modèle")
            self._write("REQUÊTE AU MODÈLE")
            self._label("Point d’accès", event["url"])
            request = event["charge"]
            self._label("Modèle", request.get("model", "?"))
            options = request.get("options", {})
            if options:
                self._label("Options", ", ".join(f"{key}={value}" for key, value in options.items()))
            self._label("Sortie structurée", "activée" if request.get("format") else "désactivée")
            self._messages(request.get("messages", []))
        elif name == "modele_reponse":
            self._section("Réponse du modèle")
            self._write("SORTIE DU MODÈLE (RÉPONSE BRUTE)")
            response = event["reponse"]
            content = response.get("message", {}).get("content", "")
            self._subsection("Réponse exacte renvoyée par le modèle")
            self._indented(_pretty_content(content))
            metadata = [f"{key}={response[key]}" for key in
                        ("done_reason", "prompt_eval_count", "eval_count", "total_duration")
                        if key in response]
            if metadata:
                self._label("Métadonnées de la réponse", ", ".join(metadata))
        elif name == "decision":
            self._section("Décision")
            self._write("DÉCISION DU MODÈLE")
            action = event["action"]
            if "fin" in action:
                self._block("Réponse finale", action["fin"])
            else:
                self._label("Outil", action.get("outil", "?"))
                for key, value in (action.get("args") or {}).items():
                    self._block(f"Argument {key}", value)
        elif name == "outil_decision":
            self._section("Autorisation de l’outil")
            self._write("AUTORISATION DE L’OUTIL")
            self._label("Outil", event["outil"])
            self._label("Statut", "AUTORISÉ" if event["autorise"] else "REFUSÉ")
            trust = event.get("trust_authorization")
            if trust:
                self._label("Confiance requise", f"{trust['threshold']:.2f}")
                self._label("Barrière des preuves négatives",
                            "ACTIVE" if trust["negative_evidence_gate"] else "NON DÉCLENCHÉE")
                if trust.get("recent_risk_enabled"):
                    self._label("Mémoire de risque récent",
                                "ACTIVE" if trust.get("recent_risk_gate") else "AUCUN RISQUE ACTIF")
                effective = trust["effective_trust"]
                self._label("Confiance effective",
                            "non appliquée" if effective is None else f"{effective:.2f}")
                self._write("Sources prises en compte :")
                for source in trust["sources"]:
                    self._write(
                        f"  - {source['author']} / "
                        f"{_source_kind_label(source['category'])} : {source['trust']:.2f}")
                if trust.get("recent_risk_sources"):
                    self._write("Sources avec risque récent :")
                    for source in trust["recent_risk_sources"]:
                        self._write(
                            f"  - {source['author']} / "
                            f"{_source_kind_label(source['category'])} : "
                            f"risque={source['risk']:.2f}, "
                            f"confiance actuelle={source['trust']:.2f}")
                if trust.get("combined_risk_gate"):
                    self._label("Risque combiné de la tâche", "ACTIF")
                if trust.get("combined_risks"):
                    self._write("Corrélations combinées prises en compte :")
                    for risk in trust["combined_risks"]:
                        self._write("  - {category}: scope={scope}; active={activated}".format(
                            **risk))
            if event.get("motif"):
                self._block("Motif", _motif_lisible_en_francais(event["motif"]))
        elif name == "outil_resultat":
            self._section("Résultat de l’outil")
            self._write("RÉSULTAT DE L’OUTIL")
            self._label("Outil", event["outil"])
            self._label("Origine agrégée", _source_origin_label(event.get("origine", "?")))
            self._label("Source agrégée", event.get("source", "?"))
            self._block("Résultat complet", event.get("texte_complet", ""))
            self._sources(event.get("sources", []))
            self._axis_b_observations(event.get("axis_b_observations", []))
            self._combined_risks(event.get("axis_b_combined_risks", []))
        elif name == "axis_b_episode_step":
            self._write("ÉTAPE D’ÉPISODE CONTINU — AXE B")
            self._label("Étape", event["label"])
            self._axis_b_observations([event["observation"]])
        elif name == "classification_case":
            self._write(f"CAS DE CLASSIFICATION : {event['case_id']}")
            self._label("Classe attendue", event["expected"])
            self._label("Résultat", event["outcome"])
            if event.get("injected_content"):
                self._block("Contenu injecté", event["injected_content"])
            if event.get("task"):
                self._block("Tâche légitime", event["task"])
            observations = event.get("semantic_observations", [])
            self._subsection("Comparaison sémantique (observation uniquement)")
            if not observations:
                self._write("  (aucun élément textuel n’a été lu)")
            for observation in observations:
                self._subsection(_source_title(observation))
                self._write(
                    "  évaluation={assessment_result}".format(**observation))
                self._write(
                    "  sémantique={semantic_category} ({semantic_score:.2f}); "
                    "candidat={semantic_candidate}".format(**observation))
                self._write("  raisons de l’évaluation : " +
                            (", ".join(observation["assessment_reasons"]) or "aucune"))
                self._write("  Éléments de preuve")
                signals = observation["beta_signals"]
                if signals:
                    self._write("    éléments pris en compte pour β après déduplication :")
                    for signal in signals:
                        self._write("      - {kind}: weight={weight:g}; origin={origin}".format(
                            **signal))
                else:
                    self._write("    éléments pris en compte pour β après déduplication : aucun")
                self._write("  Analyse sémantique")
                self._write("    concepts : " +
                            (", ".join(observation["matched_concepts"]) or "aucun"))
                self._write("    raisons contextuelles : " +
                            (", ".join(observation["semantic_reasons"]) or "aucune"))
                syntactic = observation.get("syntactic")
                if syntactic:
                    self._write("  Analyse syntaxique")
                    self._write(
                        "    disponible={available}; candidat={candidate}; "
                        "verbe={action_verb}; impératif={imperative}; "
                        "négation={negated}; voix passive={passive}; cible={target}".format(
                            **{**syntactic, "available": _oui_non(syntactic.get("available")),
                               "candidate": _oui_non(syntactic.get("candidate")),
                               "imperative": _oui_non(syntactic.get("imperative")),
                               "negated": _oui_non(syntactic.get("negated")),
                               "passive": _oui_non(syntactic.get("passive"))}))
                embedding = observation.get("embedding")
                if embedding:
                    self._write("  Embedding")
                    self._write(
                        "    observation d’embedding ({protocol}) : catégorie={category}; "
                        "attaque={attack_similarity:.3f}; légitime={legitimate_similarity:.3f}; "
                        "marge={margin:.3f}; qualifié={qualified}; soutien={support_weight:g}".format(
                            **{**embedding, "qualified": _oui_non(embedding.get("qualified"))}))
                self._block("  Texte évalué", observation["content"])
        elif name == "classification_summary":
            self._heading("RÉSUMÉ DE LA CLASSIFICATION — AXE B")
            self._label("Vrais positifs", event["true_positive"])
            self._label("Faux positifs", event["false_positive"])
            self._label("Vrais négatifs", event["true_negative"])
            self._label("Faux négatifs", event["false_negative"])
            self._label("Rappel", f"{event['recall']:.2%}")
            self._label("Précision", f"{event['precision']:.2%}")
            self._label("Taux de faux positifs", f"{event['false_positive_rate']:.2%}")
            self._label("Taux de faux négatifs", f"{event['false_negative_rate']:.2%}")
            self._label("Protocole sémantique", event.get("semantic_protocol", "non enregistré"))
            self._label("Faux négatifs avec candidat sémantique",
                        event.get("false_negative_semantic_candidates", "non enregistré"))
            self._label("Candidats sémantiques légitimes",
                        event.get("legitimate_semantic_candidates", "non enregistré"))
        elif name == "trust_lifecycle_summary":
            self._heading("RÉSUMÉ DU CYCLE DE CONFIANCE — AXE B")
            self._label("Observations légitimes initiales", event["warmup_count"])
            self._label("Observations de récupération mesurées", event["recovery_observations"])
            self._label("Facteur de décroissance", event["decay_factor"])
            self._label("Réduction du risque récent", event["recent_risk_recovery"])
            self._label("Soutien par embedding", _oui_non(event["embedding_support"]))
            classification = event["classification"]
            self._subsection("Métriques de détection")
            self._write("  VP={true_positive}; FP={false_positive}; VN={true_negative}; "
                        "FN={false_negative}; précision={precision:.2%}; rappel={recall:.2%}".format(
                            **classification))
            execution = event["execution"]
            self._subsection("Métriques d’exécution officielle")
            self._write("  Attaques empêchées : {attacks_prevented}/{attacks_total}".format(**execution))
            self._write("  Tâches légitimes terminées : {legitimate_completed}/"
                        "{legitimate_total}".format(**execution))
            self._subsection("Métriques du cycle de l’attaquant patient")
            for record in event["lifecycle"]:
                self._write(
                    "  - {payload} : sévérité={severity}; détecté={detected}; "
                    "risque_activé={risk_activated}; bloqué_initialement={initially_blocked}; "
                    "risque_effacé_après={risk_clear_after}; outils_autorisés_après="
                    "{tools_release_after}".format(**record))
            self._subsection("Métriques de corrélation d’attaque répartie")
            for record in event.get("cross_field", []):
                self._write(
                    "  - {case} : bloqué_dans_la_tâche={blocked_in_task}; "
                    "risque_combiné_effacé_après_tâche={combined_risk_cleared_after_task}; "
                    "risque_de_source_bloque_tâche_suivante={source_risk_blocks_next_task}; "
                    "bêta={beta_by_source}; "
                    "risque_récent={recent_risk_by_source}".format(**record))
        elif name == "recidivism_summary":
            self._heading("EXPÉRIENCE DE RÉCIDIVE — AXE B")
            self._label("Observations légitimes initiales", event["warmup_count"])
            self._label("Réduction du risque récent", event["recent_risk_recovery"])
            self._write("Escalade du risque : premier incident=1,0; incidents suivants=+0,5; plafond=3,0")
            for scenario in event["scenarios"]:
                self._subsection(
                    f"{scenario['scenario']} / {scenario['payload']} — "
                    f"attaques={scenario['occurrences']}; "
                    f"récupération entre deux attaques={scenario['recovery_between']}")
                self._write("  attaque | sévérité | alpha | bêta | confiance | "
                            "risque avant -> après | e-mail")
                for row in scenario["rows"]:
                    self._write(
                        "  {occurrence:6d} | {severity:8s} | {alpha:5.1f} | "
                        "{beta:4.1f} | {trust:.3f} | {risk_before:.2f} -> "
                        "{risk_after:.2f} ({risk_update}) | {email}".format(
                            **row, email="AUTORISÉ" if row["email_allowed"] else "BLOQUÉ"))
        elif name == "execution_fin":
            self._section("Résultat de l’exécution")
            self._write("FIN DE L’EXÉCUTION")
            self._label("Motif", event["raison"])
            self._label("Appels d’outils", event["appels"])
            self._block("Réponse finale", event["reponse"])
        elif name == "calibration_verdict":
            self._section("Verdict")
            self._write("VERDICT DE L’ATTAQUE DE CALIBRATION")
            self._label("Cas", event["cas"])
            self._label("Objectif prévu", event["objectif_prevu"])
            self._label("Objectif prévu atteint", _oui_non(event["objectif_prevu_atteint"]))
            self._label("Effet interdit constaté", _oui_non(event["verdict"]["reussie"]))
            self._label("Effets interdits", ", ".join(event["verdict"]["objectifs_atteints"]) or "aucun")
        elif name == "tache_verdict":
            self._section("Verdict")
            self._write("VERDICT DE LA TÂCHE LÉGITIME")
            self._label("Cas", event["cas"])
            self._label("Terminée correctement", _oui_non(event["reussie"]))
        elif name == "attaque_verdict":
            self._section("Verdict")
            self._write("VERDICT DE L’ATTAQUE")
            self._label("Cas", event["cas"])
            self._label("Effet interdit constaté", _oui_non(event["verdict"]["reussie"]))
            self._label("Effets interdits", ", ".join(event["verdict"]["objectifs_atteints"]) or "aucun")
        elif name in ("modele_erreur", "execution_erreur"):
            self._write("ERREUR")
            self._label("Type", event["type"])
            self._block("Message", event["message"])
        elif name == "campagne_fin":
            self._heading("FIN DE LA CAMPAGNE")
            self._label("Motif", event["raison"])
        else:
            self._write(f"ÉVÉNEMENT : {name}")

    def commencer(self, cas, tache, max_etapes):
        self.execution = uuid4().hex
        self.derniere_execution = self.execution
        self.etape, self.max_etapes = None, max_etapes
        self.cas, self.tipo = cas, _execution_type(cas)
        self.noter("execution_debut", cas=cas, tache=tache, max_etapes=max_etapes)
        progress = self._progress_line()
        print(f"[journal] -------- {self.tipo} | début{f' | {progress}' if progress else ''} --------")
        print(f"[journal] cas={cas} | exécution={self.execution[:8]}")
        print(f"[journal]   tâche : {_shorten(tache, 140)}")

    def annoncer_etape(self, number):
        progress = self._progress_line()
        print(f"[journal] [{self.tipo or 'EXÉCUTION'}] étape {number}/{self.max_etapes or '?'}"
              f"{f' | {progress}' if progress else ''}")

    def annoncer_decision(self, action):
        if "fin" in action:
            print("[journal]   décision : fin")
            return
        tool = str(action.get("outil", "")).strip() or "?"
        args = _readable_args(action.get("args") or {})
        print(f"[journal]   décision : {tool}({args})" if args else f"[journal]   décision : {tool}()")

    def annoncer_outil(self, tool, args, allowed, reason=""):
        print(f"[journal]   outil : {tool} | {'AUTORISÉ' if allowed else 'REFUSÉ'}"
              f"{f' | {_shorten(_motif_lisible_en_francais(reason), 80)}' if reason else ''}")

    def annoncer_resultat(self, tool, text):
        print(f"[journal]   résultat : {_shorten(text, 120)}")

    def terminer(self, reason, calls, response):
        self.noter("execution_fin", raison=reason, appels=calls, reponse=response)
        progress = self._progress_line()
        print(f"[journal] -------- {self.tipo or 'EXÉCUTION'} | fin"
              f"{f' | {progress}' if progress else ''} --------")
        print(f"[journal] cas={self.cas} | motif={reason} | appels d’outils={calls}")
        if response:
            print(f"[journal]   réponse : {_shorten(response, 140)}")
        self.execution = self.etape = self.max_etapes = None
        self.cas = self.tipo = None

    def fermer(self):
        self.fichier.close()
