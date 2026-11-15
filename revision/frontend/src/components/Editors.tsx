import { useState } from "react";
import { api, ApiError, KIND_LABELS, LANG_LABELS, type Exam, type Kind, type Lang, type Subject } from "../api";
import { Icon } from "./Ui";

const LANGS: Lang[] = ["fr", "ar", "en"];

interface SubjectsProps {
  subjects: Subject[];
  onChange: (subjects: Subject[]) => void;
  mode: "subjects" | "languages" | "all";
}

/** Liste des matières : cocher, renommer, ajouter, choisir la langue. */
export function SubjectsEditor({ subjects, onChange, mode }: SubjectsProps) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<Kind>("sciences");
  const [error, setError] = useState("");

  const run = async (call: Promise<Subject[]>) => {
    try {
      onChange(await call);
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };
  const patch = (id: number, body: Partial<Subject>) => run(api.patch<Subject[]>(`/subjects/${id}`, body));
  const showToggle = mode !== "languages";
  const showLang = mode !== "subjects";
  const visible = mode === "languages" ? subjects.filter((s) => s.enabled) : subjects;

  return (
    <div className="editor">
      <ul className="rows">
        {visible.map((s) => (
          <li key={s.id} className={`row-item ${s.enabled ? "" : "row-off"}`}>
            {showToggle && (
              <input
                type="checkbox"
                className="check"
                checked={s.enabled}
                aria-label={`Activer ${s.name}`}
                onChange={(e) => void patch(s.id, { enabled: e.target.checked })}
              />
            )}
            <span className="dot" style={{ background: s.color }} />
            {showToggle ? (
              <input
                className="input input-inline"
                defaultValue={s.name}
                aria-label="Nom de la matière"
                onBlur={(e) => {
                  const value = e.target.value.trim();
                  if (value && value !== s.name) void patch(s.id, { name: value });
                  else e.target.value = s.name;
                }}
              />
            ) : (
              <span className="grow">{s.name}</span>
            )}
            {showLang && (
              <div className="segmented" role="group" aria-label={`Langue de ${s.name}`}>
                {LANGS.map((l) => (
                  <button
                    key={l}
                    type="button"
                    className={s.language === l ? "active" : ""}
                    aria-pressed={s.language === l}
                    disabled={!s.enabled}
                    onClick={() => void patch(s.id, { language: l })}
                  >
                    {LANG_LABELS[l]}
                  </button>
                ))}
              </div>
            )}
          </li>
        ))}
      </ul>
      {showToggle && (
        <form
          className="row add-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!name.trim()) return;
            void run(api.post<Subject[]>("/subjects", { name, kind, language: "fr" })).then(() => setName(""));
          }}
        >
          <input className="input" placeholder="Ajouter une matière…" value={name} onChange={(e) => setName(e.target.value)} />
          <select className="input select" value={kind} onChange={(e) => setKind(e.target.value as Kind)} aria-label="Type de matière">
            {(Object.keys(KIND_LABELS) as Kind[]).map((k) => (
              <option key={k} value={k}>
                {KIND_LABELS[k]}
              </option>
            ))}
          </select>
          <button className="btn btn-ghost" disabled={!name.trim()}>
            <Icon name="plus" /> Ajouter
          </button>
        </form>
      )}
      {error && <p className="bad-text">{error}</p>}
    </div>
  );
}

export function daysLabel(days: number): string {
  if (days <= 0) return "aujourd'hui";
  if (days === 1) return "demain";
  return `dans ${days} jours`;
}

export function formatDate(iso: string): string {
  return new Date(`${iso}T12:00:00`).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

/** Dates des prochains contrôles. */
export function ExamsEditor({ subjects, exams, onChange }: { subjects: Subject[]; exams: Exam[]; onChange: (e: Exam[]) => void }) {
  const active = subjects.filter((s) => s.enabled);
  const [subjectId, setSubjectId] = useState<number>(active[0]?.id ?? 0);
  const [date, setDate] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const today = new Date().toISOString().slice(0, 10);

  const add = async () => {
    try {
      onChange(await api.post<Exam[]>("/exams", { subject_id: subjectId || active[0]?.id, date, title }));
      setDate("");
      setTitle("");
      setError("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };

  return (
    <div className="editor">
      <form
        className="row add-row"
        onSubmit={(e) => {
          e.preventDefault();
          if (date) void add();
        }}
      >
        <select className="input select" value={subjectId || active[0]?.id} onChange={(e) => setSubjectId(Number(e.target.value))} aria-label="Matière du contrôle">
          {active.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        <input className="input" type="date" min={today} value={date} onChange={(e) => setDate(e.target.value)} aria-label="Date du contrôle" />
        <input className="input grow" placeholder="Titre (facultatif) : DS n°1…" value={title} onChange={(e) => setTitle(e.target.value)} />
        <button className="btn btn-ghost" disabled={!date}>
          <Icon name="plus" /> Ajouter
        </button>
      </form>
      {error && <p className="bad-text">{error}</p>}
      {exams.length === 0 ? (
        <p className="muted">Aucun contrôle pour l'instant.</p>
      ) : (
        <ul className="rows">
          {exams.map((x) => (
            <li key={x.id} className="row-item">
              <span className="grow">
                <strong>{x.subject_name}</strong>
                {x.title ? ` — ${x.title}` : ""}
                <span className="muted"> · {formatDate(x.date)} ({daysLabel(x.days_left)})</span>
              </span>
              <button className="icon-btn" aria-label="Supprimer ce contrôle" onClick={async () => onChange(await api.del<Exam[]>(`/exams/${x.id}`))}>
                <Icon name="trash" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
