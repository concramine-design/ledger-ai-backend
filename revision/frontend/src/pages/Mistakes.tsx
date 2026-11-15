import { Link } from "react-router-dom";
import { api, type MistakeEntry } from "../api";
import { formatDate } from "../components/Editors";
import { Md } from "../components/Md";
import { Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad } from "../hooks";

const SOURCES: Record<string, string> = { minitest: "Mini-test", quiz: "Quiz", exercice: "Exercice", rappel: "Rappel" };

function Entry({ m }: { m: MistakeEntry }) {
  const lang = m.lesson.language;
  return (
    <details className={`card mistake ${m.resolved ? "mistake-resolved" : ""}`}>
      <summary>
        <SubjectChip name={m.lesson.subject.name} color={m.lesson.subject.color} />
        <span className="grow" dir="auto">
          {m.notion || m.lesson.title}
        </span>
        <span className={`badge ${m.resolved ? "badge-ok" : "badge-warn"}`}>
          {m.resolved ? "Résolue" : m.next_due ? `Reposée ${formatDate(m.next_due)}` : "En cours"}
        </span>
      </summary>
      <p className="muted small">
        {SOURCES[m.source] ?? m.source} du {formatDate(m.created_at)} ·{" "}
        <Link to={`/lecon/${m.lesson.id}`} dir="auto">
          {m.lesson.title}
        </Link>
      </p>
      <Md text={m.enonce} lang={lang} className="enonce" />
      <p className="muted" dir="auto">
        Ta réponse : {m.given || "(aucune)"}
      </p>
      <div className="callout callout-keep">
        <div className="callout-title">Réponse attendue</div>
        <Md text={m.expected} lang={lang} />
      </div>
      {!m.resolved && <p className="muted small">Elle te sera reposée sous une autre forme. Deux réussites de suite, et elle sort du carnet ({m.successes}/2).</p>}
    </details>
  );
}

/** Carnet d'erreurs : chaque erreur est gardée, puis reposée plus tard sous une autre forme. */
export default function Mistakes() {
  const { data, error } = useLoad(() => api.get<MistakeEntry[]>("/mistakes"), []);
  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  const open = data.filter((m) => !m.resolved);
  const resolved = data.filter((m) => m.resolved);
  return (
    <div className="page">
      <h1>Carnet d'erreurs</h1>
      <p className="muted">Se tromper sert à apprendre : chaque erreur est notée ici, puis reposée plus tard sous une autre forme.</p>
      {data.length === 0 && <p className="muted">Aucune erreur pour l'instant.</p>}
      {open.length > 0 && <h2>À retravailler ({open.length})</h2>}
      {open.map((m) => (
        <Entry key={m.id} m={m} />
      ))}
      {resolved.length > 0 && <h2>Résolues ({resolved.length})</h2>}
      {resolved.map((m) => (
        <Entry key={m.id} m={m} />
      ))}
    </div>
  );
}
