import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, ApiError, type Explanation } from "../api";
import { ChatPanel } from "../components/Chat";
import { Md } from "../components/Md";
import { TrustNote } from "../components/Report";
import { Icon, Notice } from "../components/Ui";
import type { StepProps } from "../pages/StepPage";

/** Étape 1 : l'explication, une partie à la fois, avec exemple et phrase à retenir. */
export default function Comprendre({ data }: StepProps) {
  const navigate = useNavigate();
  const content = data.content as Explanation;
  const lang = data.language;
  const [index, setIndex] = useState(0);
  const [chat, setChat] = useState(false);
  const [error, setError] = useState("");
  const section = content.sections[index];
  const last = index === content.sections.length - 1;

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
