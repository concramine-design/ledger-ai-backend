// Minimal backend that lets the LEDGER app's AI Assistant screen call a real
// Claude model — instead of the hard-coded canned answers in ledger-app.html.
//
// Setup:
//   npm install express @anthropic-ai/sdk cors dotenv
//   node server.js
//
// Two ways to supply the API key (either works, per-request wins):
//   1. In the app itself: tap the ⚙ on the AI screen and paste your key —
//      it's stored in the browser's localStorage and sent as a Bearer token
//      on each request, used only for that request, never logged or stored here.
//   2. In this server's .env file (ANTHROPIC_API_KEY=sk-ant-...) as a fallback
//      for a single-user always-on deployment where you don't want to type a
//      key into the app UI at all.
//
// Either way, the key never sits in the HTML/JS served to the browser.

import 'dotenv/config';
import path from 'path';
import { fileURLToPath } from 'url';
import express from 'express';
import cors from 'cors';
import Anthropic from '@anthropic-ai/sdk';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const app = express();
app.use(cors());                       // restrict to your app's origin in production
app.use(express.json({ limit: '256kb' }));

// Serves ledger-app.html (as public/index.html) at the same origin as the API.
// This means the phone can just visit http://<your-pc-lan-ip>:3000/ — the app's
// default backend URL resolves to this same origin automatically, no manual
// "http://localhost:3000" typo trap when loading it from another device.
app.use(express.static(path.join(__dirname, 'public')));

const SYSTEM_PROMPT = `You are the AI productivity analyst inside LEDGER, a dark, data-dense habit-tracking app.

You are given a JSON snapshot of the user's real habit/goal/XP data below their question. Rules:
- Only reference numbers, habit names, and goal names that appear in the snapshot. Never invent a statistic.
- If the snapshot doesn't contain enough information to answer, say so plainly instead of guessing.
- Keep answers under ~100 words. Terminal/dashboard tone: direct, numeric, no filler ("Great question!", "I'd be happy to...").
- Bold the numbers that matter most (using **markdown**) so they scan easily.
- Never mention mood, feelings, or emotional state — this app tracks habits and productivity only.`;

app.post('/api/ai', async (req, res) => {
  const { question, snapshot } = req.body ?? {};

  if (typeof question !== 'string' || !question.trim() || question.length > 500) {
    return res.status(400).json({ error: 'Missing or invalid "question".' });
  }
  if (!snapshot || typeof snapshot !== 'object') {
    return res.status(400).json({ error: 'Missing "snapshot" data.' });
  }

  // Per-request key from the app's Settings modal (Authorization: Bearer sk-ant-...)
  // takes priority; falls back to a server-configured key for single-user setups.
  // Nothing here logs or persists the key — it lives only for this one request.
  const authHeader = req.get('authorization') || '';
  const requestKey = authHeader.replace(/^Bearer\s+/i, '').trim();
  const apiKey = requestKey || process.env.ANTHROPIC_API_KEY;

  if (!apiKey) {
    return res.status(401).json({ error: 'No API key. Add one in the app’s AI settings, or set ANTHROPIC_API_KEY in .env.' });
  }

  try {
    const client = new Anthropic({ apiKey });
    const response = await client.messages.create({
      model: 'claude-opus-5',              // swap for claude-sonnet-5 / claude-haiku-4-5 if cost matters more than depth
      max_tokens: 400,
      output_config: { effort: 'low' },     // this is a quick Q&A, not a hard reasoning task — keep it snappy
      system: SYSTEM_PROMPT,
      messages: [
        {
          role: 'user',
          content:
            `DATA SNAPSHOT (JSON — this is the only data you may reference):\n${JSON.stringify(snapshot)}\n\n` +
            `USER QUESTION: ${question}`,
        },
      ],
    });

    const text = response.content.find((b) => b.type === 'text')?.text ?? '';
    res.json({ answer: text });
  } catch (err) {
    console.error('AI request failed:', err);
    if (err instanceof Anthropic.AuthenticationError) {
      return res.status(401).json({ error: 'That API key was rejected by Anthropic. Double-check it in the app’s AI settings.' });
    }
    if (err instanceof Anthropic.RateLimitError) {
      return res.status(429).json({ error: 'Rate limited — try again in a moment.' });
    }
    res.status(502).json({ error: 'The AI analyst is unavailable right now.' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`LEDGER AI backend listening on :${PORT}`));
