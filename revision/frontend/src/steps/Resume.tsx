import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Summary } from "../api";
import { Md } from "../components/Md";
import { TrustNote } from "../components/Report";
import { Icon, Notice } from "../components/Ui";
import type { StepProps } from "../pages/StepPage";

/** Étape 4 : la fiche de référence, exportable en PDF par l'impression du navigateur. */
export default function Resume({ data }: StepProps) {
  const navigate = useNavigate();
  const fiche = data.content as Summary;
  const lang = data.language;
  const dir = lang === "ar" ? "rtl" : "ltr";
  const [error, setError] = useState("");

  const validate = async () => {
    try {
      await api.post(`/lessons/${data.lesson.id}/steps/resume/validate`);
      navigate(`/lecon/${data.lesson.id}?valide=resume`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };

  return (
    <div>
      <article className="card fiche" dir={dir} lang={lang}>
        <header className="fiche-head">
          <p className="eyebrow" dir="ltr">
            Fiche de révision · {data.lesson.subject.name}
          </p>
          <h2>{fiche.titre || data.lesson.title}</h2>
        </header>

        {fiche.definitions.length > 0 && (
          <section>
            <h3 dir="ltr">Définitions</h3>
            <dl>
              {fiche.definitions.map((d, i) => (
                <div key={i} className="def">
                  <dt>
                    <Md inline text={d.terme} lang={lang} />
                  </dt>
                  <dd>
                    <Md inline text={d.definition} lang={lang} />
                  </dd>
                </div>
              ))}
            </dl>
          </section>
        )}

        {fiche.formules.length > 0 && (
          <section>
            <h3 dir="ltr">Formules et propriétés</h3>
            <ul className="formulas">
              {fiche.formules.map((f, i) => (
                <li key={i}>
                  {f.nom && <strong>{f.nom}</strong>}
                  <Md text={f.formule} lang={lang} className="formula" />
                  {f.quand && (
                    <span className="muted">
                      <Md inline text={f.quand} lang={lang} />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {fiche.methodes.length > 0 && (
          <section>
            <h3 dir="ltr">Méthodes</h3>
            {fiche.methodes.map((m, i) => (
              <div key={i} className="method">
                <strong>
                  <Md inline text={m.titre} lang={lang} />
                </strong>
                <ol>
                  {m.etapes.map((e, j) => (
                    <li key={j}>
                      <Md inline text={e} lang={lang} />
                    </li>
                  ))}
                </ol>
              </div>
            ))}
          </section>
        )}

        {fiche.pieges.length > 0 && (
          <section>
            <h3 dir="ltr">Pièges fréquents</h3>
            <ul className="traps">
              {fiche.pieges.map((p, i) => (
                <li key={i}>
                  <strong>
                    <Md inline text={p.piege} lang={lang} />
                  </strong>
                  {p.conseil && (
                    <span>
                      {" "}
                      <Md inline text={p.conseil} lang={lang} />
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        )}

        {fiche.a_savoir_par_coeur.length > 0 && (
          <section>
            <h3 dir="ltr">À savoir par cœur</h3>
            <ul>
              {fiche.a_savoir_par_coeur.map((x, i) => (
                <li key={i}>
                  <Md inline text={x} lang={lang} />
                </li>
              ))}
            </ul>
          </section>
        )}
      </article>

      <TrustNote lessonId={data.lesson.id} target="resume" />
      {error && <Notice tone="bad">{error}</Notice>}
      <div className="row between no-print">
        <button className="btn btn-ghost" onClick={() => window.print()}>
          <Icon name="print" /> Exporter en PDF
        </button>
        {data.status === "current" ? (
          <button className="btn" onClick={() => void validate()}>
            J'ai lu ma fiche, je passe au quiz <Icon name="arrow" />
          </button>
        ) : (
          <button className="btn" onClick={() => navigate(`/lecon/${data.lesson.id}`)}>
            Retour au parcours
          </button>
        )}
      </div>
      <p className="muted no-print small">Pour le PDF : dans la fenêtre d'impression, choisis « Enregistrer au format PDF ».</p>
    </div>
  );
}
