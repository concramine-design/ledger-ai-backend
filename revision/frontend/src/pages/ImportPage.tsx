import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, LANG_LABELS, type Lesson, type Subject } from "../api";
import { Notice, Spinner } from "../components/Ui";
import { useLoad } from "../hooks";

type Source = "text" | "pdf" | "photo";
const SOURCES: { key: Source; label: string }[] = [
  { key: "photo", label: "Photos du cahier" },
  { key: "pdf", label: "PDF" },
  { key: "text", label: "Texte collé" },
];

/** Import d'une leçon. Dès l'envoi, tout est généré en arrière-plan : aucun bouton « générer ». */
export default function ImportPage() {
  const navigate = useNavigate();
  const subjects = useLoad(() => api.get<Subject[]>("/subjects"), []);
  const [subjectId, setSubjectId] = useState<number | null>(null);
  const [chapters, setChapters] = useState<{ id: number; title: string }[]>([]);
  const [chapter, setChapter] = useState("");
  const [title, setTitle] = useState("");
  const [source, setSource] = useState<Source>("photo");
  const [text, setText] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const enabled = (subjects.data ?? []).filter((s) => s.enabled);
  const current = enabled.find((s) => s.id === subjectId) ?? null;

  useEffect(() => {
    if (subjectId === null && enabled.length) setSubjectId((enabled.find((s) => s.available) ?? enabled[0]).id);
  }, [enabled, subjectId]);

  useEffect(() => {
    if (subjectId === null) return;
    api
      .get<{ id: number; title: string }[]>(`/chapters?subject_id=${subjectId}`)
      .then(setChapters)
      .catch(() => setChapters([]));
  }, [subjectId]);

  if (!subjects.data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  const hasContent = source === "text" ? text.trim().length >= 50 : files.length > 0;
  const canSend = !!current?.available && chapter.trim() && title.trim() && hasContent && !busy;

  const submit = async () => {
    if (!current) return;
    setBusy(true);
    setError("");
    const form = new FormData();
    form.append("subject_id", String(current.id));
    form.append("chapter_title", chapter);
    form.append("title", title);
    if (source === "text") form.append("text", text);
    else files.forEach((f) => form.append("files", f));
    try {
      const lesson = await api.post<Lesson>("/lessons", form);
      navigate(`/lecon/${lesson.id}`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Une erreur est survenue.");
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <h1>Importer une leçon</h1>
      <p className="muted">Donne-moi ta leçon : je prépare l'explication, les questions et les exercices pendant que tu commences.</p>

      <div className="card form">
        <label className="field">
          <span>Matière</span>
          <select className="input select" value={subjectId ?? ""} onChange={(e) => setSubjectId(Number(e.target.value))}>
            {enabled.map((s) => (
              <option key={s.id} value={s.id} disabled={!s.available}>
                {s.name}
                {s.available ? "" : " (bientôt)"}
              </option>
            ))}
          </select>
          {current && <small className="muted">Explications et exercices en {LANG_LABELS[current.language].toLowerCase()}.</small>}
        </label>

        <div className="grid-2">
          <label className="field">
            <span>Chapitre</span>
            <input className="input" list="chapitres" dir="auto" value={chapter} onChange={(e) => setChapter(e.target.value)} placeholder="Ex. : Les fonctions" />
            <datalist id="chapitres">
              {chapters.map((c) => (
                <option key={c.id} value={c.title} />
              ))}
            </datalist>
          </label>
          <label className="field">
            <span>Titre de la leçon</span>
            <input className="input" dir="auto" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Ex. : Ensemble de définition" />
          </label>
        </div>

        <div className="field">
          <span>Ta leçon</span>
          <div className="segmented" role="tablist">
            {SOURCES.map((s) => (
              <button
                key={s.key}
                type="button"
                role="tab"
                aria-selected={source === s.key}
                className={source === s.key ? "active" : ""}
                onClick={() => {
                  setSource(s.key);
                  setFiles([]);
                }}
              >
                {s.label}
              </button>
            ))}
          </div>
        </div>

        {source === "text" ? (
          <textarea className="input" dir="auto" rows={12} value={text} onChange={(e) => setText(e.target.value)} placeholder="Colle ici le texte complet de la leçon…" />
        ) : (
          <label className="dropzone">
            <input
              type="file"
              multiple={source === "photo"}
              accept={source === "pdf" ? "application/pdf,.pdf" : "image/*,.heic,.heif"}
              onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            />
            {files.length === 0 ? (
              <span>
                {source === "pdf" ? "Choisis le PDF de la leçon" : "Choisis les photos des pages, dans l'ordre"}
                <small className="muted">{source === "photo" ? "Photos nettes, bien éclairées, une page par photo." : "PDF tapé ou scanné."}</small>
              </span>
            ) : (
              <span>
                {files.length} fichier{files.length > 1 ? "s" : ""} : {files.map((f) => f.name).join(", ")}
              </span>
            )}
          </label>
        )}

        {error && <Notice tone="bad">{error}</Notice>}
        <div className="row end">
          <button className="btn btn-big" disabled={!canSend} onClick={() => void submit()}>
            {busy ? <Spinner small /> : null} Importer et préparer ma leçon
          </button>
        </div>
      </div>
    </div>
  );
}
