import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type AnswerResult, type Exercise, type Lang } from "../api";
import { AnswerBox, FeedbackView } from "../components/Answer";
import { Md } from "../components/Md";
import { TrustNote } from "../components/Report";
import { Icon, Modal, Notice, Spinner } from "../components/Ui";
import { usePoll } from "../hooks";
import type { StepProps } from "../pages/StepPage";

const STATE_BADGE: Record<Exercise["state"], { label: string; tone: string }> = {
  todo: { label: "À faire", tone: "muted" },
  tried: { label: "À retenter", tone: "warn" },
  succeeded: { label: "Réussi", tone: "ok" },
  revealed: { label: "Correction vue", tone: "muted" },
};

interface CardProps {
  ex: Exercise;
  number: number;
  lang: Lang;
  lessonId: number;
  onResult: (r: AnswerResult<Exercise>) => void;
  onRevealed: (ex: Exercise) => void;
}

function ExerciseCard({ ex, number, lang, lessonId, onResult, onRevealed }: CardProps) {
  const [text, setText] = useState(ex.draft);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [confirm, setConfirm] = useState(false);
  const last = ex.attempts[ex.attempts.length - 1];
  const solved = ex.state === "succeeded" || ex.state === "revealed";
  const badge = STATE_BADGE[ex.state];

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      onResult(await api.post<AnswerResult<Exercise>>(`/questions/${ex.id}/answer`, { answer_text: text }));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    } finally {
      setBusy(false);
    }
  };

  const reveal = async () => {
    setConfirm(false);
    try {
      const r = await api.post<{ question: Exercise }>(`/questions/${ex.id}/reveal`);
      onRevealed(r.question);
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    }
  };

  return (
    <article className={`card exercise exercise-${ex.state}`}>
      <div className="row between">
        <h3>
          Exercice {number}
          {ex.is_variant && <span className="tag">Nouvel essai</span>}
        </h3>
        <span className={`badge badge-${badge.tone}`}>{badge.label}</span>
      </div>
      {ex.type_exercice && (
        <p className="muted small" dir="auto">
          {ex.type_exercice}
        </p>
      )}
      <Md text={ex.enonce} lang={lang} className="enonce" />

      {!solved && (
        <>
          <AnswerBox value={text} onChange={setText} disabled={busy} rows={6} placeholder="Rédige ta solution, étape par étape…" />
          {error && (
            <Notice tone="warn">
              {error.message} {error.retryable && "Ta réponse est conservée."}
            </Notice>
          )}
          <div className="row between">
            {ex.can_reveal ? (
              <button className="link-btn" onClick={() => setConfirm(true)}>
                Voir la correction détaillée
              </button>
            ) : (
              <span className="muted small">Essaie d'abord : la correction vient après ta tentative.</span>
            )}
            <button className="btn" disabled={busy || !text.trim()} onClick={() => void submit()}>
              {busy ? <Spinner small /> : null} {error ? "Réessayer" : last ? "Vérifier à nouveau" : "Vérifier ma réponse"}
            </button>
          </div>
        </>
      )}

      {last && (
        <div className="top-gap">
          {solved && (
            <p className="muted" dir="auto">
              Ta réponse : {last.answer_text}
            </p>
          )}
          <FeedbackView feedback={last.feedback} score={last.score} lang={lang} />
        </div>
      )}

      {ex.correction && (
        <details className="solution" open={ex.state === "revealed"}>
          <summary>Correction détaillée</summary>
          <ol>
            {ex.correction.etapes.map((e, i) => (
              <li key={i}>
                <Md inline text={e} lang={lang} />
              </li>
            ))}
          </ol>
          {ex.correction.reponse_finale && (
            <div className="callout callout-keep">
              <div className="callout-title">Résultat</div>
              <Md text={ex.correction.reponse_finale} lang={lang} />
            </div>
          )}
          <TrustNote lessonId={lessonId} target={`exercice:${ex.id}`} excerpt={ex.enonce} />
        </details>
      )}
      {ex.state === "revealed" && <p className="muted small">Cet exercice ne compte plus. Un exercice du même type t'attend plus bas pour réessayer la méthode.</p>}

      {confirm && (
        <Modal title="Voir la correction ?" onClose={() => setConfirm(false)}>
          <p>La correction est le dernier recours. Si tu la lis, cet exercice ne comptera plus et je t'en préparerai un autre du même type.</p>
          <div className="row end">
            <button className="btn" onClick={() => setConfirm(false)}>
              Je réessaie encore
            </button>
            <button className="btn btn-ghost" onClick={() => void reveal()}>
              Voir la correction
            </button>
          </div>
        </Modal>
      )}
    </article>
  );
}

const LEVEL_TEXT: Record<string, string> = {
  ex1: "Application directe : une notion à la fois, pour prendre confiance.",
  ex2: "Typique de contrôle : comme les questions de tes devoirs surveillés.",
  ex3: "Difficile : des problèmes de synthèse, pour viser haut.",
};

/** Étape 7 : exercices par niveau. Elle tente d'abord ; la correction vient en dernier recours. */
export default function Exercices({ data, reload }: StepProps) {
  const navigate = useNavigate();
  const lang = data.language;
  const lessonId = data.lesson.id;
  const [exercises, setExercises] = useState<Exercise[]>(data.exercises ?? []);
  const [progress, setProgress] = useState(data.progress ?? { succeeded: 0, required: 2 });
  const [justDone, setJustDone] = useState<{ mastered: boolean } | null>(null);

  useEffect(() => {
    setExercises(data.exercises ?? []);
    if (data.progress) setProgress(data.progress);
  }, [data.exercises, data.progress]);

  usePoll(reload, !!data.variant_pending);

  const replace = (ex: Exercise) => setExercises((list) => list.map((x) => (x.id === ex.id ? ex : x)));
  const onResult = (r: AnswerResult<Exercise>) => {
    replace(r.question);
    if (r.progress) setProgress(r.progress);
    if (r.step_done) setJustDone({ mastered: r.mastered });
  };

  const done = data.status === "done" || justDone !== null;

  return (
    <div>
      <p className="muted">{LEVEL_TEXT[data.step.key]}</p>
      <div className="card level-progress">
        <span>
          <strong>
            {Math.min(progress.succeeded, progress.required)} / {progress.required}
          </strong>{" "}
          exercices réussis pour valider ce niveau
        </span>
        <div className="pips" aria-hidden="true">
          {Array.from({ length: progress.required }, (_, i) => (
            <span key={i} className={i < progress.succeeded ? "pip on" : "pip"} />
          ))}
        </div>
      </div>

      {done && (
        <Notice tone="ok">
          <p>
            <strong>{justDone?.mastered ? "Leçon maîtrisée." : "Niveau validé."}</strong>{" "}
            {justDone?.mastered ? "Tu as réussi jusqu'aux exercices difficiles. Bravo." : "Tu peux continuer, ou t'entraîner encore sur les exercices restants."}
          </p>
          <button className="btn btn-small" onClick={() => navigate(`/lecon/${lessonId}${justDone ? `?valide=${data.step.key}` : ""}`)}>
            {justDone ? "Continuer" : "Retour au parcours"} <Icon name="arrow" />
          </button>
        </Notice>
      )}

      {exercises.map((ex, i) => (
        <ExerciseCard key={ex.id} ex={ex} number={i + 1} lang={lang} lessonId={lessonId} onResult={onResult} onRevealed={(q) => { replace(q); void reload(); }} />
      ))}
      {data.variant_pending && (
        <div className="preparing">
          <Spinner small /> Je prépare un nouvel exercice du même type…
        </div>
      )}
    </div>
  );
}
