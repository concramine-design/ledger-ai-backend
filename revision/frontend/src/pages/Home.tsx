import { Link } from "react-router-dom";
import { api, type Activity, type NextStep } from "../api";
import { daysLabel, formatDate } from "../components/Editors";
import { GenerationNotice, Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

function StreakRewards() {
  const { data } = useLoad(() => api.get<Activity>("/activity"), []);
  if (!data) return null;
  const earned = data.rewards.filter((r) => r.earned);
  const active = data.history.filter((d) => d.actions + d.pomodoros > 0).length;
  return (
    <div className="streak-row">
      <div className="streak">
        <span className="streak-flame">🔥</span>
        <div>
          <strong>
            {data.streak} jour{data.streak > 1 ? "s" : ""} de suite
          </strong>
          <span className="muted"> · {active} jours actifs sur 14</span>
        </div>
      </div>
      {earned.length > 0 && (
        <div className="rewards" title="Tes récompenses">
          {earned.slice(-5).map((r) => (
            <span key={r.key} className="reward" title={`${r.label} — ${r.description}`}>
              <Icon name="star" size={14} /> {r.label}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Écran d'accueil : une seule chose, « Ta prochaine étape ». */
export default function Home() {
  const { data, error, reload } = useLoad(() => api.get<NextStep>("/next"), []);
  usePoll(reload, data?.kind === "step" && !data.ready);

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  if (data.kind === "import") {
    return (
      <>
        <StreakRewards />
        <section className="next card">
        <p className="eyebrow">Ta prochaine étape</p>
        <h1>Importe ta première leçon</h1>
        <p className="muted">Un PDF, des photos de ton cahier ou le texte collé. Je prépare tout le reste.</p>
        <Link className="btn btn-big" to="/importer">
          Importer une leçon <Icon name="arrow" />
        </Link>
        </section>
      </>
    );
  }

  if (data.kind === "review") {
    const { size } = data;
    void StreakRewards;
    const parts = [
      size.questions ? `${size.questions} question${size.questions > 1 ? "s" : ""}` : "",
      size.cards ? `${size.cards} carte${size.cards > 1 ? "s" : ""} mémoire` : "",
    ].filter(Boolean);
    return (
      <>
        <StreakRewards />
        <section className="next card">
        <p className="eyebrow">Ta prochaine étape</p>
        <p className="muted">{data.subjects.join(" · ")}</p>
        <h1>Révision du jour</h1>
        <p className="next-desc">{parts.join(" et ")} à revoir aujourd'hui, pour ne pas oublier.</p>
        <p className="muted row center-row">
          <Icon name="clock" size={16} /> environ {size.minutes} min
        </p>
        <Link className="btn btn-big" to="/revision">
          Continuer <Icon name="arrow" />
        </Link>
        <Link className="link-btn" to="/planning">
          Voir mon planning
        </Link>
        </section>
      </>
    );
  }

  if (data.kind === "done") {
    return (
      <>
        <StreakRewards />
        <section className="next card">
        <p className="eyebrow">Ta prochaine étape</p>
        <h1>Tout est maîtrisé</h1>
        <p className="muted">
          Tu as maîtrisé {data.mastered} leçon{data.mastered > 1 ? "s" : ""}. Importe la leçon suivante pour continuer.
          {data.next_review && ` Prochain rappel : ${formatDate(data.next_review)}.`}
        </p>
        <Link className="btn btn-big" to="/importer">
          Importer une leçon <Icon name="arrow" />
        </Link>
        </section>
      </>
    );
  }

  const { lesson, step, exam } = data;
  return (
    <>
      <StreakRewards />
      <section className="next card">
      <p className="eyebrow">Ta prochaine étape</p>
      <div className="row center-row">
        <SubjectChip name={lesson.subject.name} color={lesson.subject.color} />
        <span className="muted">{lesson.title}</span>
      </div>
      <h1>{step.label}</h1>
      <p className="next-desc">{step.description}</p>
      <p className="muted row center-row">
        <Icon name="clock" size={16} /> environ {step.minutes} min
        {exam && <span className="exam-pill">Contrôle {daysLabel(exam.days_left)}</span>}
      </p>
      {data.ready ? (
        <Link className="btn btn-big" to={`/lecon/${lesson.id}/${step.key}`}>
          Continuer <Icon name="arrow" />
        </Link>
      ) : (
        <>
          <button className="btn btn-big" disabled>
            Continuer <Icon name="arrow" />
          </button>
          <GenerationNotice lessonId={lesson.id} generation={data.generation} onRetried={() => void reload()} />
        </>
      )}
      <Link className="link-btn" to={`/lecon/${lesson.id}`}>
        Voir le parcours de cette leçon
      </Link>
      </section>
    </>
  );
}
