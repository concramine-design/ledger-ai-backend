import { useState } from "react";
import { api, ApiError, type Exam, type Subject } from "../api";
import { useApp } from "../App";
import { ExamsEditor, SubjectsEditor } from "../components/Editors";
import { Spinner } from "../components/Ui";
import { useLoad } from "../hooks";

const PROVIDERS: Record<string, string> = { gemini: "Gemini", groq: "Groq", mock: "IA simulée (démonstration)" };

/** Réglages : matières, langues, contrôles, seuils de réussite. */
export default function Settings() {
  const { state, refresh } = useApp();
  const subjects = useLoad(() => api.get<Subject[]>("/subjects"), []);
  const exams = useLoad(() => api.get<Exam[]>("/exams"), []);
  const [quiz, setQuiz] = useState(String(state.settings.quiz_threshold));
  const [saved, setSaved] = useState("");

  if (!subjects.data || !exams.data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  const saveThreshold = async () => {
    try {
      await api.patch("/settings", { quiz_threshold: Number(quiz) });
      await refresh();
      setSaved("Seuil enregistré.");
    } catch (e) {
      setSaved(e instanceof ApiError ? "Choisis une valeur entre 50 et 100." : "Erreur");
    }
  };

  return (
    <div className="page">
      <h1>Réglages</h1>

      <section className="card">
        <h2>Matières et langues</h2>
        <p className="muted">La langue est celle des explications et des exercices de la matière.</p>
        <SubjectsEditor mode="all" subjects={subjects.data} onChange={subjects.setData} />
      </section>

      <section className="card">
        <h2>Prochains contrôles</h2>
        <ExamsEditor subjects={subjects.data} exams={exams.data} onChange={exams.setData} />
      </section>

      <section className="card">
        <h2>Seuil de réussite du quiz</h2>
        <p className="muted">Pourcentage à atteindre au quiz complet pour débloquer les exercices.</p>
        <div className="row">
          <input className="input input-number" type="number" min={50} max={100} step={5} value={quiz} onChange={(e) => setQuiz(e.target.value)} aria-label="Seuil du quiz en pourcentage" />
          <span>%</span>
          <button className="btn btn-ghost" onClick={() => void saveThreshold()}>
            Enregistrer
          </button>
          {saved && <span className="muted">{saved}</span>}
        </div>
      </section>

      <section className="card">
        <h2>Intelligence artificielle</h2>
        {state.ai.configured ? (
          <p>
            Fournisseur actif : <strong>{PROVIDERS[state.ai.provider ?? ""] ?? state.ai.provider}</strong>
          </p>
        ) : (
          <p className="warn-text">Aucune clé configurée. Remplis le fichier .env, puis relance l'application.</p>
        )}
        <p className="muted">Les clés se règlent dans le fichier .env du dossier de l'application, jamais ici.</p>
      </section>
    </div>
  );
}
