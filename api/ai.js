// Vercel serverless function — any file under /api becomes a route at
// /api/<filename>, so this file alone handles POST /api/ai. Same logic as
// server.js (used for local dev / self-hosting), sharing lib/ai-shared.js so
// the two never drift out of sync.

import {
  GEMINI_ENDPOINT,
  GEMINI_MODEL,
  SYSTEM_PROMPT,
  TOOLS,
  extractStepsPayload,
  classifyGeminiError,
  unwrapGeminiSuccess,
} from '../lib/ai-shared.js';

export default async function handler(req, res) {
  // Same-origin on Vercel by default, but these headers keep it working if the
  // app is ever opened from a different origin (e.g. testing the raw HTML file
  // locally against an already-deployed API).
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization');

  if (req.method === 'OPTIONS') {
    res.status(204).end();
    return;
  }
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method not allowed' });
    return;
  }

  const { question, snapshot } = req.body ?? {};

  if (typeof question !== 'string' || !question.trim() || question.length > 500) {
    res.status(400).json({ error: 'Missing or invalid "question".' });
    return;
  }
  if (!snapshot || typeof snapshot !== 'object') {
    res.status(400).json({ error: 'Missing "snapshot" data.' });
    return;
  }

  // Per-request key from the app's Settings modal (Authorization: Bearer AIza...)
  // takes priority; falls back to a Vercel-configured env var for single-user setups.
  const authHeader = req.headers['authorization'] || '';
  const requestKey = authHeader.replace(/^Bearer\s+/i, '').trim();
  const apiKey = requestKey || process.env.GEMINI_API_KEY;

  if (!apiKey) {
    res.status(401).json({ error: 'No API key. Add one in the app’s AI settings, or set GEMINI_API_KEY in Vercel’s project environment variables.' });
    return;
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
      res.status(status).json({ error });
      return;
    }

    const data = unwrapGeminiSuccess(rawData);
    const { text, actions } = extractStepsPayload(data);

    res.status(200).json({ answer: text, actions });
  } catch (err) {
    console.error('AI request failed:', err);
    res.status(502).json({ error: 'The AI analyst is unavailable right now.' });
  }
}
