"""Historique par tache : observations compatibles et echanges structures."""
from copy import deepcopy


class Historique(list):
    # The list view preserves compatibility with the deterministic simulator.
    # The Ollama client uses echanges instead.
    def __init__(self):
        super().__init__()
        self.echanges = []

    def enregistrer(self, outil, args, resultat, autorise=True, motif=""):
        observation = (f"[{outil}] {resultat[:600]}" if autorise
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
        # Keep every action of this task, including refused actions.
        # Long bodies are shortened only in the model-facing representation.
        for echange in self.echanges:
            action = deepcopy(echange["action"])
            for cle in ("corps", "contenu"):
                valeur = action["args"].get(cle)
                if isinstance(valeur, str) and len(valeur) > 600:
                    action["args"][cle] = valeur[:600] + " [texte tronque]"
            messages.append({
                "role": "assistant",
                "content": json.dumps(action, ensure_ascii=False),
            })
            resultat = echange["resultat"]
            messages.append({
                "role": "user",
                "content": "Resultat de l'outil : " + json.dumps({
                    "outil": action["outil"],
                    "statut": "execute" if echange["autorise"] else "refuse",
                    "motif": echange["motif"],
                    "resultat": resultat[:600],
                    "resultat_tronque": len(resultat) > 600,
                }, ensure_ascii=False),
            })
        return messages
