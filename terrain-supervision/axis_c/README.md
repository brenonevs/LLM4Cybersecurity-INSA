# Axe C — permissions par outil

**Étapes 1–2 terminées : contrat validé et fondements étudiés.** Le moteur d’autorisation
et l’attaquant restent à développer. Charger une politique n’active aucune défense.
Référence : énoncé du professeur, section Axe C (conservé dans la documentation locale).

## Spécification

Mesurer la réduction des actions interdites, le coût sur les tâches légitimes et
les contournements par composition d’appels individuellement autorisés.
La base collective est gelée ; le module utilise les points d’extension prévus.
L’attaquant ne modifie que les champs déclarés par `Corpus.injection_points()`.

La politique [policy.json](policy.json), version `axis-c-policy-v0.1`, décrit les
cinq outils. JSON permet une validation avec la bibliothèque standard Python.

| Outil | Origine minimale | Confiance minimale | Ressource autorisée |
|---|---|---|---|
| `read_log` | `externe` | aucune | lecture des journaux |
| `search_document` | `externe` | aucune | recherche documentaire |
| `send_email` | `utilisateur` | 0,7 | `entreprise.fr` et ses sous-domaines |
| `restart_equipment` | `interne` | 0,5 | équipement demandé |
| `write_file` | `interne` | 0,5 | descendants de `/var/supervision/` |

- Ordre : `externe < interne < utilisateur < systeme`. `null` désactive uniquement
  le seuil de confiance ; il ne signifie pas une confiance maximale.
- Les seuils de courriel et de redémarrage suivent l’exemple de l’énoncé.
  La règle d’écriture et les lectures sans seuil sont des choix initiaux à évaluer.
- Le contrat impose `default_effect=deny`. Le validateur rejette les champs
  inconnus, doublons, outils manquants, seuils invalides et ressources mal formées.
- La configuration chargée est immuable. Son SHA-256 identifie le contenu JSON
  canonique, indépendamment des espaces et de l’ordre des clés. Ce n’est pas une signature.

## Intégration prévue et limites

`PermisParOutil.verify()` devra retourner `None` ou un motif de refus explicite.
Le contrôle des destinataires et chemins demandés sera effectué par ce futur
moteur ; le validateur actuel contrôle seulement la configuration des règles.
L’autorisation vérifiera les domaines par frontière de label et les chemins par
composants normalisés. Le ticket ouvert reste un critère du juge partagé.

La base transmet une origine initiale constante et ne fournit aucun score de
confiance. Un adaptateur explicite devra définir ces attributs, sans accepter une
identité déclarée dans une charge. Un attribut requis absent entraînera un refus.
Empiler les protections ne partage pas automatiquement les attributs A/B/C.
La relecture des fichiers écrits n’existe pas dans cette base : les expériences
de composition porteront sur les séquences effectivement disponibles.

## Décisions issues des lectures

[FIDES](https://arxiv.org/abs/2505.23643v2) motive le contrôle déterministe
avant exécution ; [ChainCaps](https://arxiv.org/abs/2605.26542v4) distingue
les permissions locales de la sûreté des flux composés. Ces garanties ne sont
pas celles de notre validateur actuel.

Le prochain moteur séparera décision pure et adaptateur d’exécution. Origine et
confiance viendront de fournisseurs de confiance, jamais du texte injecté.
Sans fournisseur configuré, les attributs requis restent inconnus et les actions
concernées sont refusées. Le rôle constant `utilisateur` ne prouve pas l’origine
causale. Le fournisseur opérationnel devra être défini avant toute campagne.
Les seuils restent des choix initiaux ; aucune efficacité n’est encore mesurée.

## Plan complet

1. **Contrat exécutable** : spécification, politique, validation et critères de fin.
2. **Fondements** : vérifier et étudier FIDES/ChainCaps ; justifier les règles et les attributs.
3. **Autorisation** : implémenter le moteur déterministe et intégrer `PermisParOutil`.
4. **Tests de défense** : vérifier décisions, refus sans effet, seuils et isolation des tâches.
5. **Évaluation initiale** : comparer sécurité, utilité et coût avec/sans C ; distinguer 40 tâches de base et 8 extensions.
6. **Attaquant adaptatif** : génération LLM, mémoire SQLite, budgets et adaptation aux refus.
7. **Composition** : distinguer attaque directe, violation individuelle et composition conforme avec dépendance démontrée.
8. **Campagne individuelle** : figer C et l’attaquant ; 150 tentatives par configuration prévue, traces et métriques reproductibles.
9. **Intégration collective** : croisements avec A, B et leur combinaison ; interprétation commune.
10. **Livrables** : analyse des limites, rapport de 20–25 pages, soutenance de 20 minutes et code reproductible.

## Définition de fini et vérification

L’étape 1 est terminée quand tous les critères de la matrice d’acceptation
locale sont satisfaits : validité du contrat,
rejets explicites, immutabilité, reproductibilité, CLI utilisable et absence de
régression. Le nombre de tests ne constitue pas un critère suffisant.
Cette validation ne démontre pas encore l’efficacité d’une défense contre les attaques.

Depuis `terrain-supervision`, avec l’environnement virtuel du projet :

```bash
../venv/bin/python -B -m axis_c.policy
../venv/bin/python -B -m pytest tests/test_axis_c_policy.py tests/test_axis_c_acceptance.py -q
../venv/bin/python -B -m pytest tests/ -q
```

La CLI accepte aussi un chemin JSON explicite. Succès : code 0 et résumé JSON
avec version, SHA-256, outils et `configuration_validated_not_enforced`.
Échec de configuration : code 2, diagnostic sur stderr et aucun résumé de succès.

Seuls les README sont versionnés comme documentation Markdown. Les critères
détaillés, références et journaux de développement restent dans `.context/`,
un dossier local ignoré par Git.
