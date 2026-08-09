// Shared between api/ai.js (Vercel) and server.js (local/self-host) so the two
// never drift out of sync again. Talks to Google's Gemini Interactions API.

export const GEMINI_ENDPOINT = 'https://generativelanguage.googleapis.com/v1beta/interactions';
export const GEMINI_MODEL = 'gemini-3.6-flash';

export const SYSTEM_PROMPT = `You are the AI productivity analyst inside LEDGER, a dark, data-dense habit-tracking app.

You are given a JSON snapshot of the user's real habit/goal/XP data below their question. Rules:
- Only reference numbers, habit names, and goal names that appear in the snapshot. Never invent a statistic.
- If the snapshot doesn't contain enough information to answer, say so plainly instead of guessing.
- Keep text answers under ~100 words. Terminal/dashboard tone: direct, numeric, no filler ("Great question!", "I'd be happy to...").
- Bold the numbers that matter most (using **markdown**) so they scan easily.
- Never mention mood, feelings, or emotional state — this app tracks habits and productivity only.
- When the user asks you to change something (mark a habit done/undone, create a habit, create a goal, update a goal's progress), call the matching tool instead of just describing what you'd do. Match habit/goal names from the request to the closest one in the snapshot — don't ask for clarification unless genuinely ambiguous between two very different items.
- When the user is only asking a question (not requesting a change), just answer in text — do not call a tool.`;

export const TOOLS = [
  {
    type: 'function',
    name: 'mark_habit',
    description: "Mark one of the user's existing habits as done or not done for today.",
    parameters: {
      type: 'object',
      properties: {
        habit: { type: 'string', description: 'The habit name (or close match) from the data snapshot.' },
        done: { type: 'boolean', description: 'true to mark complete, false to mark incomplete.' },
      },
      required: ['habit', 'done'],
    },
  },
  {
    type: 'function',
    name: 'create_habit',
    description: 'Create a brand new habit that does not yet exist in the snapshot.',
    parameters: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Short habit name, e.g. "MEDITATE 10M".' },
        sub: { type: 'string', description: 'Short category/subtitle, e.g. "MORNING" or "DAILY". Optional.' },
        xp: { type: 'number', description: 'XP awarded per completion, 5-30. Optional, defaults to 10.' },
      },
      required: ['name'],
    },
  },
  {
    type: 'function',
    name: 'create_goal',
    description: 'Create a brand new goal that does not yet exist in the snapshot.',
    parameters: {
      type: 'object',
      properties: {
        name: { type: 'string', description: 'Goal name, e.g. "PASS MEDICAL EXAM".' },
        deadline: { type: 'string', description: 'Deadline in YYYY-MM-DD format.' },
      },
      required: ['name', 'deadline'],
    },
  },
  {
    type: 'function',
    name: 'update_goal_progress',
    description: "Set an existing goal's completion percentage.",
    parameters: {
      type: 'object',
      properties: {
        goal: { type: 'string', description: 'The goal name (or close match) from the data snapshot.' },
        pct: { type: 'number', description: 'New completion percentage, 0-100.' },
      },
      required: ['goal', 'pct'],
    },
  },
];

/** Unwraps Gemini's response shape into { text, actions }. */
export function extractStepsPayload(data) {
  const steps = data.steps || [];
  const modelStep = steps.find((s) => s.type === 'model_output');
  const textBlock = modelStep?.content?.find((c) => c.type === 'text');
  const text = textBlock?.text ?? '';

  const actions = steps
    .filter((s) => s.type === 'function_call')
    .map((s) => ({ name: s.name, arguments: s.arguments || {} }));

  return { text, actions };
}

/** Normalizes Gemini's error shape (sometimes array-wrapped) and classifies it. */
export function classifyGeminiError(rawData, httpStatus) {
  const data = Array.isArray(rawData) ? (rawData[0] ?? {}) : rawData;
  const message = data?.error?.message || `Gemini returned ${httpStatus}`;
  const invalidKey = (data?.error?.details || []).some((d) => d.reason === 'API_KEY_INVALID');
  if (invalidKey || httpStatus === 401 || httpStatus === 403) {
    return { status: 401, error: 'That API key was rejected by Google. Double-check it in the app’s AI settings.' };
  }
  if (httpStatus === 429) {
    return { status: 429, error: 'Rate limited — try again in a moment.' };
  }
  return { status: 502, error: message };
}

export function unwrapGeminiSuccess(rawData) {
  return Array.isArray(rawData) ? (rawData[0] ?? {}) : rawData;
}
