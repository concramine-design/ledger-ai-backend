import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AnswerResult, type ReviewItem, type ReviewSession, type TestQuestion } from "../api";
import { formatDate } from "../components/Editors";
import { Md } from "../components/Md";
import { Correction, QuestionView } from "../components/Question";
import { Icon, Notice, Progress, Spinner, SubjectChip } from "../components/Ui";
import { useLoad } from "../hooks";

type Step = { item: ReviewItem; question?: TestQuestion };

const KIND_LABEL = { lesson: "Rappel de leçon", error: "Reprise d'une erreur", card: "Carte mémoire" } as const;

function CardStep({ item, onDone }: { item: ReviewItem; onDone: (knew: boolean, next: string | null) => void }) {
  const [shown, setShown] = useState(false);
  const [busy, setBusy] = useState(false);
  const lang = item.lesson.language;
  const answer = async (knew: boolean) => {
    setBusy(true);
    try {
      const r = await api.post<{ next_due: string | null }>(`/reviews/${item.id}/card`, { knew });
      onDone(knew, r.next_due);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flashcard">
      <div className="flashcard-face">
        <Md text={item.card?.recto ?? ""} lang={lang} />
      </div>
      {shown ? (
        <>
          <div className="flashcard-face flashcard-back">
            <Md text={item.card?.verso ?? ""} lang={lang} />
          </div>
          <div className="row center-row">
            <button className="btn btn-ghost" disabled={busy} onClick={() => void answer(false)}>
              Pas encore
            </button>
            <button className="btn" disabled={busy} onClick={() => void answer(true)}>
              Je savais
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="muted">Dis la réponse dans ta tête ou à voix haute, puis vérifie.</p>
          <button className="btn" onClick={() => setShown(true)}>
            Voir la réponse
          </button>
        </>
      )}
    </div>
  );
}

/** Révision du jour : rappels de leçons, erreurs reposées et cartes mémoire, mélangés entre matières. */
export default function Revision() {
  const { data, error, reload } = useLoad(() => api.get<ReviewSession>("/reviews/today"), []);
  const [index, setIndex] = useState(0);
  const [answered, setAnswered] = useState<Record<number, TestQuestion>>({});
  const [results, setResults] = useState<{ ok: number; ko: number }>({ ok: 0, ko: 0 });
  const [nextDates, setNextDates] = useState<string[]>([]);

  const steps: Step[] = useMemo(
    () => (data?.items ?? []).flatMap((item) => (item.kind === "card" ? [{ item }] : (item.questions ?? []).map((question) => ({ item, question })))),
    [data],
  );

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  if (steps.length === 0) {
    return (
      <section className="next card">
        <p className="eyebrow">Révision du jour</p>
        <h1>Rien à revoir aujourd'hui</h1>
        <p className="muted">
          {data.waiting > 0 ? "Des rappels sont en cours de préparation : reviens dans un instant." : "Tes prochains rappels arriveront les jours suivants."}
        </p>
        <Link className="btn" to="/">
          Retour à l'accueil
        </Link>
        <Link className="link-btn" to="/planning">
          Voir mon planning
        </Link>
      </section>
    );
  }

  if (index >= steps.length) {
    const next = nextDates.filter(Boolean).sort()[0];
    return (
      <section className="next card">
        <p className="eyebrow">Révision du jour</p>
        <h1>Séance terminée</h1>
        <p className="next-desc">
          {results.ok} réussi{results.ok > 1 ? "s" : ""}
          {results.ko > 0 && ` · ${results.ko} à revoir demain`}
        </p>
        <p className="muted">
          {results.ko > 0 ? "Ce que tu as raté reviendra demain, sous une autre forme. " : "Bravo, ta mémoire tient bon. "}
          {next && `Prochain rappel : ${formatDate(next)}.`}
        </p>
        {data.remaining > 0 ? (
          <button
            className="btn btn-big"
            onClick={() => {
              setIndex(0);
              setAnswered({});
              setResults({ ok: 0, ko: 0 });
              void reload();
            }}
          >
            Encore une séance ({data.remaining} en attente)
          </button>
        ) : (
          <Link className="btn btn-big" to="/">
            Continuer <Icon name="arrow" />
          </Link>
        )}
      </section>
    );
  }

  const step = steps[index];
  const { item } = step;
  const question = step.question ? (answered[step.question.id] ?? step.question) : undefined;
  const graded = question?.attempt?.status === "graded";

  const onAnswered = (r: AnswerResult<TestQuestion>) => {
    setAnswered((a) => ({ ...a, [r.question.id]: r.question }));
    const good = (r.question.attempt?.score ?? 0) >= 0.7;
    setResults((x) => (good ? { ...x, ok: x.ok + 1 } : { ...x, ko: x.ko + 1 }));
    if (r.review?.next_due) setNextDates((d) => [...d, r.review!.next_due!]);
  };

  return (
    <div className="page">
      <div className="row between">
        <span className="muted">
          {index + 1} sur {steps.length}
        </span>
        <span className="tag">{KIND_LABEL[item.kind]}</span>
      </div>
      <Progress value={(100 * index) / steps.length} />
      <div className="row">
        <SubjectChip name={item.lesson.subject.name} color={item.lesson.subject.color} />
        <span className="muted" dir="auto">
          {item.lesson.title}
        </span>
      </div>
      <div className="card">
        {question ? (
          <>
            <QuestionView key={question.id} q={question} lang={item.lesson.language} onAnswered={onAnswered} />
            {graded && <Correction q={question} lang={item.lesson.language} lessonId={item.lesson.id} />}
          </>
        ) : (
          <CardStep
            key={item.id}
            item={item}
            onDone={(knew, next) => {
              setResults((x) => (knew ? { ...x, ok: x.ok + 1 } : { ...x, ko: x.ko + 1 }));
              if (next) setNextDates((d) => [...d, next]);
              setIndex((i) => i + 1);
            }}
          />
        )}
      </div>
      {graded && (
        <div className="row end">
          <button className="btn" onClick={() => setIndex((i) => i + 1)}>
            {index === steps.length - 1 ? "Terminer la séance" : "Suivant"} <Icon name="arrow" />
          </button>
        </div>
      )}
    </div>
  );
}
