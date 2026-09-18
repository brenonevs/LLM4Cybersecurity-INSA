"""Task history: compatible observations and structured exchanges."""
from copy import deepcopy


class Historique(list):
    # The list view preserves compatibility with the deterministic simulator.
    # The Ollama client uses echanges instead.
    def __init__(self):
        super().__init__()
        self.echanges = []

    def enregistrer(self, tool, args, resultat, autorise=True, motif=""):
        observation = (f"[{tool}] {resultat[:600]}" if autorise
                       else f"[{tool}] refused ({motif})")
        self.append(observation)
        self.echanges.append({
            "action": {"tool": tool, "args": deepcopy(args)},
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
            for cle in ("body", "content"):
                valeur = action["args"].get(cle)
                if isinstance(valeur, str) and len(valeur) > 600:
                    action["args"][cle] = valeur[:600] + " [text truncated]"
            tool_name = action.get("tool", "")
            messages.append({
                "role": "assistant",
                "content": json.dumps({"tool": tool_name, "args": action["args"]}, ensure_ascii=False),
            })
            resultat = echange["resultat"]
            messages.append({
                "role": "user",
                "content": "Tool result: " + json.dumps({
                    "tool": tool_name,
                    "status": "executed" if echange["autorise"] else "refused",
                    "reason": echange["motif"],
                    "result": resultat[:600],
                    "result_truncated": len(resultat) > 600,
                }, ensure_ascii=False),
            })
        return messages
