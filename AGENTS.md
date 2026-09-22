# LLM4Cybersecurity-INSA

## Project purpose

`terrain-supervision` is a controlled industrial-supervision environment for
studying prompt injection against an LLM agent and evaluating protections. It
has no real network, mail server, filesystem, or equipment: tools update an
in-memory `Etat`, and `terrain/juge.py` evaluates the final effects.

The three project axes are independent:

- Axis A: data provenance;
- Axis B: source confidence and authorization decisions;
- Axis C: tool permissions.

Do not implement an Axis B defense in prompts. The defense belongs in Python
and is evaluated with `--protections aucune` as the vulnerable baseline.

## Repository layout

- `terrain-supervision/run.py`: command-line entry point and campaigns.
- `terrain-supervision/terrain/agent.py`: agent loop and the only point where
  protections authorize or refuse a tool call.
- `terrain-supervision/terrain/modele.py`: Ollama client, prompt, JSON action
  parsing, and the local simulator.
- `terrain-supervision/terrain/outils.py`: in-memory tool effects and
  `SourceReference` metadata.
- `terrain-supervision/terrain/protections.py`: protection interface and Axis
  B placeholder (`ScoreConfiance`).
- `terrain-supervision/terrain/scenarios.py`: fixed official attacks and
  legitimate tasks.
- `terrain-supervision/terrain/journal.py`: human-readable execution reports.
- `terrain-supervision/tests/`: deterministic pytest coverage.

## Tool contract

Keep these tool names and argument keys exact throughout prompts, models,
scenarios, protections, tests, and logs:

```text
read_log(equipement)
search_document(requete)
restart_equipment(equipement)
send_email(destinataire, sujet, corps)
write_file(chemin, contenu)
fin(reponse)
```

Never reintroduce the older French tool names. New text that is sent to an LLM
or written to human-facing reports must be in English.

## Axis B source tracking

Preserve `SourceReference` and `Fragment.sources` in `terrain/outils.py`.
Each corpus field returned by a read tool must retain a stable key, record kind,
record ID, field, origin, and declared actor. Pass these sources through the
agent to `Journal`; they are evidence for Axis B, not a protection decision.

Do not infer a source from text inside a document. A document's metadata is the
source identity. Injection data must not be able to change that identity.

## Execution and experiment rules

- The agent may call one tool per step, up to `max_etapes` (normally 8).
- Keep the loop breaker in `agent.py`: block repeated calls to the same target
  and terminate after two consecutive refusals.
- A protection returns `None` to allow a call or a non-empty reason to refuse.
- Keep `juge.py` deterministic; do not use an LLM to determine attack success.
- Inject only into points declared by `corpus.points_injection()`.
- Do not change the corpus or official scenarios during a measured campaign.
  If either changes, update its version and rerun the baseline.
- Do not add prompt rules that selectively prevent attack destinations or other
  prohibited effects during the baseline; that would bias the measurement.

## Logs

`--journal name.jsonl` deliberately creates `logs/name.log`. Reports must show
the campaign, human-readable date, task, model input, raw model output,
decision, tool authorization, full tool result, visible sources, and verdict.
Keep `Journal.evenements` for tests; `lire_evenements()` is only for legacy
JSON/JSONL files.

## Commands

From the repository root, run tests with:

```bash
venv/bin/python -B -m pytest terrain-supervision/tests -q -p no:cacheprovider
```

From `terrain-supervision`, run the official baseline with:

```bash
../venv/bin/python -B run.py calibrer-officiel \
  --modele ollama \
  --ollama-modele llama3.1:8b \
  --protections aucune \
  --debug \
  --journal calibration.log
```

Run tests after every code change. Do not treat simulator results as the final
measurement; use Ollama for the reported calibration.

## Git workflow

`main` is the shared integration branch. `axis-b` contains Axis B work and
must retain source tracking when integrating shared improvements. Port shared
changes selectively when they overlap `agent.py`, `journal.py`, or `outils.py`;
do not overwrite `SourceReference` or `Fragment.sources`. Resolve conflicts by
keeping the current English tool contract, loop breaker, readable reports, and
source metadata together.
