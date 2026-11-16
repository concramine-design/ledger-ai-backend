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
  has_methods?: boolean;
  open_mistakes?: number;
  mastery: number;
  color: "rouge" | "orange" | "vert";
  mindmap?: MindMap | null;
}

export interface MindMap {
  centre: string;
  branches: { titre: string; feuilles: string[] }[];
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
  youtube: boolean;
  streak: number;
}

export interface StepInfo {
  key: string;
  label: string;
  description: string;
  minutes: number;
}

export interface SessionSize {
  questions: number;
  cards: number;
  minutes: number;
}

export type NextStep =
  | { kind: "import" }
  | { kind: "done"; mastered: number; next_review: string | null }
  | { kind: "review"; size: SessionSize; subjects: string[]; lessons: number }
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
  // Rédaction : notes par critère et fautes expliquées.
  mode?: "redaction";
  criteres?: { nom: string; note: number; commentaire: string }[];
  fautes?: { extrait: string; type: string; explication: string; piste: string }[];
  // Schéma à légender : chaque case juste ou fausse.
  cases?: boolean[];
}

export interface TestQuestion {
  id: number;
  type: "qcm" | "ouverte" | "schema";
  enonce: string;
  choix: string[];
  notion: string;
  schema?: { disposition: "chaine" | "cycle" | "ensemble"; cases: { role: string }[]; banque: string[] };
  attempt: {
    status: "pending" | "graded";
    answer_text: string;
    choice_index: number | null;
    score: number | null;
    feedback: Feedback | null;
  } | null;
  correction: { bonne_reponse: number | null; reponse_modele: string; explication: string; noms: string[] } | null;
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
  document: string;
  mode: "elements" | "redaction";
  hints: string[];
  hints_total: number;
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
  vocabulaire?: { mot: string; sens: string; exemple: string }[];
  auteurs?: { nom: string; these: string; argument: string }[];
}

export interface Video {
  id: string;
  title: string;
  channel: string;
  duration_s: number;
  raison: string;
}

export interface StepData {
  lesson: Lesson;
  step: StepInfo;
  status: "current" | "done";
  language: Lang;
  kind: Kind;
  generation: Generation;
  ready: boolean;
  content?: Explanation | Summary | null;
  videos?: { status: string; videos: Video[] } | null;
  mindmap?: MindMap | null;
  cards?: number;
  has_methods?: boolean;
  feuille?: { submissions: FeuilleSubmission[] };
  explique?: Talk;
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

export interface ReviewResult {
  passed: boolean;
  done: boolean;
  next_due: string | null;
}

export interface AnswerResult<Q> {
  question: Q;
  set: SetResult | null;
  progress: { succeeded: number; required: number } | null;
  review: ReviewResult | null;
  step_done: boolean;
  mastered: boolean;
}

export interface LessonBrief {
  id: number;
  title: string;
  chapter?: string;
  subject: Subject;
  language: Lang;
}

export interface ReviewItem {
  id: number;
  kind: "lesson" | "error" | "card";
  stage: number;
  lesson: LessonBrief;
  questions?: TestQuestion[];
  card?: { recto: string; verso: string };
}

export interface ReviewSession {
  items: ReviewItem[];
  size: SessionSize;
  remaining: number;
  waiting: number;
  total_due: number;
}

export interface Plan {
  today: {
    size: SessionSize;
    total_due: number;
    remaining: number;
    waiting: number;
    subjects: { subject: Subject; lessons: string[]; count: number }[];
  };
  upcoming: { date: string; count: number }[];
  exams: Exam[];
  open_mistakes: number;
}

export interface MistakeEntry {
  id: number;
  lesson: LessonBrief;
  source: string;
  notion: string;
  enonce: string;
  given: string;
  expected: string;
  created_at: string;
  resolved: boolean;
  successes: number;
  next_due: string | null;
}

export interface MethodsSheet {
  chapter: { id: number; title: string };
  subject: Subject;
  language: Lang;
  lessons: {
    id: number;
    title: string;
    types: { nom: string; reconnaitre: string; etapes: string[]; erreur_classique: string; exemple: string }[];
  }[];
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

export interface FeuillePoint {
  point: string;
  etat: "ok" | "partiel" | "absent";
  rappel: string;
}

export interface FeuilleResult {
  points: FeuillePoint[];
  erreurs: { extrait: string; correction: string }[];
  message: string;
}

export interface FeuilleSubmission {
  text: string;
  coverage: number;
  passed: boolean;
  result: FeuilleResult;
}

export interface Talk {
  attempt: number;
  messages: { role: "eleve" | "camarade"; content: string }[];
  evaluation: {
    clarte: number;
    exactitude: number;
    completude: number;
    reponses: number;
    points_clairs: string;
    a_ameliorer: string;
    erreurs: string[];
  } | null;
  score: number | null;
  passed: boolean | null;
}

export interface Activity {
  streak: number;
  history: { date: string; actions: number; pomodoros: number; minutes: number }[];
  rewards: { key: string; label: string; description: string; earned: boolean }[];
}

export interface MockQuestion {
  numero: string;
  enonce: string;
  points: number;
  correction?: string;
}

export interface MockPaper {
  titre: string;
  exercices: { titre: string; contexte: string; questions: MockQuestion[] }[];
}

export interface MockResult {
  note: number;
  sur: number;
  questions: {
    numero: string;
    points: number;
    note: number;
    commentaire: string;
    correction: string;
    notion: string;
    lecon: string;
    lesson_id: number | null;
  }[];
  bilan: { lecon: string; lesson_id: number | null; taux: number; notions: string[] }[];
}

export interface MockExam {
  id: number;
  subject: Subject;
  language: Lang;
  status: "pending" | "ready" | "started" | "graded" | "error";
  error: string | null;
  duration_min: number;
  remaining_seconds: number | null;
  lessons: string[];
  paper: MockPaper | null;
  summary: { exercices: number; questions: number } | null;
  answers: Record<string, string>;
  result: MockResult | null;
  created_at: string;
}

export interface PastExam {
  id: number;
  subject_id: number;
  title: string;
  status: "pending" | "ready" | "error";
  error: string | null;
  analysis: {
    duree_min: number | null;
    structure: string;
    types: { type: string; exemple: string; notions: string }[];
    style: string;
  } | null;
  created_at: string;
}

export interface PastExamGroup {
  subject: Subject;
  exams: PastExam[];
  recurring: { type: string; count: number; exemple: string }[];
}

export interface ParentOverview {
  streak: number;
  history: Activity["history"];
  subjects: {
    subject: Subject;
    exam: { date: string; title: string } | null;
    mastery: number;
    lessons: {
      id: number;
      title: string;
      chapter: string;
      mastery: number;
      color: "rouge" | "orange" | "vert";
      mastered: boolean;
      step: string;
      scores: Record<string, number>;
      open_mistakes: number;
      last_activity: string | null;
    }[];
  }[];
  open_mistakes: number;
  mock_exams: { id: number; subject: string; note: number | null; date: string }[];
  reports: { id: number; lesson: string; target: string; comment: string; excerpt: string; date: string }[];
  settings: Record<string, number>;
}
