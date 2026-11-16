import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type MockExam, type MockPaper, type MockResult, type Subject } from "../api";
import { formatDate } from "../components/Editors";
import { Md } from "../components/Md";
import { GenerationNotice, Icon, Notice, Progress, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

function mmss(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Épreuve en cours : chronomètre, copie sauvegardée régulièrement, remise automatique à la fin du temps. */
function Paper({ mock, onGraded }: { mock: MockExam; onGraded: () => void }) {
  const paper = mock.paper as MockPaper;
  const [answers, setAnswers] = useState<Record<string, string>>(mock.answers ?? {});
  const [remaining, setRemaining] = useState(mock.remaining_seconds ?? mock.duration_min * 60);
  const [busy, setBusy] = useState(false);
  const dirty = useRef(false);
  const submittedRef = useRef(false);

  const submit = async () => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    setBusy(true);
    try {
      await api.post(`/mock-exams/${mock.id}/submit`, { answers });
      onGraded();
    } catch {
      submittedRef.current = false;
      setBusy(false);
    }
  };

  // Chronomètre : remise automatique à zéro.
  useEffect(() => {
    const id = window.setInterval(() => setRemaining((r) => Math.max(0, r - 1)), 1000);
    return () => window.clearInterval(id);
  }, []);
  useEffect(() => {
    if (remaining === 0 && !submittedRef.current) void submit();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remaining]);

  // Sauvegarde régulière de la copie (rien n'est perdu si la page se ferme).
  useEffect(() => {
    const id = window.setInterval(() => {
      if (dirty.current) {
        dirty.current = false;
        void api.put(`/mock-exams/${mock.id}/answers`, { answers }).catch(() => undefined);
      }
    }, 5000);
    return () => window.clearInterval(id);
  }, [answers, mock.id]);

  const set = (numero: string, value: string) => {
    dirty.current = true;
    setAnswers((a) => ({ ...a, [numero]: value }));
  };
  const answered = Object.values(answers).filter((v) => v.trim()).length;
  const total = paper.exercices.reduce((n, ex) => n + ex.questions.length, 0);
  const low = remaining <= 300;

  return (
    <div className="page exam">
      <div className="exam-bar no-print">
        <SubjectChip name={mock.subject.name} color={mock.subject.color} />
        <span className="grow muted">{paper.titre}</span>
        <span className={`exam-timer ${low ? "exam-timer-low" : ""}`}>
          <Icon name="clock" size={16} /> {mmss(remaining)}
        </span>
      </div>
      <Progress value={(100 * answered) / total} />
      {paper.exercices.map((ex, i) => (
        <section key={i} className="card">
          <h2 className="flush">
            {ex.titre || `Exercice ${i + 1}`}
            <span className="muted"> · {ex.questions.reduce((n, q) => n + q.points, 0)} pts</span>
          </h2>
          {ex.contexte && (
            <div className="document">
              <Md text={ex.contexte} lang={mock.language} />
            </div>
          )}
          {ex.questions.map((q) => (
            <div key={q.numero} className="exam-question">
              <div className="exam-question-head">
                <strong>{q.numero}.</strong>
                <Md inline text={q.enonce} lang={mock.language} />
                <span className="muted">({q.points} pt{q.points > 1 ? "s" : ""})</span>
              </div>
              <textarea
                className="input"
                dir="auto"
                rows={3}
                value={answers[q.numero] ?? ""}
                onChange={(e) => set(q.numero, e.target.value)}
                placeholder="Ta réponse…"
              />
            </div>
          ))}
        </section>
      ))}
      <div className="row between no-print">
        <span className="muted">
          {answered} / {total} question{total > 1 ? "s" : ""} traitée{answered > 1 ? "s" : ""}
        </span>
        <button
          className="btn btn-big"
          disabled={busy}
          onClick={() => {
            if (window.confirm("Rendre ta copie et voir ta note ?")) void submit();
          }}
        >
          {busy ? <Spinner small /> : null} Rendre ma copie
        </button>
      </div>
    </div>
  );
}

function Result({ mock }: { mock: MockExam }) {
  const result = mock.result as MockResult;
  const paper = mock.paper as MockPaper;
  const tone = result.note >= 10 ? "ok" : result.note >= 7 ? "warn" : "bad";
  const corrections = new Map(result.questions.map((q) => [q.numero, q]));
  return (
    <div className="page">
      <Link className="link-btn no-print" to="/controles">
        <Icon name="back" size={15} /> Contrôles blancs
      </Link>
      <div className="card result">
        <div className={`result-score ${tone === "ok" ? "ok-text" : tone === "warn" ? "warn-text" : "bad-text"}`}>
          {result.note}/20
        </div>
        <h2>{paper.titre}</h2>
      </div>

      <section className="card">
        <h2 className="flush">Points à retravailler</h2>
        {result.bilan.map((b, i) => (
          <div key={i} className="bilan-row">
            <span className="grow">
              {b.lesson_id ? (
                <Link to={`/lecon/${b.lesson_id}`} dir="auto">
                  {b.lecon}
                </Link>
              ) : (
                <span dir="auto">{b.lecon}</span>
              )}
              {b.notions.length > 0 && <span className="muted"> — {b.notions.join(", ")}</span>}
            </span>
            <span className="bilan-bar">
              <Progress value={b.taux} tone={b.taux >= 75 ? "ok" : undefined} />
            </span>
            <span className="muted">{b.taux} %</span>
          </div>
        ))}
      </section>

      {paper.exercices.map((ex, i) => (
        <section key={i} className="card">
          <h2 className="flush">{ex.titre || `Exercice ${i + 1}`}</h2>
          {ex.questions.map((q) => {
            const c = corrections.get(q.numero);
            if (!c) return null;
            const qtone = c.note >= 0.999 * q.points ? "ok" : c.note > 0 ? "warn" : "bad";
            return (
              <details key={q.numero} className="exam-review" open={c.note < q.points}>
                <summary>
                  <span className={`badge badge-${qtone}`}>
                    {c.note}/{q.points}
                  </span>
                  <span>Question {q.numero}</span>
                </summary>
                <Md text={q.enonce} lang={mock.language} className="enonce" />
                <p className="muted" dir="auto">
                  Ta réponse : {mock.answers[q.numero] || "(rien)"}
                </p>
                {c.commentaire && (
                  <p>
                    <Md inline text={c.commentaire} lang={mock.language} />
                  </p>
                )}
                {q.correction && (
                  <div className="callout callout-keep">
                    <div className="callout-title">Corrigé</div>
                    <Md text={q.correction} lang={mock.language} />
                  </div>
                )}
              </details>
            );
          })}
        </section>
      ))}
    </div>
  );
}

/** Un contrôle blanc : préparation, salle d'attente avant le départ, épreuve, résultat. */
export default function ControleBlanc() {
  const { id } = useParams();
  const { data, error, reload } = useLoad(() => api.get<MockExam>(`/mock-exams/${id}`), [id]);
  usePoll(reload, !!data && (data.status === "pending" || (data.status === "ready" && !data.paper)));

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  if (data.status === "graded") return <Result mock={data} />;
  if (data.status === "started" && data.paper) return <Paper mock={data} onGraded={() => void reload()} />;

  return (
    <div className="page">
      <Link className="link-btn" to="/controles">
        <Icon name="back" size={15} /> Contrôles blancs
      </Link>
      <section className="next card">
        <p className="eyebrow">Contrôle blanc</p>
        <div className="row center-row">
          <SubjectChip name={data.subject.name} color={data.subject.color} />
        </div>
        <h1>Prête pour l'épreuve ?</h1>
        <p className="muted">
          {data.duration_min} minutes · noté sur 20 · {data.lessons.length} leçon{data.lessons.length > 1 ? "s" : ""} au programme
          {data.summary && ` · ${data.summary.questions} questions`}
        </p>
        <p className="next-desc">Une fois commencé, le chronomètre tourne. Installe-toi au calme, comme pour un vrai devoir surveillé.</p>
        {data.status === "ready" && data.summary ? (
          <button
            className="btn btn-big"
            onClick={async () => {
              await api.post(`/mock-exams/${data.id}/start`);
              await reload();
            }}
          >
            Commencer l'épreuve <Icon name="arrow" />
          </button>
        ) : data.status === "error" ? (
          <Notice tone="bad">
            <p>{data.error}</p>
            <button
              className="btn btn-small"
              onClick={async () => {
                await api.post(`/mock-exams/${data.id}/retry`);
                await reload();
              }}
            >
              Réessayer
            </button>
          </Notice>
        ) : (
          <GenerationNotice lessonId={0} generation={{ total: 1, done: 0, active: true, current: "Préparation du sujet", problem: null }} />
        )}
      </section>
    </div>
  );
}

export function ControlesList() {
  const navigate = useNavigate();
  const subjects = useLoad(() => api.get<Subject[]>("/subjects"), []);
  const mocks = useLoad(() => api.get<MockExam[]>("/mock-exams"), []);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [duration, setDuration] = useState(60);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const active = (subjects.data ?? []).filter((s) => s.enabled);

  const create = async () => {
    setBusy(true);
    setErr("");
    try {
      const mock = await api.post<MockExam>("/mock-exams", { subject_id: subjectId ?? active[0]?.id, duration_min: duration });
      navigate(`/controle/${mock.id}`);
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Erreur");
      setBusy(false);
    }
  };

  if (!subjects.data || !mocks.data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="page">
      <h1>Contrôle blanc</h1>
      <p className="muted">Une épreuve chronométrée au format d'un devoir surveillé, notée sur 20, avec le bilan de ce qu'il faut retravailler. Idéal quelques jours avant un contrôle.</p>

      <section className="card form">
        <h2 className="flush">Nouveau contrôle blanc</h2>
        <div className="row wrap">
          <label className="field">
            <span>Matière</span>
            <select className="input select" value={subjectId ?? active[0]?.id} onChange={(e) => setSubjectId(Number(e.target.value))}>
              {active.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Durée</span>
            <select className="input select" value={duration} onChange={(e) => setDuration(Number(e.target.value))}>
              {[30, 45, 60, 90, 120].map((m) => (
                <option key={m} value={m}>
                  {m} minutes
                </option>
              ))}
            </select>
          </label>
          <button className="btn" disabled={busy || active.length === 0} onClick={() => void create()}>
            {busy ? <Spinner small /> : null} Préparer le sujet
          </button>
        </div>
        <p className="muted small">Le sujet porte sur toutes les leçons importées de la matière. Si tu as importé d'anciens devoirs, il imite le style de ton professeur.</p>
        {err && <Notice tone="bad">{err}</Notice>}
      </section>

      {mocks.data.length > 0 && (
        <section className="card">
          <h2 className="flush">Mes contrôles blancs</h2>
          <ul className="rows">
            {mocks.data.map((m) => (
              <li key={m.id} className="row-item">
                <SubjectChip name={m.subject.name} color={m.subject.color} />
                <span className="grow muted">{formatDate(m.created_at)}</span>
                {m.status === "graded" && m.result ? (
                  <span className={`badge ${m.result.note >= 10 ? "badge-ok" : "badge-warn"}`}>{m.result.note}/20</span>
                ) : (
                  <span className="muted">{m.status === "error" ? "à relancer" : m.status === "started" ? "en cours" : "prêt"}</span>
                )}
                <Link className="link-btn" to={`/controle/${m.id}`}>
                  {m.status === "graded" ? "Revoir" : "Ouvrir"}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Link className="card link-card" to="/anciens-devoirs">
        <span>
          <strong>Anciens devoirs surveillés</strong>
          <span className="muted"> · importe-les pour un contrôle blanc dans le style de ton professeur</span>
        </span>
        <Icon name="arrow" />
      </Link>
    </div>
  );
}
