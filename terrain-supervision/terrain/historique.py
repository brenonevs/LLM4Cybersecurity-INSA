"""Historique par tache : observations compatibles et echanges structures."""
from copy import deepcopy


# Limites explicites de la representation envoyee au modele. Le journal conserve
# toujours le resultat complet; seul le contexte du LLM est limite.
LIMITE_RESULTAT_MODELE = 1200
BUDGET_RESULTATS_MODELE = 4800
LIMITE_OBSERVATION_COMPATIBILITE = 600


class Historique(list):
    # The list view preserves compatibility with the deterministic simulator.
    # The Ollama client uses echanges instead.
    def __init__(self, limite_resultat_modele=LIMITE_RESULTAT_MODELE,
                 budget_resultats_modele=BUDGET_RESULTATS_MODELE):
        super().__init__()
        self.echanges = []
        self.limite_resultat_modele = limite_resultat_modele
        self.budget_resultats_modele = budget_resultats_modele

    def record(self, outil, args, resultat, autorise=True, motif=""):
        observation = (f"[{outil}] {resultat[:LIMITE_OBSERVATION_COMPATIBILITE]}" if autorise
                       else f"[{outil}] refuse ({motif})")
        self.append(observation)
        self.echanges.append({
            "action": {"outil": outil, "args": deepcopy(args)},
            "autorise": autorise,
            "motif": motif,
            "resultat": resultat,
        })

    def messages(self):
        import json
        messages = []
        quota_resultat = min(
            self.limite_resultat_modele,
            self.budget_resultats_modele // max(1, len(self.echanges)),
        )
        # Keep every action of this task, including refused actions.
        # Long bodies are shortened only in the model-facing representation.
        for echange in self.echanges:
            action = deepcopy(echange["action"])
            for cle in ("corps", "contenu"):
                valeur = action["args"].get(cle)
                if isinstance(valeur, str) and len(valeur) > self.limite_resultat_modele:
                    action["args"][cle] = valeur[:self.limite_resultat_modele] + " [texte tronque]"
            messages.append({
                "role": "assistant",
                "content": json.dumps(action, ensure_ascii=False),
            })
            resultat = echange["resultat"]
            messages.append({
                "role": "user",
                "content": "Tool result: " + json.dumps({
                    "outil": action["outil"],
                    "statut": "execute" if echange["autorise"] else "refuse",
                    "motif": echange["motif"],
                    "resultat": resultat[:quota_resultat],
                    "resultat_tronque": len(resultat) > quota_resultat,
                    "limite_resultat_modele": quota_resultat,
                }, ensure_ascii=False),
            })
        return messages
