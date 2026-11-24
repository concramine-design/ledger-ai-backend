# Mes révisions — contexte pour Claude Code

Application locale d'aide à la révision pour **une élève marocaine de tronc commun** (première année du lycée).
Le propriétaire du projet est son grand frère (ou parent) : il n'est pas développeur, il teste sur le PC Windows de sa sœur.

## Comment travailler avec lui

- **Répondre en français**, simplement, sans jargon. Phrases courtes, étapes numérotées quand il doit agir.
- Il teste **sur Windows**, sur le PC de sa sœur, à partir d'un **ZIP** : après chaque changement, construire le ZIP
  avec `git archive --format=zip --prefix=mes-revisions/ -o <scratchpad>/mes-revisions-vX.Y.zip HEAD:revision` et le lui envoyer.
  Pour mettre à jour, il extrait par-dessus l'ancien dossier en gardant `data/` et `.env`, puis relance `installer.bat`.
- Quand il propose une **grosse idée d'architecture**, il veut d'abord en discuter (avis, détails, questions) :
  ne pas coder avant son feu vert explicite (« commence », « do the work »).
- Ne jamais mettre de **clé API** dans le code, un commit ou un message. Les clés vont dans `revision/.env` (ignoré par git).
  Ne jamais lui demander de coller une clé dans le chat.
- Être honnête sur ce qui n'a pas pu être testé (les `.bat` / PowerShell ne tournent pas dans le conteneur Linux ;
  les vrais appels IA demandent ses clés).

## Le produit (cahier des charges d'origine, résumé)

Elle travaille beaucoup mais sans méthode. L'application prépare tout à sa place et la guide **leçon par leçon**
dans un **parcours obligatoire à étapes verrouillées**, pour réussir ses devoirs surveillés.
Principes : se tester plutôt que relire, espacer les révisions, mélanger les chapitres, apprendre de ses erreurs.

- Matières préconfigurées : Maths, Physique-Chimie, SVT, Philosophie, Arabe, Français, Anglais.
  Langue des explications réglable par matière (fr / ar / en) ; l'arabe s'affiche de droite à gauche, les formules restent LTR.
- Import d'une leçon (PDF, photos du cahier avec lecture par l'IA, texte collé), rangée par matière et chapitre.
  **Tout est généré automatiquement dès l'import, sans bouton « générer ».**
- Parcours (côté serveur, impossible à contourner) : 1 Comprendre (explication, exemples, vidéos, carte mentale, chat)
  → 2 Mini-test (échec = ré-explication autrement + nouveau test) → 3 Feuille blanche (écrire de mémoire, comparaison)
  → 4 Résumé (fiche, export PDF) → 5 Quiz complet (majorité de questions ouvertes, seuil 80 % réglable)
  → 6 Explique-moi (l'IA joue un élève qui pose des questions, puis note la clarté)
  → 7 Exercices niveau 1 → 2 → 3 → 8 leçon maîtrisée, puis rappels espacés (J+1, 3, 7, 14, 30).
- Le chat ne donne jamais la réponse directement : il pose d'abord une question.
- Exercices selon la matière : sciences (indices à 3 niveaux, correction détaillée en dernier recours, fiche « méthodes types »,
  SVT : documents et schémas à légender) ; langues (grammaire, vocabulaire en cartes, compréhension, production écrite corrigée
  sans réécrire) ; philosophie (notions et auteurs, plan, rédaction argumentée).
- Révision : planning « à revoir aujourd'hui » qui mélange les matières, carnet d'erreurs (erreurs reposées autrement),
  contrôle blanc chronométré noté sur 20 avec bilan, anciens devoirs importés (types de questions récurrents, style du prof).
- Interface : française, mode sombre, écran d'accueil « Ta prochaine étape », carte de progression, maîtrise par chapitre
  rouge/orange/vert, série de jours, minuteur 25 min + pause, récompenses sans classement, KaTeX,
  mode parent/frère protégé par code (progression + réglage des seuils), « Signaler une erreur » + rappel « c'est le professeur
  qui a raison ».

## Architecture

```
revision/
  installer.bat, lancer.bat        installation Windows + lancement (raccourci bureau via outils/raccourci.ps1)
  connecter_claude.bat             branche le serveur MCP dans l'application Claude pour ordinateur (outils/connecter_claude.ps1)
  .env.example                     toutes les variables (copié en .env à l'installation)
  backend/app/                     FastAPI + SQLite (SQLAlchemy), sert aussi l'interface compilée
    main.py, config.py, db.py, models.py, launcher.py
    routers/                       setup, lessons, steps, chat, reviews, parent, exams
    services/llm/                  fournisseurs : gemini.py, groq.py, claude.py (API), mock.py (IA simulée) ; jsonfix.py
    services/generation/           worker.py (file de tâches SQLite), generators.py, prompts.py (consignes), content.py (validation pydantic)
    services/                      parcours.py (étapes verrouillées), srs.py (répétition espacée), followup.py, evaluation.py,
                                   activity.py (série, maîtrise, récompenses), exams.py (contrôle blanc, anciens devoirs),
                                   youtube.py, ingestion.py (PDF, photos)
    mcp_server.py                  serveur MCP « Révision » (préparation par Claude) ; lancé par backend/mcp_revision.py
  backend/tests/                   pytest (IA simulée, sans réseau)
  frontend/                        React + Vite + TypeScript ; frontend/dist est VERSIONNÉ (le PC de l'élève n'a pas Node)
  e2e/parcours.mjs                 parcours complet dans un vrai navigateur (Playwright), IA simulée
```

L'application tourne **en local** sur le PC de l'élève : `http://127.0.0.1:8765`, données dans `revision/data/`.

## IA : qui fait quoi (décisions prises)

- **Gemini Flash** (gratuit, `GEMINI_API_KEY`) est l'IA par défaut : préparation des leçons et échanges en direct.
  Repli automatique vers un autre modèle Gemini en cas de surcharge (503) ou de limite gratuite atteinte (429).
- **Mode « Claude prépare la nuit »** (`PREPARATION_PAR=claude`, optionnel, **désactivé par défaut**) : les tâches prévisibles
  (lecture des photos, explication, tests, exercices, résumé, carte mentale, rappels, reprises d'erreurs) attendent Claude ;
  dans l'application Claude pour ordinateur (**mode Chat**, pas Claude Code), on écrit « Prépare les leçons de Révision » :
  Claude utilise le serveur MCP (`travail_en_attente`, `lire_lecon`, `lire_page`, `enregistrer_texte_lecon`,
  `obtenir_consigne`, `enregistrer_contenu`). Révision lui donne les mêmes consignes qu'à Gemini et vérifie chaque réponse.
  Si Claude n'est pas passé à `HEURE_LIMITE_CLAUDE` (07:00), la file prend le relais ; bouton « Préparer maintenant ».
  Les réactions immédiates (nouveau test après échec, ré-explication, nouvel exercice, vidéos) restent automatiques.
- **API Claude** (`ANTHROPIC_API_KEY`, payante) : codée mais inactive tant qu'il n'y a pas de clé ; il ne veut pas payer d'API.
- Testé et écarté : **Gemma 4** (surchargé, rien produit en 25 min), **Gemini Pro** (quota gratuit = 0),
  **Groq** (console bloquée depuis le Maroc), **NotebookLM** (pas d'API grand public).
- YouTube Data API (`YOUTUBE_API_KEY`) pour 3 vidéos par leçon, avec la raison du choix.

## Commandes

```bash
cd revision
python -m venv .venv && .venv/bin/pip install -r backend/requirements-dev.txt
cd backend && ../.venv/bin/python -m pytest -q            # ~114 tests, IA simulée
../.venv/bin/python -m app.launcher                        # lance l'app (LLM_PROVIDER=mock pour sans clé)
cd ../frontend && npm install && npm run build             # régénère frontend/dist (à committer)
node e2e/parcours.mjs http://127.0.0.1:8765 "" <data>/revision.db   # serveur lancé avec LLM_PROVIDER=mock sur base vide
```

Après un changement d'interface : `npx tsc --noEmit`, `npm run build`, committer `frontend/dist`.
Fichiers Windows (`*.bat`, `*.ps1`) : ASCII uniquement, fins de ligne CRLF (voir `.gitattributes`).

## État (fin novembre 2026)

- V1, V2, V3 terminées (tout le cahier des charges), plus le mode « Claude prépare la nuit ».
- Le propriétaire a installé la version 3.3 sur le PC de sa sœur : import d'un PDF de maths réussi, préparation OK.
- Le mode Claude via MCP n'a pas encore été vérifié sur son PC (première tentative faite par erreur dans Claude Code au lieu
  du Chat de l'application Claude). `connecter_claude.bat` n'a jamais pu être exécuté dans le conteneur.

## Idées en attente (à proposer, pas à faire sans accord)

- Rendre discret le cadre jaune « souci passager » quand il concerne une étape lointaine (ex. exercices niveau 2).
- Lecture audio de la fiche de résumé (l'équivalent des résumés audio de NotebookLM).
