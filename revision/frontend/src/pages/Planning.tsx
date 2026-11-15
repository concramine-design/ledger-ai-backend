import { Link } from "react-router-dom";
import { api, type Plan } from "../api";
import { daysLabel, formatDate } from "../components/Editors";
import { Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad } from "../hooks";

/** Planning : à revoir aujourd'hui, les jours suivants, et les contrôles. */
export default function Planning() {
  const { data, error } = useLoad(() => api.get<Plan>("/reviews/plan"), []);
  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  const { today } = data;
  const max = Math.max(1, ...data.upcoming.map((d) => d.count));
  const nothing = today.total_due === 0;

  return (
    <div className="page">
      <h1>Mon planning</h1>

      <section className="card">
        <div className="row between wrap">
          <div>
            <h2 className="flush">À revoir aujourd'hui</h2>
            {nothing ? (
              <p className="muted">Rien à revoir aujourd'hui. {today.waiting > 0 && "Des rappels sont en préparation."}</p>
            ) : (
              <p className="muted">
                {today.size.questions} question{today.size.questions > 1 ? "s" : ""}
                {today.size.cards > 0 && ` et ${today.size.cards} carte${today.size.cards > 1 ? "s" : ""} mémoire`} · environ {today.size.minutes} min
                {today.remaining > 0 && ` · ${today.remaining} de plus pour une deuxième séance`}
              </p>
            )}
          </div>
          {!nothing && (
            <Link className="btn btn-big" to="/revision">
              Commencer <Icon name="arrow" />
            </Link>
          )}
        </div>
        {today.subjects.length > 0 && (
          <ul className="rows">
            {today.subjects.map((s) => (
              <li key={s.subject.id} className="row-item">
                <SubjectChip name={s.subject.name} color={s.subject.color} />
                <span className="grow muted" dir="auto">
                  {s.lessons.join(" · ")}
                </span>
                <span className="muted">
                  {s.count} élément{s.count > 1 ? "s" : ""}
                </span>
              </li>
            ))}
          </ul>
        )}
        {today.subjects.length > 1 && <p className="muted small">La séance mélange les matières : c'est plus efficace que de réviser un seul chapitre d'affilée.</p>}
      </section>

      <section className="card">
        <h2 className="flush">Les 14 prochains jours</h2>
        <ul className="calendar">
          {data.upcoming.map((d, i) => (
            <li key={d.date} className={i === 0 ? "calendar-today" : ""}>
              <span className="calendar-date">{i === 0 ? "Aujourd'hui" : formatDate(d.date)}</span>
              <span className="calendar-bar">
                <span style={{ width: `${(100 * d.count) / max}%` }} />
              </span>
              <span className="calendar-count muted">{d.count || ""}</span>
            </li>
          ))}
        </ul>
        <p className="muted small">Après un rappel réussi, le suivant s'éloigne : 1 jour, puis 3, 7, 14 et 30. Les rappels se resserrent avant un contrôle.</p>
      </section>

      <section className="card">
        <div className="row between">
          <h2 className="flush">Prochains contrôles</h2>
          <Link className="link-btn" to="/reglages">
            Modifier les dates
          </Link>
        </div>
        {data.exams.length === 0 ? (
          <p className="muted">Aucun contrôle enregistré.</p>
        ) : (
          <ul className="rows">
            {data.exams.map((x) => (
              <li key={x.id} className="row-item">
                <span className="grow">
                  <strong>{x.subject_name}</strong>
                  {x.title ? ` — ${x.title}` : ""}
                  <span className="muted"> · {formatDate(x.date)}</span>
                </span>
                <span className="exam-pill">{daysLabel(x.days_left)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <Link className="card link-card" to="/erreurs">
        <span>
          <strong>Carnet d'erreurs</strong>
          <span className="muted">
            {" "}
            · {data.open_mistakes} erreur{data.open_mistakes > 1 ? "s" : ""} à retravailler
          </span>
        </span>
        <Icon name="arrow" />
      </Link>
    </div>
  );
}
