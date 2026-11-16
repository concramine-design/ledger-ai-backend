import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError, type PastExam, type PastExamGroup } from "../api";
import { Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

function ExamCard({ exam, onChange }: { exam: PastExam; onChange: () => void }) {
  return (
    <details className="card mistake">
      <summary>
        <span className="grow" dir="auto">
          {exam.title}
        </span>
        <span className={`badge ${exam.status === "ready" ? "badge-ok" : exam.status === "error" ? "badge-bad" : "badge-muted"}`}>
          {exam.status === "ready" ? "Analysé" : exam.status === "error" ? "À relancer" : "En cours…"}
        </span>
      </summary>
      {exam.status === "error" && (
        <Notice tone="bad">
          <p>{exam.error}</p>
          <button
            className="btn btn-small"
            onClick={async () => {
              await api.post(`/past-exams/${exam.id}/retry`);
              onChange();
            }}
          >
            Réessayer
          </button>
        </Notice>
      )}
      {exam.analysis && (
        <>
          <p className="muted">{exam.analysis.structure}</p>
          <ul className="rows">
            {exam.analysis.types.map((t, i) => (
              <li key={i} className="row-item">
                <span className="grow">
                  <strong>{t.type}</strong>
                  {t.notions && <span className="muted"> — {t.notions}</span>}
                </span>
              </li>
            ))}
          </ul>
          {exam.analysis.style && <p className="muted small">{exam.analysis.style}</p>}
        </>
      )}
      <div className="row end">
        <button className="link-btn danger" onClick={async () => { await api.del(`/past-exams/${exam.id}`); onChange(); }}>
          <Icon name="trash" size={14} /> Supprimer
        </button>
      </div>
    </details>
  );
}

/** Anciens devoirs : importés et analysés ; l'application repère les types de questions qui reviennent. */
export default function Devoirs() {
  const { data, error, reload } = useLoad(() => api.get<PastExamGroup[]>("/past-exams"), []);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const busyAnalysis = !!data?.some((g) => g.exams.some((e) => e.status === "pending"));
  usePoll(reload, busyAnalysis, 3000);

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  const groups = data.filter((g) => g.subject.enabled);
  const current = subjectId ?? groups[0]?.subject.id ?? null;

  const submit = async () => {
    if (current === null) return;
    setBusy(true);
    setErr("");
    const form = new FormData();
    form.append("subject_id", String(current));
    form.append("title", title);
    if (text.trim()) form.append("text", text);
    files.forEach((f) => form.append("files", f));
    try {
      await api.post("/past-exams", form);
      setTitle("");
      setText("");
      setFiles([]);
      await reload();
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <Link className="link-btn" to="/controles">
        <Icon name="back" size={15} /> Contrôles blancs
      </Link>
      <h1>Anciens devoirs surveillés</h1>
      <p className="muted">
        Importe tes devoirs déjà passés : l'application repère les types de questions qui reviennent et les contrôles blancs imiteront le style de ton professeur.
      </p>

      <section className="card form">
        <h2 className="flush">Importer un devoir</h2>
        <div className="grid-2">
          <label className="field">
            <span>Matière</span>
            <select className="input select" value={current ?? ""} onChange={(e) => setSubjectId(Number(e.target.value))}>
              {groups.map((g) => (
                <option key={g.subject.id} value={g.subject.id}>
                  {g.subject.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Titre</span>
            <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="DS n°1, contrôle du 2e semestre…" />
          </label>
        </div>
        <label className="dropzone">
          <input type="file" multiple accept="application/pdf,.pdf,image/*,.heic,.heif" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
          {files.length === 0 ? <span>Photos du devoir ou PDF<small className="muted">Ou colle le texte ci-dessous.</small></span> : <span>{files.map((f) => f.name).join(", ")}</span>}
        </label>
        <textarea className="input" dir="auto" rows={4} value={text} onChange={(e) => setText(e.target.value)} placeholder="…ou colle ici le texte du devoir." />
        {err && <Notice tone="bad">{err}</Notice>}
        <div className="row end">
          <button className="btn" disabled={busy || (!text.trim() && files.length === 0)} onClick={() => void submit()}>
            {busy ? <Spinner small /> : null} Importer et analyser
          </button>
        </div>
      </section>

      {groups.map((g) => (
        <section key={g.subject.id} className="card">
          <div className="row between">
            <h2 className="flush" style={{ color: g.subject.color }}>
              {g.subject.name}
            </h2>
            <SubjectChip name={`${g.exams.length} devoir${g.exams.length > 1 ? "s" : ""}`} color={g.subject.color} />
          </div>
          {g.recurring.length > 0 && (
            <div className="recurring">
              <strong>Questions qui reviennent :</strong>
              <div className="recurring-tags">
                {g.recurring.map((t, i) => (
                  <span key={i} className="recurring-tag">
                    {t.type}
                    {t.count > 1 && <span className="recurring-count">×{t.count}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}
          {g.exams.map((e) => (
            <ExamCard key={e.id} exam={e} onChange={() => void reload()} />
          ))}
          {g.exams.length === 0 && <p className="muted">Aucun devoir importé pour cette matière.</p>}
        </section>
      ))}
    </div>
  );
}
