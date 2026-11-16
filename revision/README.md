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
| `YOUTUBE_API_KEY` | Facultative. Clé YouTube Data API v3 pour la sélection de vidéos. |
| `GEMINI_API_KEY` | Clé Gemini, gratuite sur https://aistudio.google.com/apikey. Sert aussi à lire les photos du cahier. |
| `GROQ_API_KEY` | Facultative, sur https://console.groq.com/keys. Sert de secours si Gemini est saturé. |
| `LLM_PROVIDER` | `auto` (Gemini puis Groq), `gemini`, `groq`, ou `mock` pour essayer sans clé avec des contenus factices. |
| `GEMINI_MODEL`, `GROQ_MODEL` | Nom du modèle. Si le modèle indiqué n'existe plus, l'application en choisit un autre toute seule. |

Après une modification de `.env`, ferme la fenêtre noire et relance l'application.

## Ce que fait l'application (version 3 — complète)

**Préparation automatique.** Elle importe une leçon (photos du cahier, PDF ou texte collé) dans n'importe quelle matière. Dès l'import, et sans aucun bouton « générer », l'application prépare tout en arrière-plan : explication progressive, carte mentale, sélection de 3 vidéos YouTube, mini-test, résumé, quiz, exercices des trois niveaux et fiche « méthodes types ».

**Parcours guidé à étapes verrouillées.** Chaque étape se débloque quand la précédente est validée :
1. **Comprendre** — explication pas à pas (exemples, vidéos, carte mentale) ; un chat qui commence toujours par une question.
2. **Mini-test** — en cas d'échec, les points ratés sont réexpliqués autrement, puis un nouveau test.
3. **Feuille blanche** — elle écrit de mémoire ; l'application compare avec la leçon et signale oublis et erreurs.
4. **Résumé** — fiche de référence exportable en PDF ; ses définitions deviennent des cartes mémoire.
5. **Quiz complet** — majorité de questions ouvertes, seuil 80 % (réglable).
6. **Explique-moi** — elle explique avec ses mots, l'IA joue un élève qui pose des questions, puis évalue la clarté.
7. **Exercices** niveau 1 → 2 → 3, chacun débloqué par le précédent.
8. **Leçon maîtrisée**, puis rappels en répétition espacée.

**Exercices selon la matière.** Maths/PC/SVT : indices à 3 niveaux puis correction détaillée, fiche « méthodes types », et en SVT analyse de documents et schémas à légender. Langues : grammaire, vocabulaire en flashcards, compréhension de texte, production écrite corrigée par critères sans réécriture. Philosophie : fiches notions et auteurs, plan, rédaction argumentée.

**Révision et suivi.** Planning « à revoir aujourd'hui » (répétition espacée, séances qui mélangent les matières), carnet d'erreurs (chaque erreur reposée plus tard sous une autre forme), **contrôle blanc** chronométré au format d'un devoir surveillé noté sur 20 avec bilan des points à retravailler, import d'anciens devoirs (types de questions récurrents, style du professeur réutilisé), score de maîtrise par chapitre (rouge/orange/vert).

**Interface.** Écran d'accueil « Ta prochaine étape » (la révision du jour d'abord), carte de progression par leçon, série de jours, minuteur de séance (25 min + pause), récompenses légères sans classement, formules en LaTeX, mode sombre, arabe de droite à gauche. **Mode parent/frère protégé par un code** : progression détaillée, résultats des contrôles blancs, erreurs signalées, et réglage des seuils de réussite. Bouton « Signaler une erreur » partout, avec le rappel : en cas de désaccord, c'est le professeur qui a raison.

## Vidéos YouTube

Ajoute `YOUTUBE_API_KEY` dans `.env` (clé gratuite, voir les indications dans `.env.example`). Le quota gratuit est de 10 000 unités par jour ; une leçon en consomme environ 200.

Les sous-titres ne sont pas accessibles par l'API officielle pour les vidéos d'autrui. L'application tente de les lire par une bibliothèque non officielle ; si cela échoue, elle classe les vidéos sur le titre, la description, la durée et la chaîne.

## Mettre à jour depuis une version précédente

Extrais la nouvelle archive par-dessus l'ancien dossier, en gardant `data` et `.env`, puis relance `installer.bat` une fois. Les leçons déjà importées reçoivent automatiquement les nouveautés au démarrage.

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
node e2e/parcours.mjs http://127.0.0.1:8765 "" data/revision.db
```

Le dossier `frontend/dist` est versionné exprès : le PC de l'élève n'a besoin que de Python.

Organisation du code :

- `backend/app/services/llm` : fournisseurs Gemini, Groq et IA simulée, derrière une interface commune.
- `backend/app/services/generation` : file de tâches, consignes données à l'IA, validation des réponses.
- `backend/app/services/parcours.py` : étapes verrouillées, décidées côté serveur.
- `backend/app/services/srs.py` : répétition espacée, carnet d'erreurs, planning du jour.
- `backend/app/services/youtube.py` : recherche et tri des vidéos.
- `backend/app/routers` : API. `frontend/src` : interface React.
