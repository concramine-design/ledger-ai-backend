import { Link, useParams } from "react-router-dom";
import { api, type StepData } from "../api";
import { GenerationNotice, Icon, Notice, Spinner, SubjectChip } from "../components/Ui";
import { useLoad, usePoll } from "../hooks";
import Comprendre from "../steps/Comprendre";
import Exercices from "../steps/Exercices";
import Explique from "../steps/Explique";
import Feuille from "../steps/Feuille";
import Resume from "../steps/Resume";
import TestStep from "../steps/TestStep";

export interface StepProps {
  data: StepData;
  reload: () => Promise<void>;
}

/** Une étape du parcours. Le serveur refuse l'accès si l'étape est verrouillée. */
export default function StepPage() {
  const { id, step } = useParams();
  const { data, error, reload } = useLoad(() => api.get<StepData>(`/lessons/${id}/steps/${step}`), [id, step]);
  const waiting = !!data && !data.ready && !data.previous && data.step.key !== "feuille" && data.step.key !== "explique";
  usePoll(reload, waiting);

  if (error) {
    return (
      <div className="page">
        <Notice tone={error.status === 403 ? "warn" : "bad"}>
          <p>{error.message}</p>
          <Link className="btn btn-small" to={`/lecon/${id}`}>
            Retour au parcours
          </Link>
        </Notice>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  const key = data.step.key;
  return (
    <div className="page step-page">
      <div className="row between no-print">
        <Link className="link-btn" to={`/lecon/${data.lesson.id}`}>
          <Icon name="back" size={15} /> Parcours de la leçon
        </Link>
        <div className="row">
          <SubjectChip name={data.lesson.subject.name} color={data.lesson.subject.color} />
          <span className="muted" dir="auto">
            {data.lesson.title}
          </span>
        </div>
      </div>
      <h1 className="no-print">{data.step.label}</h1>

      {waiting ? (
        <div className="card center-card">
          <p>Cette étape est presque prête.</p>
          <GenerationNotice lessonId={data.lesson.id} generation={data.generation} onRetried={() => void reload()} />
        </div>
      ) : key === "comprendre" ? (
        <Comprendre data={data} reload={reload} />
      ) : key === "feuille" ? (
        <Feuille data={data} reload={reload} />
      ) : key === "explique" ? (
        <Explique data={data} reload={reload} />
      ) : key === "resume" ? (
        <Resume data={data} reload={reload} />
      ) : key === "minitest" || key === "quiz" ? (
        <TestStep key={key} data={data} reload={reload} />
      ) : (
        <Exercices key={key} data={data} reload={reload} />
      )}
    </div>
  );
}
