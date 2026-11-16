import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Explanation, type Video } from "../api";
import { ChatPanel } from "../components/Chat";
import { Md } from "../components/Md";
import { MindMap } from "../components/MindMap";
import { TrustNote } from "../components/Report";
import { Icon, Notice } from "../components/Ui";
import { usePoll } from "../hooks";
import type { StepProps } from "../pages/StepPage";

function minutes(seconds: number): string {
  return `${Math.max(1, Math.round(seconds / 60))} min`;
}

/** Les 3 vidéos choisies par l'application, avec la raison du choix. Le lecteur ne se charge qu'au clic. */
function Videos({ videos }: { videos: Video[] }) {
  const [playing, setPlaying] = useState<string | null>(null);
  return (
    <section className="videos no-print">
      <h2>Vidéos choisies pour toi</h2>
      <div className="video-grid">
        {videos.map((v) => (
          <article key={v.id} className="card video">
            {playing === v.id ? (
              <iframe
                className="video-frame"
                src={`https://www.youtube-nocookie.com/embed/${v.id}?autoplay=1&rel=0`}
                title={v.title}
                allow="autoplay; encrypted-media; picture-in-picture"
                allowFullScreen
              />
            ) : (
              <button className="video-thumb" onClick={() => setPlaying(v.id)} aria-label={`Lire la vidéo : ${v.title}`}>
                <img src={`https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`} alt="" loading="lazy" />
                <span className="video-play">▶</span>
                <span className="video-duration">{minutes(v.duration_s)}</span>
              </button>
            )}
            <div className="video-title" dir="auto">
              {v.title}
            </div>
            <div className="muted small" dir="auto">
              {v.channel}
            </div>
            <p className="video-reason" dir="auto">
              <strong>Pourquoi celle-ci : </strong>
              {v.raison}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}

/** Étape 1 : l'explication, une partie à la fois, avec exemple et phrase à retenir. */
export default function Comprendre({ data, reload }: StepProps) {
  const navigate = useNavigate();
  const content = data.content as Explanation;
  const lang = data.language;
  const [index, setIndex] = useState(0);
  const [chat, setChat] = useState(false);
  const [error, setError] = useState("");
  const section = content.sections[index];
  const last = index === content.sections.length - 1;
  const videos = data.videos?.videos ?? [];
  usePoll(reload, data.videos == null); // la sélection de vidéos arrive un peu après l'explication

  const validate = async () => {
    try {
      await api.post(`/lessons/${data.lesson.id}/steps/comprendre/validate`);
      navigate(`/lecon/${data.lesson.id}?valide=comprendre`);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Erreur");
    }
  };

  return (
    <div className={`with-chat ${chat ? "chat-open" : ""}`}>
      <div className="grow">
        {index === 0 && content.accroche && (
          <div className="card intro">
            <Md text={content.accroche} lang={lang} />
          </div>
        )}
        <div className="pager" aria-label="Parties de l'explication">
          {content.sections.map((s, i) => (
            <button key={i} className={`pager-dot ${i === index ? "on" : i < index ? "seen" : ""}`} onClick={() => setIndex(i)} aria-label={`Partie ${i + 1} : ${s.titre}`} />
          ))}
          <span className="muted">
            Partie {index + 1} sur {content.sections.length}
          </span>
        </div>

        <article className="card lesson-card">
          <h2 dir={lang === "ar" ? "rtl" : "ltr"}>{section.titre}</h2>
          <Md text={section.contenu} lang={lang} />
          {section.exemple && (
            <div className="callout callout-example">
              <div className="callout-title">Exemple</div>
              <Md text={section.exemple} lang={lang} />
            </div>
          )}
          {section.a_retenir && (
            <div className="callout callout-keep">
              <div className="callout-title">À retenir</div>
              <Md text={section.a_retenir} lang={lang} />
            </div>
          )}
          <TrustNote lessonId={data.lesson.id} target={`explication:partie-${index + 1}`} excerpt={section.contenu} />
        </article>

        {data.mindmap && (
          <section className="mindmap-section">
            <h2>Carte mentale</h2>
            <div className="card">
              <MindMap map={data.mindmap} lang={lang} />
            </div>
          </section>
        )}
        {videos.length > 0 && <Videos videos={videos} />}
        {data.videos == null && <p className="muted small">Je cherche des vidéos sur cette leçon…</p>}

        {error && <Notice tone="bad">{error}</Notice>}
        <div className="row between">
          <button className="btn btn-ghost" onClick={() => setIndex((i) => i - 1)} disabled={index === 0}>
            <Icon name="back" /> Précédent
          </button>
          <button className="btn btn-ghost" onClick={() => setChat((c) => !c)}>
            <Icon name="chat" /> {chat ? "Fermer le chat" : "Poser une question"}
          </button>
          {!last ? (
            <button className="btn" onClick={() => setIndex((i) => i + 1)}>
              Suivant <Icon name="arrow" />
            </button>
          ) : data.status === "current" ? (
            <button className="btn" onClick={() => void validate()}>
              J'ai compris, je passe au mini-test <Icon name="arrow" />
            </button>
          ) : (
            <button className="btn" onClick={() => navigate(`/lecon/${data.lesson.id}`)}>
              Retour au parcours
            </button>
          )}
        </div>
      </div>
      {chat && <ChatPanel lessonId={data.lesson.id} lang={lang} onClose={() => setChat(false)} />}
    </div>
  );
}
