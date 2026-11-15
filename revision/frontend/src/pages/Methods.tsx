import { Link, useParams } from "react-router-dom";
import { api, type MethodsSheet } from "../api";
import { Md } from "../components/Md";
import { Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad } from "../hooks";

/** Fiche « méthodes types » d'un chapitre : reconnaître et résoudre chaque type d'exercice. */
export default function Methods() {
  const { id } = useParams();
  const { data, error } = useLoad(() => api.get<MethodsSheet>(`/chapters/${id}/methods`), [id]);
  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  const lang = data.language;
  return (
    <div className="page">
      <Link className="link-btn no-print" to="/lecons">
        <Icon name="back" size={15} /> Mes leçons
      </Link>
      <div className="row">
        <SubjectChip name={data.subject.name} color={data.subject.color} />
        <span className="muted" dir="auto">
          {data.chapter.title}
        </span>
      </div>
      <div className="row between">
        <h1>Méthodes types</h1>
        <button className="btn btn-ghost no-print" onClick={() => window.print()}>
          <Icon name="print" /> Exporter en PDF
        </button>
      </div>
      {data.lessons.length === 0 && <p className="muted">La fiche se prépare : elle arrive après les exercices de la leçon.</p>}
      {data.lessons.map((lesson) => (
        <section key={lesson.id} className="card fiche" dir={lang === "ar" ? "rtl" : "ltr"}>
          <h2 className="flush" dir="auto">
            {lesson.title}
          </h2>
          {lesson.types.map((t, i) => (
            <article key={i} className="method-type">
              <h3 dir="ltr">
                <Md inline text={t.nom} lang={lang} />
              </h3>
              {t.reconnaitre && (
                <p>
                  <strong>Comment le reconnaître : </strong>
                  <Md inline text={t.reconnaitre} lang={lang} />
                </p>
              )}
              <ol>
                {t.etapes.map((e, j) => (
                  <li key={j}>
                    <Md inline text={e} lang={lang} />
                  </li>
                ))}
              </ol>
              {t.erreur_classique && (
                <p className="trap-line">
                  <strong>Erreur classique : </strong>
                  <Md inline text={t.erreur_classique} lang={lang} />
                </p>
              )}
              {t.exemple && (
                <div className="callout callout-example">
                  <div className="callout-title">Exemple</div>
                  <Md text={t.exemple} lang={lang} />
                </div>
              )}
            </article>
          ))}
        </section>
      ))}
    </div>
  );
}
