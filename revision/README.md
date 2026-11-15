# Mes révisions

Application locale d'aide à la révision pour une élève de tronc commun (Maroc). Elle importe une leçon, l'application prépare tout le reste et la guide étape par étape jusqu'à ce que la leçon soit maîtrisée.

Tout tourne sur le PC : un seul programme, une base SQLite, l'interface dans le navigateur. Seuls les appels à l'IA passent par internet.

## Installer sur Windows

1. Copie le dossier `revision` sur le PC (par exemple dans `Documents`).
2. Double-clique sur `installer.bat`. Il installe Python si besoin, puis les composants.
3. Le fichier `.env` s'ouvre dans le Bloc-notes : colle la clé Gemini après `GEMINI_API_KEY=`, enregistre, ferme.
4. Double-clique sur le raccourci **Mes révisions** créé sur le bureau. Le navigateur s'ouvre sur `http://127.0.0.1:8765`.

Une fenêtre noire reste ouverte (réduite) pendant l'utilisation : la fermer arrête l'application.

## Clés d'IA

Les clés se règlent uniquement dans le fichier `.env` (jamais dans le code).

| Variable | Rôle |
| --- | --- |
| `GEMINI_API_KEY` | Clé Gemini, gratuite sur https://aistudio.google.com/apikey. Sert aussi à lire les photos du cahier. |
| `GROQ_API_KEY` | Facultative, sur https://console.groq.com/keys. Sert de secours si Gemini est saturé. |
| `LLM_PROVIDER` | `auto` (Gemini puis Groq), `gemini`, `groq`, ou `mock` pour essayer sans clé avec des contenus factices. |
| `GEMINI_MODEL`, `GROQ_MODEL` | Nom du modèle. Si le modèle indiqué n'existe plus, l'application en choisit un autre toute seule. |

Après une modification de `.env`, ferme la fenêtre noire et relance l'application.

## Ce que fait la version 1

- Premier lancement : matières, langue de chaque matière (français, arabe, anglais), dates des contrôles.
- Import d'une leçon de Maths ou de Physique-Chimie : photos du cahier, PDF ou texte collé.
- Génération automatique en arrière-plan dès l'import : explication, mini-test, résumé, quiz, exercices des trois niveaux.
- Parcours verrouillé : Comprendre, Mini-test, Résumé, Quiz complet, Exercices niveau 1, 2 puis 3. Chaque étape débloque la suivante.
- Écran d'accueil « Ta prochaine étape ».
- Chat sur la leçon, qui commence toujours par une question.
- Bouton « Signaler une erreur » et rappel : en cas de désaccord, c'est le professeur qui a raison.

Les étapes « Feuille blanche » et « Explique-moi », les autres matières, les vidéos, les indices, le planning et le carnet d'erreurs arrivent dans les versions 2 et 3.

## Données

Tout est dans le dossier `data` : la base `revision.db` et les fichiers importés. Pour sauvegarder, copie ce dossier. Pour repartir de zéro, supprime-le.

## En cas de problème

| Message | Que faire |
| --- | --- |
| « Aucune clé d'IA n'est configurée » | Remplir `.env`, puis relancer. |
| « La clé d'IA est refusée » | Vérifier la clé dans `.env` (pas d'espace, pas de guillemets), puis relancer. |
| « Pas de connexion internet » ou « L'IA est très sollicitée » | Rien : l'application réessaie toute seule et la progression est conservée. |
| Photo mal lue | Sur la page de la leçon, « Voir le texte de la leçon » permet de corriger le texte. |
| « L'application ne répond plus » | Relancer avec le raccourci du bureau. |

## Pour développer

```bash
# Backend (Python 3.10 ou plus)
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend && ../.venv/bin/python -m pytest          # tests, avec IA simulée, sans réseau
../.venv/bin/python -m app.launcher                  # lance l'application

# Interface (Node 20 ou plus) : seulement pour la modifier
cd frontend && npm install && npm run build          # régénère frontend/dist, servi par FastAPI

# Parcours complet dans un navigateur (Playwright), sur une base vide et avec LLM_PROVIDER=mock
node e2e/parcours.mjs http://127.0.0.1:8765
```

Le dossier `frontend/dist` est versionné exprès : le PC de l'élève n'a besoin que de Python.

Organisation du code :

- `backend/app/services/llm` : fournisseurs Gemini, Groq et IA simulée, derrière une interface commune.
- `backend/app/services/generation` : file de tâches, consignes données à l'IA, validation des réponses.
- `backend/app/services/parcours.py` : étapes verrouillées, décidées côté serveur.
- `backend/app/routers` : API. `frontend/src` : interface React.
