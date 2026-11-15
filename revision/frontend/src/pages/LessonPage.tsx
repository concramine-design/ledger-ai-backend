import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, ApiError, type Lesson, type PathStep } from "../api";
import { daysLabel } from "../components/Editors";
import { GenerationNotice, Icon, Modal, Notice, Progress, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";

function StepRow({ step, lessonId, ready }: { step: PathStep; lessonId: number; ready: boolean }) {
  const to = `/lecon/${lessonId}/${step.key}`;
  return (
    <li className={`step step-${step.status}`}>
      <span className="step-mark">
        {step.status === "done" ? <Icon name="check" /> : step.status === "locked" ? <Icon name="lock" size={15} /> : step.status === "soon" ? "…" : <span className="pulse" />}
      </span>
      <div className="step-body">
        <div className="step-title">
          {step.label}
          {step.status === "done" && step.score !== null && <span className="muted"> · {step.score} %</span>}
          {step.status === "soon" && <span className="tag">Bientôt</span>}
        </div>
        <div className="muted">{step.description}</div>
      </div>
      {step.status === "current" &&
        (ready ? (
          <Link className="btn" to={to}>
            Continuer <Icon name="arrow" />
          </Link>
        ) : (
          <span className="muted row">
            <Spinner small /> En préparation
          </span>
        ))}
      {step.status === "done" && (
        <Link className="link-btn" to={to}>
          Revoir
        </Link>
      )}
    </li>
  );
}

function SourceModal({ lesson, onClose, onSaved }: { lesson: Lesson; onClose: () => void; onSaved: () => void }) {
  const source = useLoad(() => api.get<{ text: string }>(`/lessons/${lesson.id}/source`), [lesson.id]);
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const value = text ?? source.data?.text ?? "";
  const changed = text !== null && text.trim() !== (source.data?.text ?? "").trim();

  const save = async () => {
    if (!window.confirm("Corriger le texte relance toute la préparation et remet le parcours de cette leçon à zéro. Continuer ?")) return;
    setBusy(true);
    try {
      await api.put(`/lessons/${lesson.id}/source`, { text: value });
      onSaved();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
      setBusy(false);
    }
  };

  return (
    <Modal title="Texte de la leçon" onClose={onClose}>
      <p className="muted">C'est le texte que j'ai lu. S'il contient des erreurs de lecture, corrige-les ici.</p>
      {!source.data ? <Spinner /> : <textarea className="input" dir="auto" rows={16} value={value} onChange={(e) => setText(e.target.value)} />}
      {error && <p className="bad-text">{error}</p>}
      <div className="row end">
        <button className="btn btn-ghost" onClick={onClose}>
          Fermer
        </button>
        <button className="btn" disabled={!changed || busy} onClick={() => void save()}>
          Enregistrer et tout repréparer
        </button>
      </div>
    </Modal>
  );
}

/** Le parcours d'une leçon : les étapes s'allument une à une. */
export default function LessonPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [showSource, setShowSource] = useState(false);
  const { data, error, reload } = useLoad(() => api.get<Lesson>(`/lessons/${id}`), [id]);
  usePoll(reload, !!data?.generation.active);

  if (error) return <Notice tone="bad">{error.message}</Notice>;
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  const remove = async () => {
    if (!window.confirm(`Supprimer la leçon « ${data.title} » et toute sa progression ?`)) return;
    await api.del(`/lessons/${data.id}`);
    navigate("/lecons");
  };

  return (
    <div className="page">
      <Link className="link-btn" to="/lecons">
        <Icon name="back" size={15} /> Mes leçons
      </Link>
      <div className="row between wrap">
        <div>
          <div className="row">
            <SubjectChip name={data.subject.name} color={data.subject.color} />
            <span className="muted" dir="auto">
              {data.chapter.title}
            </span>
            {data.exam && <span className="exam-pill">Contrôle {daysLabel(data.exam.days_left)}</span>}
          </div>
          <h1 dir="auto">{data.title}</h1>
        </div>
        <div className="progress-box">
          <span className="muted">{data.progress} %</span>
          <Progress value={data.progress} tone={data.mastered ? "ok" : undefined} />
        </div>
      </div>

      {params.get("valide") && !data.mastered && <Notice tone="ok">Étape validée. La suivante est débloquée.</Notice>}
      {data.mastered && (
        <Notice tone="ok">
          <strong>
            <Icon name="star" /> Leçon maîtrisée.
          </strong>{" "}
          Tu as validé toutes les étapes, jusqu'aux exercices difficiles. Bravo.
        </Notice>
      )}
      {data.truncated && <Notice tone="warn">Cette leçon est très longue : seul le début a été utilisé. Découpe-la en plusieurs leçons pour tout couvrir.</Notice>}
      <GenerationNotice lessonId={data.id} generation={data.generation} onRetried={() => void reload()} />

      <ol className="path card">
        {(data.path ?? []).map((s) => (
          <StepRow key={s.key} step={s} lessonId={data.id} ready={!!data.current_ready} />
        ))}
        <li className={`step step-${data.mastered ? "done" : "locked"}`}>
          <span className="step-mark">
            <Icon name="star" size={16} />
          </span>
          <div className="step-body">
            <div className="step-title">Leçon maîtrisée</div>
            <div className="muted">Puis des rappels espacés les jours suivants.</div>
          </div>
        </li>
      </ol>

      <div className="row end">
        {data.has_text && (
          <button className="link-btn" onClick={() => setShowSource(true)}>
            Voir le texte de la leçon
          </button>
        )}
        <button className="link-btn danger" onClick={() => void remove()}>
          <Icon name="trash" size={14} /> Supprimer la leçon
        </button>
      </div>
      {showSource && (
        <SourceModal
          lesson={data}
          onClose={() => setShowSource(false)}
          onSaved={() => {
            setShowSource(false);
            void reload();
          }}
        />
      )}
    </div>
  );
}
