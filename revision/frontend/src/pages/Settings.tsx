import { Link } from "react-router-dom";
import { api, type Exam, type Subject } from "../api";
import { useApp } from "../App";
import { ExamsEditor, SubjectsEditor } from "../components/Editors";
import { Icon, Spinner } from "../components/Ui";
import { useLoad } from "../hooks";

const PROVIDERS: Record<string, string> = { gemini: "Gemini", groq: "Groq", mock: "IA simulée (démonstration)" };

/** Réglages : matières, langues, contrôles, seuils de réussite. */
export default function Settings() {
  const { state } = useApp();
  const subjects = useLoad(() => api.get<Subject[]>("/subjects"), []);
  const exams = useLoad(() => api.get<Exam[]>("/exams"), []);

  if (!subjects.data || !exams.data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

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

      <Link className="card link-card" to="/parent">
        <span>
          <strong>Espace parent / frère</strong>
          <span className="muted"> · progression détaillée et réglage des seuils de réussite (protégé par un code)</span>
        </span>
        <Icon name="arrow" />
      </Link>

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
        <p className="muted">Vidéos YouTube : {state.youtube ? "activées" : "désactivées (ajoute YOUTUBE_API_KEY dans .env)"}.</p>
      </section>
    </div>
  );
}
