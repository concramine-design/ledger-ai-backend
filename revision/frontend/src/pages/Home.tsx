import { Link } from "react-router-dom";
import { api, type NextStep } from "../api";
import { daysLabel } from "../components/Editors";
import { GenerationNotice, Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

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
      <section className="next card">
        <p className="eyebrow">Ta prochaine étape</p>
        <h1>Importe ta première leçon</h1>
        <p className="muted">Un PDF, des photos de ton cahier ou le texte collé. Je prépare tout le reste.</p>
        <Link className="btn btn-big" to="/importer">
          Importer une leçon <Icon name="arrow" />
        </Link>
      </section>
    );
  }

  if (data.kind === "done") {
    return (
      <section className="next card">
        <p className="eyebrow">Ta prochaine étape</p>
        <h1>Tout est maîtrisé</h1>
        <p className="muted">
          Tu as maîtrisé {data.mastered} leçon{data.mastered > 1 ? "s" : ""}. Importe la leçon suivante pour continuer.
        </p>
        <Link className="btn btn-big" to="/importer">
          Importer une leçon <Icon name="arrow" />
        </Link>
      </section>
    );
  }

  const { lesson, step, exam } = data;
  return (
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
  );
}
