import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import type { AnswerResult, Lang, SetResult, TestQuestion, TestSet } from "../api";
import { scoreLabel, scoreTone } from "../components/Answer";
import { Md } from "../components/Md";
import { Correction, QuestionView } from "../components/Question";
import { TrustNote } from "../components/Report";
import { Icon, Notice, Progress, Spinner } from "../components/Ui";
import { usePoll } from "../hooks";
import type { StepProps } from "../pages/StepPage";

function Review({ set, lang, lessonId }: { set: TestSet; lang: Lang; lessonId: number }) {
  return (
    <div className="review">
      {set.questions.map((q, i) => (
        <details key={q.id} className="card review-item" open={(q.attempt?.score ?? 0) < 0.999}>
          <summary>
            <span className={`badge badge-${scoreTone(q.attempt?.score)}`}>{scoreLabel(q.attempt?.score)}</span>
            <span>Question {i + 1}</span>
          </summary>
          <Md text={q.enonce} lang={lang} className="enonce" />
          {q.type === "ouverte" && q.attempt?.answer_text && (
            <p className="muted" dir="auto">
              Ta réponse : {q.attempt.answer_text}
            </p>
          )}
          {q.type === "schema" && q.attempt?.answer_text && (
            <p className="muted" dir="auto">
              Ta légende : {q.attempt.answer_text}
            </p>
          )}
          {q.type === "qcm" && q.attempt?.choice_index != null && (
            <p className="muted">
              Ta réponse : <Md inline text={q.choix[q.attempt.choice_index] ?? ""} lang={lang} />
            </p>
          )}
          <Correction q={q} lang={lang} lessonId={lessonId} />
        </details>
      ))}
    </div>
  );
}

/** Étapes 2 et 5 : mini-test et quiz complet. Une question à la fois, retour immédiat. */
export default function TestStep({ data, reload }: StepProps) {
  const navigate = useNavigate();
  const lang = data.language;
  const lessonId = data.lesson.id;
  const isQuiz = data.step.key === "quiz";
  const name = isQuiz ? "quiz" : "mini-test";

  const [questions, setQuestions] = useState<TestQuestion[]>(data.set?.questions ?? []);
  const [index, setIndex] = useState(0);
  const [pending, setPending] = useState<SetResult | null>(null);
  const [result, setResult] = useState<SetResult | null>(null);
  const [reviewSeen, setReviewSeen] = useState(false);

  // Nouveau test (ou premier affichage) : on repart de la première question sans réponse.
  useEffect(() => {
    const qs = data.set?.questions ?? [];
    setQuestions(qs);
    const firstOpen = qs.findIndex((q) => q.attempt?.status !== "graded");
    setIndex(firstOpen === -1 ? 0 : firstOpen);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.set?.id]);

  // Le résultat s'affiche en haut de page, pas là où elle avait fait défiler la dernière question.
  useEffect(() => {
    if (result) window.scrollTo(0, 0);
  }, [result]);

  const previous = data.previous ?? null;
  const started = questions.some((q) => q.attempt?.status === "graded");
  const failedView = (result && !result.passed) || (!data.set && !!previous) || (!!previous && !started && !reviewSeen);
  usePoll(reload, data.status === "current" && failedView && (!data.set || !previous?.reexplain));

  // Le résultat qu'elle vient d'obtenir passe avant la relecture d'une étape déjà validée.
  if (result?.passed) {
    return (
      <div className="card result">
        <div className="result-score ok-text">{result.score} %</div>
        <h2>{isQuiz ? "Quiz réussi" : "Mini-test réussi"}</h2>
        <p className="muted">
          Il fallait {result.threshold} %. {isQuiz ? "Les exercices sont débloqués." : "Ta fiche de résumé est débloquée."}
        </p>
        <button className="btn btn-big" onClick={() => navigate(`/lecon/${lessonId}?valide=${data.step.key}`)}>
          Continuer <Icon name="arrow" />
        </button>
      </div>
    );
  }

  if (data.status === "done" && data.set) {
    return (
      <div>
        <Notice tone="ok">
          Étape validée avec {data.set.score} %. Tu peux relire tes réponses et les corrections.
        </Notice>
        <Review set={data.set} lang={lang} lessonId={lessonId} />
        <div className="row end">
          <button className="btn" onClick={() => navigate(`/lecon/${lessonId}`)}>
            Retour au parcours
          </button>
        </div>
      </div>
    );
  }

  if (failedView && previous) {
    return (
      <div>
        <div className="card result">
          <div className="result-score warn-text">{previous.score} %</div>
          <h2>Pas encore : on reprend les points ratés</h2>
          <p className="muted">
            Il faut {data.threshold} % pour valider. Se tromper fait partie de l'apprentissage : lis la nouvelle explication, puis refais un {name}.
          </p>
        </div>

        <h2>Autrement dit</h2>
        {previous.reexplain ? (
          previous.reexplain.points.map((p, i) => (
            <article key={i} className="card lesson-card">
              {p.notion && <h3 dir={lang === "ar" ? "rtl" : "ltr"}>{p.notion}</h3>}
              {p.ce_qui_a_coince && (
                <p className="muted">
                  <Md inline text={p.ce_qui_a_coince} lang={lang} />
                </p>
              )}
              <Md text={p.explication} lang={lang} />
              {p.exemple && (
                <div className="callout callout-example">
                  <div className="callout-title">Exemple</div>
                  <Md text={p.exemple} lang={lang} />
                </div>
              )}
              {p.astuce && (
                <div className="callout callout-keep">
                  <div className="callout-title">Astuce</div>
                  <Md text={p.astuce} lang={lang} />
                </div>
              )}
              <TrustNote lessonId={lessonId} target={`reexplication:${previous.id}:${i + 1}`} excerpt={p.explication} />
            </article>
          ))
        ) : (
          <div className="preparing">
            <Spinner small /> Je prépare une nouvelle explication des points ratés…
          </div>
        )}

        <h2>Tes réponses</h2>
        <Review set={previous} lang={lang} lessonId={lessonId} />

        <div className="row end">
          {data.set ? (
            <button
              className="btn btn-big"
              onClick={() => {
                setReviewSeen(true);
                setResult(null);
                setPending(null);
                window.scrollTo(0, 0);
              }}
            >
              Passer le nouveau {name} <Icon name="arrow" />
            </button>
          ) : (
            <span className="preparing">
              <Spinner small /> Je prépare un nouveau {name}…
            </span>
          )}
        </div>
      </div>
    );
  }

  const q = questions[index];
  if (!q) return null;
  const graded = q.attempt?.status === "graded";
  const isLast = index === questions.length - 1;
  const answered = questions.filter((x) => x.attempt?.status === "graded").length;

  const onAnswered = (r: AnswerResult<TestQuestion>) => {
    setQuestions((qs) => qs.map((x) => (x.id === r.question.id ? r.question : x)));
    if (r.set) setPending(r.set);
  };

  return (
    <div>
      <div className="row between">
        <span className="muted">
          Question {index + 1} sur {questions.length}
        </span>
        <span className="muted">Objectif : {data.threshold} %</span>
      </div>
      <Progress value={(100 * answered) / questions.length} />
      <div className="card">
        <QuestionView key={q.id} q={q} lang={lang} onAnswered={onAnswered} />
        {graded && <Correction q={q} lang={lang} lessonId={lessonId} />}
      </div>
      {graded && (
        <div className="row end">
          {!isLast ? (
            <button className="btn" onClick={() => setIndex((i) => i + 1)}>
              Question suivante <Icon name="arrow" />
            </button>
          ) : (
            <button
              className="btn"
              onClick={() => {
                setResult(pending);
                void reload();
              }}
              disabled={!pending}
            >
              Voir mon résultat <Icon name="arrow" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
