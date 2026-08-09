# Faire fonctionner l'IA de LEDGER pour de vrai

## Pourquoi l'Artifact publié ne peut pas le faire

`claude.ai/code/artifact/...` sert la page dans un bac à sable avec une CSP qui bloque
tout `fetch`/XHR vers un hôte externe — y compris votre propre serveur. Aucune
capacité "appeler un LLM" n'est branchée aux Artifacts pour ce compte. Donc cette
fonctionnalité doit vivre **en dehors** du système Artifact : une vraie app web ou
mobile, hébergée par vous (Vercel, Render, Fly.io, un VPS, etc.), avec son propre backend.

## Mise en place

```bash
cd ledger-ai-backend
npm install
cp .env.example .env
# éditez .env et collez votre clé (console.anthropic.com → API Keys)
npm start
```

Sans clé statique : `ant auth login` une fois sur la machine, puis supprimez
`ANTHROPIC_API_KEY` de `.env` — le SDK reprend automatiquement la session connectée.

## Patch côté client (`ledger-app.html`)

Remplacez l'objet `AI_ANSWERS` codé en dur et la fonction `sendChat` par un appel
réseau vers votre backend. Le snapshot envoyé est construit à partir des **vraies**
variables `HABITS`/`GOALS`/`level`/`xp` déjà présentes dans le fichier — donc les
réponses de l'IA porteront sur les données réelles de l'utilisateur, jamais inventées.

```js
async function askBackend(question) {
  const snapshot = {
    level, xp, xpToday,
    habits: HABITS.map(h => ({
      name: h.name,
      currentStreak: currentStreak(h),
      bestStreak: bestStreak(h),
      completion30d: Math.round(completionPct(h, 30) * 10) / 10,
      completion7d: Math.round(completionPct(h, 7) * 10) / 10,
    })),
    goals: GOALS.map(g => ({
      name: g.name, pct: g.pct, weekDelta: g.weekDelta, deadline: g.deadline,
    })),
  };

  const res = await fetch('https://your-backend.example.com/api/ai', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question, snapshot }),
  });
  if (!res.ok) throw new Error('AI request failed');
  const data = await res.json();
  return data.answer;
}

// Replace inside window.askAI(btn) and window.sendChat():
//   const answerFn = AI_ANSWERS[btn.textContent];
//   ...
//   appendBubble(answerFn ? answerFn() : "...", 'ai', true);
// with:
askBackend(question)
  .then(answer => { typing.remove(); appendBubble(answer, 'ai', true); })
  .catch(() => { typing.remove(); appendBubble('The AI analyst is unavailable right now.', 'ai'); });
```

## Sécurité — non négociable

- La clé Anthropic ne doit **jamais** apparaître dans du JS servi au navigateur.
- Validez/limitez la longueur de `question` côté serveur (déjà fait dans `server.js`).
- En prod : ajoutez du rate-limiting par utilisateur (ex. `express-rate-limit`) pour
  éviter qu'un abus ne fasse exploser la facture API.
- Restreignez `cors()` à l'origine exacte de votre app plutôt que de tout autoriser.

## Modèle et coût

Le backend utilise `claude-opus-5` avec `effort: "low"` (réponses rapides, pas de
raisonnement profond nécessaire pour ce cas d'usage). Pour réduire les coûts sur un
gros volume, remplacez par `claude-sonnet-5` ou `claude-haiku-4-5` dans `server.js`.
