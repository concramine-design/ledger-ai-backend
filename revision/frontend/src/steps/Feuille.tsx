import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type FeuilleResult, type FeuilleSubmission } from "../api";
import { AnswerBox } from "../components/Answer";
import { Md } from "../components/Md";
import { Icon, Notice, Spinner } from "../components/Ui";
import type { StepProps } from "../pages/StepPage";

const MARK = { ok: "✓", partiel: "~", absent: "✗" } as const;
const LABEL = { ok: "Retrouvé", partiel: "Incomplet", absent: "Oublié" } as const;

function Comparison({ result, coverage, threshold, lang }: { result: FeuilleResult; coverage: number; threshold: number; lang: StepProps["data"]["language"] }) {
  const tone = coverage >= threshold ? "ok" : coverage >= threshold / 2 ? "warn" : "bad";
  return (
    <div className="card">
      <div className="row between wrap">
        <h2 className="flush">Ce que tu as retrouvé</h2>
        <span className={`badge badge-${tone}`}>{coverage} % de la leçon</span>
      </div>
      {result.message && <Md text={result.message} lang={lang} className="muted" />}
      <ul className="elements">
        {result.points.map((p, i) => (
          <li key={i} className={`element element-${p.etat}`}>
            <span className="element-mark" title={LABEL[p.etat]}>
              {MARK[p.etat]}
            </span>
            <span>
              <Md inline text={p.point} lang={lang} />
              {p.etat !== "ok" && p.rappel && (
                <span className="muted"> — <Md inline text={p.rappel} lang={lang} /></span>
              )}
            </span>
          </li>
        ))}
      </ul>
      {result.erreurs.length > 0 && (
        <div className="faults">
          <strong className="bad-text">À corriger :</strong>
          <ul className="plain">
            {result.erreurs.map((e, i) => (
              <li key={i} className="fault">
                {e.extrait && <q className="fault-quote" dir="auto">{e.extrait}</q>}
                <div>
                  <Md inline text={e.correction} lang={lang} />
                </div>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Étape 3 : elle écrit de mémoire ; l'application compare avec la leçon et signale oublis et erreurs. */
export default function Feuille({ data, reload }: StepProps) {
  const navigate = useNavigate();
  const lang = data.language;
  const lid = data.lesson.id;
  const submissions = data.feuille?.submissions ?? [];
  const last: FeuilleSubmission | undefined = submissions[submissions.length - 1];
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [writing, setWriting] = useState(!last || data.status === "current");

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ passed: boolean }>(`/lessons/${lid}/steps/feuille/submit`, { text });
      await reload();
      setWriting(false);
      if (result.passed) setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    } finally {
      setBusy(false);
    }
  };

  const done = data.status === "done";

  return (
    <div>
      {!last && (
        <Notice tone="info">
          Ferme ton cahier. Écris tout ce que tu as retenu de la leçon, avec tes mots, même en désordre. Se tester de mémoire est la meilleure façon d'ancrer une leçon.
        </Notice>
      )}

      {writing ? (
        <div className="card">
          <AnswerBox
            value={text}
            onChange={setText}
            disabled={busy}
            rows={12}
            symbols={data.kind === "sciences"}
            placeholder="Écris de mémoire tout ce dont tu te souviens…"
          />
          {error && (
            <Notice tone="warn">
              {error.message} {error.retryable && "Ton texte est conservé."}
            </Notice>
          )}
          <div className="row end">
            {last && (
              <button className="btn btn-ghost" onClick={() => setWriting(false)} disabled={busy}>
                Annuler
              </button>
            )}
            <button className="btn" disabled={busy || text.trim().split(/\s+/).length < 15} onClick={() => void submit()}>
              {busy ? <Spinner small /> : null} Comparer avec la leçon
            </button>
          </div>
        </div>
      ) : (
        last && <Comparison result={last.result} coverage={last.coverage} threshold={data.threshold ?? 50} lang={lang} />
      )}

      {last && !writing && (
        <div className="row between top-gap">
          {done ? (
            <button className="btn" onClick={() => navigate(`/lecon/${lid}`)}>
              Retour au parcours
            </button>
          ) : (
            <>
              <button className="btn btn-ghost" onClick={() => setWriting(true)}>
                <Icon name="back" /> Réessayer de mémoire
              </button>
              <span className="muted">Il faut retrouver {data.threshold} % de la leçon pour valider.</span>
            </>
          )}
        </div>
      )}
      {done && !writing && (
        <Notice tone="ok">
          Étape validée : tu as retrouvé {last?.coverage} % de la leçon de mémoire.{" "}
          <button className="link-btn" onClick={() => navigate(`/lecon/${lid}?valide=feuille`)}>
            Continuer
          </button>
        </Notice>
      )}
    </div>
  );
}
