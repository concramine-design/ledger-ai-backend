// Client de l'API locale et types partagés.

export type Lang = "fr" | "ar" | "en";
export type Kind = "sciences" | "langue" | "philo";

export interface Subject {
  id: number;
  code: string | null;
  name: string;
  kind: Kind;
  language: Lang;
  color: string;
  enabled: boolean;
  available: boolean;
}

export interface Exam {
  id: number;
  subject_id: number;
  subject_name: string;
  date: string;
  title: string;
  days_left: number;
}

export interface Problem {
  kind: string | null;
  message: string | null;
  label: string;
  fatal: boolean;
  retry_in: number | null;
}

export interface Generation {
  total: number;
  done: number;
  active: boolean;
  current: string | null;
  problem: Problem | null;
}

export type StepStatus = "done" | "current" | "locked" | "soon";

export interface PathStep {
  key: string;
  label: string;
  description: string;
  minutes: number;
  status: StepStatus;
  score: number | null;
}

export interface Lesson {
  id: number;
  title: string;
  chapter: { id: number; title: string };
  subject: Subject;
  source_type: "text" | "pdf" | "photo";
  progress: number;
  mastered: boolean;
  current_step: { key: string; label: string } | null;
  generation: Generation;
  has_text: boolean;
  truncated: boolean;
  path?: PathStep[];
  exam?: Exam | null;
  current_ready?: boolean;
}

export interface AppState {
  version: string;
  onboarded: boolean;
  settings: {
    minitest_threshold: number;
    quiz_threshold: number;
    exercise_threshold: number;
    exercises_required: number;
  };
  ai: { configured: boolean; provider: string | null; demo: boolean };
}

export interface StepInfo {
  key: string;
  label: string;
  description: string;
  minutes: number;
}

export type NextStep =
  | { kind: "import" }
  | { kind: "done"; mastered: number }
  | {
      kind: "step";
      lesson: Lesson;
      step: StepInfo;
      ready: boolean;
      generation: Generation;
      exam: Exam | null;
      mastered: number;
      total: number;
    };

export interface EvalElement {
  attendu?: string;
  etat: "ok" | "partiel" | "absent";
  commentaire: string;
}

export interface Feedback {
  correct?: boolean;
  elements?: EvalElement[];
  points_justes?: string;
  manque?: string;
  erreurs?: string[];
  conseil?: string;
}

export interface TestQuestion {
  id: number;
  type: "qcm" | "ouverte";
  enonce: string;
  choix: string[];
  notion: string;
  attempt: {
    status: "pending" | "graded";
    answer_text: string;
    choice_index: number | null;
    score: number | null;
    feedback: Feedback | null;
  } | null;
  correction: { bonne_reponse: number | null; reponse_modele: string; explication: string } | null;
}

export interface TestSet {
  id: number;
  version: number;
  state: "active" | "passed" | "failed";
  score: number | null;
  questions: TestQuestion[];
}

export interface ReexplainPoint {
  notion: string;
  ce_qui_a_coince: string;
  explication: string;
  exemple: string;
  astuce: string;
}

export interface Exercise {
  id: number;
  titre: string;
  enonce: string;
  type_exercice: string;
  notion: string;
  state: "todo" | "tried" | "succeeded" | "revealed";
  is_variant: boolean;
  draft: string;
  can_reveal: boolean;
  attempts: { answer_text: string; score: number | null; feedback: Feedback | null; after_reveal: boolean }[];
  correction: { etapes: string[]; reponse_finale: string } | null;
}

export interface Explanation {
  titre: string;
  accroche: string;
  sections: { titre: string; contenu: string; exemple: string; a_retenir: string }[];
  notions: string[];
}

export interface Summary {
  titre: string;
  definitions: { terme: string; definition: string }[];
  formules: { nom: string; formule: string; quand: string }[];
  methodes: { titre: string; etapes: string[] }[];
  pieges: { piege: string; conseil: string }[];
  a_savoir_par_coeur: string[];
}

export interface StepData {
  lesson: Lesson;
  step: StepInfo;
  status: "current" | "done";
  language: Lang;
  generation: Generation;
  ready: boolean;
  content?: Explanation | Summary | null;
  threshold?: number;
  set?: TestSet | null;
  previous?: (TestSet & { reexplain: { points: ReexplainPoint[] } | null }) | null;
  exercises?: Exercise[];
  progress?: { succeeded: number; required: number };
  variant_pending?: boolean;
}

export interface SetResult {
  state: "passed" | "failed";
  score: number;
  threshold: number;
  passed: boolean;
  mastered: boolean;
}

export interface AnswerResult<Q> {
  question: Q;
  set: SetResult | null;
  progress: { succeeded: number; required: number } | null;
  step_done: boolean;
  mastered: boolean;
}

export class ApiError extends Error {
  status: number;
  kind: string | null;
  constructor(status: number, message: string, kind: string | null = null) {
    super(message);
    this.status = status;
    this.kind = kind;
  }
  /** Erreur passagère de l'IA ou du réseau : on peut proposer de réessayer. */
  get retryable(): boolean {
    return this.status === 503 || this.status === 0;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    const init: RequestInit = { method };
    if (body instanceof FormData) {
      init.body = body;
    } else if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    resp = await fetch(`/api${path}`, init);
  } catch {
    throw new ApiError(0, "L'application ne répond plus. Relance-la avec le raccourci du bureau.");
  }
  if (resp.ok) return (await resp.json()) as T;
  let message = "Une erreur est survenue.";
  let kind: string | null = null;
  try {
    const data = await resp.json();
    const detail = data?.detail;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = "Vérifie les informations saisies.";
    else if (detail && typeof detail === "object") {
      message = detail.message ?? message;
      kind = detail.kind ?? null;
    }
  } catch {
    /* réponse non JSON */
  }
  throw new ApiError(resp.status, message, kind);
}

export const api = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body),
  patch: <T,>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  put: <T,>(path: string, body?: unknown) => request<T>("PUT", path, body),
  del: <T,>(path: string) => request<T>("DELETE", path),
};

export const LANG_LABELS: Record<Lang, string> = { fr: "Français", ar: "Arabe", en: "Anglais" };
export const KIND_LABELS: Record<Kind, string> = { sciences: "Sciences", langue: "Langue", philo: "Philosophie" };
