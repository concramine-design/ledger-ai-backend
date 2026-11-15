import { useState } from "react";
import { api, ApiError, type AnswerResult, type Lang, type TestQuestion } from "../api";
import { AnswerBox, FeedbackView, scoreLabel, scoreTone } from "./Answer";
import { Md } from "./Md";
import { TrustNote } from "./Report";
import { Notice, Spinner } from "./Ui";

/** Correction d'une question : bonne réponse, explication, retour de l'IA. */
export function Correction({ q, lang, lessonId }: { q: TestQuestion; lang: Lang; lessonId: number }) {
  if (!q.attempt || q.attempt.status !== "graded" || !q.correction) return null;
  const score = q.attempt.score;
  return (
    <div className="correction">
      {q.type === "ouverte" ? (
        <>
          <FeedbackView feedback={q.attempt.feedback} score={score} lang={lang} />
          <div className="callout callout-example">
            <div className="callout-title">Réponse attendue</div>
            <Md text={q.correction.reponse_modele} lang={lang} />
          </div>
        </>
      ) : (
        <div className={`feedback feedback-${scoreTone(score)}`}>
          <span className={`badge badge-${scoreTone(score)}`}>{scoreLabel(score)}</span>
          {q.type === "schema" && <span className="muted"> {Math.round((score ?? 0) * 100)} % des cases</span>}
          {q.type === "qcm" && score !== 1 && q.correction.bonne_reponse !== null && (
            <p>
              <strong>Bonne réponse : </strong>
              <Md inline text={q.choix[q.correction.bonne_reponse] ?? ""} lang={lang} />
            </p>
          )}
        </div>
      )}
      {q.correction.explication && (
        <div className="callout callout-keep">
          <div className="callout-title">Explication</div>
          <Md text={q.correction.explication} lang={lang} />
        </div>
      )}
      <TrustNote lessonId={lessonId} target={`question:${q.id}`} excerpt={q.enonce} />
    </div>
  );
}

/** Schéma à légender : des cases numérotées, reliées selon la disposition, dont il faut retrouver le nom. */
function SchemaBoxes({ q, lang, labels, onChange, disabled }: { q: TestQuestion; lang: Lang; labels: string[]; onChange: (l: string[]) => void; disabled: boolean }) {
  const schema = q.schema!;
  const graded = q.attempt?.status === "graded";
  const results = q.attempt?.feedback?.cases ?? [];
  const linked = schema.disposition !== "ensemble";
  return (
    <div className={`schema schema-${schema.disposition}`} dir={lang === "ar" ? "rtl" : "ltr"}>
      {schema.cases.map((c, i) => (
        <div key={i} className="schema-cell">
          <div className={`schema-box ${graded ? (results[i] ? "right" : "wrong") : ""}`}>
            <span className="schema-number">{i + 1}</span>
            <select
              className="input select"
              value={labels[i] ?? ""}
              disabled={disabled}
              aria-label={`Nom de la case ${i + 1}`}
              onChange={(e) => onChange(labels.map((l, j) => (j === i ? e.target.value : l)))}
            >
              <option value="">Choisir…</option>
              {schema.banque.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            {c.role && <Md inline text={c.role} lang={lang} className="schema-role" />}
            {graded && !results[i] && q.correction && <span className="ok-text small">→ {q.correction.noms[i]}</span>}
          </div>
          {linked && i < schema.cases.length - 1 && (
            <span className="schema-arrow" aria-hidden="true">
              →
            </span>
          )}
          {schema.disposition === "cycle" && i === schema.cases.length - 1 && (
            <span className="schema-arrow" aria-hidden="true" title="Retour à la case 1">
              ↺
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

/** Une question (QCM, réponse ouverte ou schéma) avec son bouton de validation. */
export function QuestionView({ q, lang, onAnswered }: { q: TestQuestion; lang: Lang; onAnswered: (r: AnswerResult<TestQuestion>) => void }) {
  const graded = q.attempt?.status === "graded";
  const [text, setText] = useState(q.attempt?.answer_text ?? "");
  const [choice, setChoice] = useState<number | null>(q.attempt?.choice_index ?? null);
  const [labels, setLabels] = useState<string[]>(() => {
    const n = q.schema?.cases.length ?? 0;
    const previous = q.type === "schema" && q.attempt?.answer_text ? q.attempt.answer_text.split(" ; ") : [];
    return Array.from({ length: n }, (_, i) => previous[i] ?? "");
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const body = q.type === "qcm" ? { choice_index: choice } : q.type === "schema" ? { labels } : { answer_text: text };
      onAnswered(await api.post<AnswerResult<TestQuestion>>(`/questions/${q.id}/answer`, body));
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    } finally {
      setBusy(false);
    }
  };

  const incomplete = q.type === "qcm" ? choice === null : q.type === "schema" ? labels.some((l) => !l) : !text.trim();

  return (
    <div className="question">
      <Md text={q.enonce} lang={lang} className="enonce" />
      {q.type === "qcm" && (
        <div className="choices" role="radiogroup" dir={lang === "ar" ? "rtl" : "ltr"}>
          {q.choix.map((c, i) => {
            const isRight = graded && q.correction?.bonne_reponse === i;
            const isWrong = graded && q.attempt?.choice_index === i && !isRight;
            return (
              <button
                key={i}
                type="button"
                role="radio"
                aria-checked={choice === i}
                disabled={graded || busy}
                className={`choice ${choice === i ? "selected" : ""} ${isRight ? "right" : ""} ${isWrong ? "wrong" : ""}`}
                onClick={() => setChoice(i)}
              >
                <span className="choice-letter">{"ABCDEF"[i]}</span>
                <Md inline text={c} lang={lang} />
              </button>
            );
          })}
        </div>
      )}
      {q.type === "schema" && <SchemaBoxes q={q} lang={lang} labels={labels} onChange={setLabels} disabled={graded || busy} />}
      {q.type === "ouverte" && <AnswerBox value={text} onChange={setText} disabled={graded || busy} />}
      {error && (
        <Notice tone="warn">
          {error.message} {error.retryable && "Ta réponse est conservée."}
        </Notice>
      )}
      {!graded && (
        <div className="row end">
          <button className="btn" disabled={busy || incomplete} onClick={() => void submit()}>
            {busy ? <Spinner small /> : null} {error ? "Réessayer" : "Valider ma réponse"}
          </button>
        </div>
      )}
    </div>
  );
}
