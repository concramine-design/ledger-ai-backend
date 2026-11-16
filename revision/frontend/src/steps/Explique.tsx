import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Talk } from "../api";
import { Md } from "../components/Md";
import { Icon, Notice, Spinner } from "../components/Ui";
import type { StepProps } from "../pages/StepPage";

function Evaluation({ talk, threshold, lang }: { talk: Talk; threshold: number; lang: StepProps["data"]["language"] }) {
  const ev = talk.evaluation!;
  const score = talk.score ?? 0;
  const tone = talk.passed ? "ok" : "warn";
  const criteria = [
    ["Clarté", ev.clarte],
    ["Exactitude", ev.exactitude],
    ["Complétude", ev.completude],
    ["Réponses aux questions", ev.reponses],
  ] as const;
  return (
    <div className={`feedback feedback-${tone}`}>
      <div className="feedback-head">
        <span className={`badge badge-${tone}`}>{talk.passed ? "C'est clair !" : "Presque"}</span>
        <span className="muted">{score} %</span>
      </div>
      <ul className="criteria">
        {criteria.map(([name, note]) => (
          <li key={name}>
            <span className="criteria-name">{name}</span>
            <span className="criteria-dots" aria-label={`${note} sur 4`}>
              {[1, 2, 3, 4].map((n) => (
                <span key={n} className={n <= Math.round(note) ? "pip on" : "pip"} />
              ))}
            </span>
          </li>
        ))}
      </ul>
      {ev.points_clairs && (
        <p>
          <strong className="ok-text">Bien expliqué : </strong>
          <Md inline text={ev.points_clairs} lang={lang} />
        </p>
      )}
      {ev.a_ameliorer && (
        <p>
          <strong className="warn-text">À améliorer : </strong>
          <Md inline text={ev.a_ameliorer} lang={lang} />
        </p>
      )}
      {ev.erreurs.length > 0 && (
        <ul className="plain">
          {ev.erreurs.map((e, i) => (
            <li key={i} className="bad-text">
              <Md inline text={e} lang={lang} />
            </li>
          ))}
        </ul>
      )}
      {!talk.passed && <p className="muted">Il faut {threshold} % pour valider. Reprends ton explication en visant ce qui n'était pas clair.</p>}
    </div>
  );
}

/** Étape 6 : elle explique la leçon avec ses mots ; l'IA joue un élève qui pose des questions, puis évalue. */
export default function Explique({ data, reload }: StepProps) {
  const navigate = useNavigate();
  const lang = data.language;
  const lid = data.lesson.id;
  const talk = data.explique ?? { attempt: 0, messages: [], evaluation: null, score: null, passed: null };
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const started = talk.messages.length > 0;
  const finished = talk.evaluation !== null;

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [talk.messages.length, busy]);

  const send = async () => {
    if (!text.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await api.post(`/lessons/${lid}/steps/explique/message`, { text });
      setText("");
      await reload();
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "Une erreur est survenue."));
    } finally {
      setBusy(false);
    }
  };

  const restart = async () => {
    await api.post(`/lessons/${lid}/steps/explique/restart`);
    setText("");
    await reload();
  };

  return (
    <div>
      {!started && (
        <Notice tone="info">
          Explique cette leçon avec tes mots, comme à un camarade qui ne la connaît pas. Il va te poser des questions. Si tu sais l'expliquer, c'est que tu l'as comprise.
        </Notice>
      )}

      <div className="card talk">
        {talk.messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role === "eleve" ? "user" : "assistant"}`}>
            {m.role === "camarade" && <span className="bubble-who">Ton camarade</span>}
            <Md text={m.content} lang={m.role === "camarade" ? lang : undefined} />
          </div>
        ))}
        {busy && (
          <div className="bubble bubble-assistant">
            <Spinner small />
          </div>
        )}
        <div ref={endRef} />
      </div>

      {finished ? (
        <>
          <Evaluation talk={talk} threshold={data.threshold ?? 60} lang={lang} />
          <div className="row between top-gap">
            {data.status === "done" ? (
              <button className="btn" onClick={() => navigate(`/lecon/${lid}?valide=explique`)}>
                Continuer <Icon name="arrow" />
              </button>
            ) : (
              <button className="btn" onClick={() => void restart()}>
                <Icon name="back" /> Recommencer l'explication
              </button>
            )}
          </div>
        </>
      ) : (
        <form
          className="chat-form card"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <textarea
            className="input"
            dir="auto"
            rows={3}
            value={text}
            placeholder={started ? "Réponds à sa question…" : "Commence ton explication…"}
            onChange={(e) => setText(e.target.value)}
          />
          <button className="btn" disabled={busy || !text.trim()}>
            {started ? "Répondre" : "Expliquer"}
          </button>
        </form>
      )}
      {error && (
        <Notice tone="warn">
          {error.message} {error.retryable && "Ton message est conservé."}
        </Notice>
      )}
    </div>
  );
}
