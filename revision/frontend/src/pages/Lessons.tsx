import { Link } from "react-router-dom";
import { api, type Exam, type Lesson, type Subject } from "../api";
import { daysLabel } from "../components/Editors";
import { Icon, Notice, Spinner } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

interface Group {
  subject: Subject;
  exam: Exam | null;
  chapters: { id: number; title: string; lessons: Lesson[] }[];
}

const COLOR_CLASS = { vert: "m-vert", orange: "m-orange", rouge: "m-rouge" } as const;

function status(lesson: Lesson): string {
  if (lesson.mastered) return "Maîtrisée";
  if (lesson.generation.problem?.fatal) return "À relancer";
  if (lesson.generation.active && lesson.progress === 0) return "En préparation…";
  return lesson.current_step ? `Étape : ${lesson.current_step.label}` : "";
}

function chapterColor(lessons: Lesson[]): "rouge" | "orange" | "vert" {
  const avg = lessons.reduce((n, l) => n + l.mastery, 0) / lessons.length;
  return avg >= 75 ? "vert" : avg >= 40 ? "orange" : "rouge";
}

/** Toutes les leçons, par matière et par chapitre. */
export default function Lessons() {
  const { data, error, reload } = useLoad(() => api.get<Group[]>("/lessons"), []);
  const busy = !!data?.some((g) => g.chapters.some((c) => c.lessons.some((l) => l.generation.active)));
  usePoll(reload, busy, 4000);

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  const groups = data.filter((g) => g.chapters.length > 0);

  return (
    <div className="page">
      <div className="row between">
        <h1>Mes leçons</h1>
        <Link className="btn" to="/importer">
          <Icon name="plus" /> Importer une leçon
        </Link>
      </div>
      {groups.length === 0 && <p className="muted">Aucune leçon pour l'instant. Importe la première pour commencer.</p>}
      {groups.map((g) => (
        <section key={g.subject.id} className="card subject-card">
          <div className="row between">
            <h2 style={{ color: g.subject.color }}>{g.subject.name}</h2>
            {g.exam && <span className="exam-pill">Contrôle {daysLabel(g.exam.days_left)}</span>}
          </div>
          {g.chapters.map((c) => (
            <div key={c.id} className="chapter">
              <h3 dir="auto">
                <span className={`chapter-dot ${COLOR_CLASS[chapterColor(c.lessons)]}`} aria-hidden="true" />
                {c.title}
              </h3>
              <ul className="rows">
                {c.lessons.map((l) => (
                  <li key={l.id}>
                    <Link className="lesson-row" to={`/lecon/${l.id}`}>
                      <span className="grow" dir="auto">
                        {l.title}
                      </span>
                      <span className={`muted status ${l.mastered ? "ok-text" : ""}`}>{status(l)}</span>
                      <span className={`mastery-pill ${COLOR_CLASS[l.color]}`} title="Score de maîtrise">
                        {l.mastery} %
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </section>
      ))}
    </div>
  );
}
