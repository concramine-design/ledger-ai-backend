// Minimal backend that lets the LEDGER app's AI Assistant screen call a real
// Gemini model — instead of the hard-coded canned answers in ledger-app.html.
// Shares lib/ai-shared.js with api/ai.js (the Vercel version) so both stay in sync.
//
// Setup:
//   npm install express cors dotenv
//   node server.js
//
// Two ways to supply the API key (either works, per-request wins):
//   1. In the app itself: tap the ⚙ on the AI screen and paste your key —
//      it's stored in the browser's localStorage and sent as a Bearer token
//      on each request, used only for that request, never logged or stored here.
//   2. In this server's .env file (GEMINI_API_KEY=AIza...) as a fallback for a
//      single-user always-on deployment where you don't want to type a key
//      into the app UI at all.
//
// Either way, the key never sits in the HTML/JS served to the browser.

import 'dotenv/config';
import path from 'path';
import { fileURLToPath } from 'url';
import express from 'express';
import cors from 'cors';
import {
  GEMINI_ENDPOINT,
  GEMINI_MODEL,
  SYSTEM_PROMPT,
  TOOLS,
  extractStepsPayload,
  classifyGeminiError,
  unwrapGeminiSuccess,
} from './lib/ai-shared.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
app.use(cors());                       // restrict to your app's origin in production
app.use(express.json({ limit: '256kb' }));

// Serves ledger-app.html (as public/index.html) at the same origin as the API.
// This means the phone can just visit http://<your-pc-lan-ip>:3000/ — the app's
// default backend URL resolves to this same origin automatically, no manual
// "http://localhost:3000" typo trap when loading it from another device.
app.use(express.static(path.join(__dirname, 'public')));

app.post('/api/ai', async (req, res) => {
  const { question, snapshot } = req.body ?? {};

  if (typeof question !== 'string' || !question.trim() || question.length > 500) {
    return res.status(400).json({ error: 'Missing or invalid "question".' });
  }
  if (!snapshot || typeof snapshot !== 'object') {
    return res.status(400).json({ error: 'Missing "snapshot" data.' });
  }

  // Per-request key from the app's Settings modal (Authorization: Bearer AIza...)
  // takes priority; falls back to a server-configured key for single-user setups.
  // Nothing here logs or persists the key — it lives only for this one request.
  const authHeader = req.get('authorization') || '';
  const requestKey = authHeader.replace(/^Bearer\s+/i, '').trim();
  const apiKey = requestKey || process.env.GEMINI_API_KEY;

  if (!apiKey) {
    return res.status(401).json({ error: 'No API key. Add one in the app’s AI settings, or set GEMINI_API_KEY in .env.' });
  }

  try {
    const geminiRes = await fetch(GEMINI_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-goog-api-key': apiKey,
      },
      body: JSON.stringify({
        model: GEMINI_MODEL,
        system_instruction: SYSTEM_PROMPT,
        tools: TOOLS,
        input:
          `DATA SNAPSHOT (JSON — this is the only data you may reference):\n${JSON.stringify(snapshot)}\n\n` +
          `USER REQUEST: ${question}`,
      }),
    });

    const rawData = await geminiRes.json().catch(() => ({}));

    if (!geminiRes.ok) {
      const { status, error } = classifyGeminiError(rawData, geminiRes.status);
      return res.status(status).json({ error });
    }

    const data = unwrapGeminiSuccess(rawData);
    const { text, actions } = extractStepsPayload(data);

    res.json({ answer: text, actions });
  } catch (err) {
    console.error('AI request failed:', err);
    res.status(502).json({ error: 'The AI analyst is unavailable right now.' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`LEDGER AI backend listening on :${PORT}`));
