import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { api, ApiError, type Exam, type Subject } from "../api";
import { useApp } from "../App";
import { ExamsEditor, SubjectsEditor } from "../components/Editors";
import { Spinner } from "../components/Ui";
import { useLoad } from "../hooks";

const TITLES = ["Tes matières", "La langue de chaque matière", "Tes prochains contrôles"];
const HELP = [
  "Vérifie la liste. Décoche celles que tu n'as pas, renomme-les ou ajoutes-en.",
  "C'est la langue des explications et des exercices. Choisis celle de ton cours.",
  "Ajoute les dates que tu connais. Je m'en sers pour te dire quoi réviser en premier. Tu pourras en ajouter plus tard.",
];

/** Premier lancement : matières, langues, dates des contrôles. */
export default function Onboarding() {
  const { state, refresh } = useApp();
  const navigate = useNavigate();
  const [screen, setScreen] = useState(0);
  const [error, setError] = useState("");
  const subjects = useLoad(() => api.get<Subject[]>("/subjects"), []);
  const exams = useLoad(() => api.get<Exam[]>("/exams"), []);

  if (state.onboarded) return <Navigate to="/" replace />;
  if (!subjects.data || !exams.data) {
    return (
      <div className="center-screen">
        <Spinner />
      </div>
    );
  }

  const finish = async () => {
    try {
      await api.post("/onboarding/complete");
      await refresh();
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };

  return (
    <div className="onboarding">
      <div className="card card-wide">
        <p className="eyebrow">Bienvenue · étape {screen + 1} sur 3</p>
        <div className="dots" aria-hidden="true">
          {TITLES.map((_, i) => (
            <span key={i} className={i <= screen ? "dot-on" : ""} />
          ))}
        </div>
        <h1>{TITLES[screen]}</h1>
        <p className="muted">{HELP[screen]}</p>

        {screen === 0 && <SubjectsEditor mode="subjects" subjects={subjects.data} onChange={subjects.setData} />}
        {screen === 1 && <SubjectsEditor mode="languages" subjects={subjects.data} onChange={subjects.setData} />}
        {screen === 2 && <ExamsEditor subjects={subjects.data} exams={exams.data} onChange={exams.setData} />}

        {error && <p className="bad-text">{error}</p>}
        <div className="row between top-gap">
          <button className="btn btn-ghost" onClick={() => setScreen((s) => s - 1)} disabled={screen === 0}>
            Retour
          </button>
          {screen < 2 ? (
            <button className="btn" onClick={() => setScreen((s) => s + 1)} disabled={!subjects.data.some((s) => s.enabled)}>
              Suivant
            </button>
          ) : (
            <button className="btn" onClick={() => void finish()}>
              C'est parti
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
