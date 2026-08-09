// Vercel serverless function — any file under /api becomes a route at
// /api/<filename>, so this file alone handles POST /api/ai. Same logic as
// server.js (used for local dev / self-hosting), just in Vercel's handler shape.
//
// Calls Google's Gemini API (Interactions endpoint) instead of Anthropic's —
// no SDK dependency needed, plain fetch() is enough (Node 18+ / Vercel both
// ship a global fetch).

const GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/interactions';
const GEMINI_MODEL = 'gemini-3.6-flash';

const SYSTEM_PROMPT = `You are the AI productivity analyst inside LEDGER, a dark, data-dense habit-tracking app.

You are given a JSON snapshot of the user's real habit/goal/XP data below their question. Rules:
- Only reference numbers, habit names, and goal names that appear in the snapshot. Never invent a statistic.
- If the snapshot doesn't contain enough information to answer, say so plainly instead of guessing.
- Keep answers under ~100 words. Terminal/dashboard tone: direct, numeric, no filler ("Great question!", "I'd be happy to...").
- Bold the numbers that matter most (using **markdown**) so they scan easily.
- Never mention mood, feelings, or emotional state — this app tracks habits and productivity only.`;

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
        input:
          `DATA SNAPSHOT (JSON — this is the only data you may reference):\n${JSON.stringify(snapshot)}\n\n` +
          `USER QUESTION: ${question}`,
      }),
    });

    const rawData = await geminiRes.json().catch(() => ({}));
    // Error responses come back wrapped in an array: [{ "error": {...} }].
    // Success responses do not. Unwrap either shape into a plain object.
    const data = Array.isArray(rawData) ? (rawData[0] ?? {}) : rawData;

    if (!geminiRes.ok) {
      const message = data?.error?.message || `Gemini returned ${geminiRes.status}`;
      // Google returns 400 INVALID_ARGUMENT (not 401/403) for a bad key —
      // detect it by the structured "reason" field, not just the HTTP status.
      const invalidKey = (data?.error?.details || []).some((d) => d.reason === 'API_KEY_INVALID');
      if (invalidKey || geminiRes.status === 401 || geminiRes.status === 403) {
        res.status(401).json({ error: 'That API key was rejected by Google. Double-check it in the app’s AI settings.' });
        return;
      }
      if (geminiRes.status === 429) {
        res.status(429).json({ error: 'Rate limited — try again in a moment.' });
        return;
      }
      res.status(502).json({ error: message });
      return;
    }

    const modelStep = (data.steps || []).find((s) => s.type === 'model_output');
    const textBlock = modelStep?.content?.find((c) => c.type === 'text');
    const text = textBlock?.text ?? '';

    res.status(200).json({ answer: text });
  } catch (err) {
    console.error('AI request failed:', err);
    res.status(502).json({ error: 'The AI analyst is unavailable right now.' });
  }
}
