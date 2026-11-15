import { useRef } from "react";
import type { Feedback } from "../api";
import { Md } from "./Md";
import type { Lang } from "../api";

const SYMBOLS = ["²", "³", "√", "×", "÷", "≤", "≥", "≠", "±", "π", "∈", "∉", "ℝ", "∞", "→", "∪", "∩", "⊂", "°"];

interface BoxProps {
  value: string;
  onChange: (v: string) => void;
  disabled?: boolean;
  rows?: number;
  placeholder?: string;
  symbols?: boolean;
}

/** Zone de réponse : texte libre, avec une barre de symboles pour les sciences. */
export function AnswerBox({ value, onChange, disabled, rows = 4, placeholder, symbols = true }: BoxProps) {
  const ref = useRef<HTMLTextAreaElement>(null);
  const insert = (s: string) => {
    const el = ref.current;
    if (!el) return onChange(value + s);
    const start = el.selectionStart ?? value.length;
    const end = el.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + s + value.slice(end));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(start + s.length, start + s.length);
    });
  };
  return (
    <div className="answer-box">
      <textarea
        ref={ref}
        className="input"
        dir="auto"
        rows={rows}
        value={value}
        disabled={disabled}
        placeholder={placeholder ?? "Écris ta réponse ici…"}
        onChange={(e) => onChange(e.target.value)}
      />
      {symbols && !disabled && (
        <div className="symbols" aria-label="Symboles">
          {SYMBOLS.map((s) => (
            <button key={s} type="button" className="symbol" onClick={() => insert(s)} tabIndex={-1}>
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const STATE_LABEL = { ok: "Présent", partiel: "Incomplet", absent: "Manquant" } as const;
const STATE_MARK = { ok: "✓", partiel: "~", absent: "✗" } as const;

export function scoreTone(score: number | null | undefined): "ok" | "warn" | "bad" {
  const s = score ?? 0;
  return s >= 0.999 ? "ok" : s >= 0.5 ? "warn" : "bad";
}

export function scoreLabel(score: number | null | undefined): string {
  const tone = scoreTone(score);
  return tone === "ok" ? "Juste" : tone === "warn" ? "Presque" : "À revoir";
}

/** Retour précis de l'IA sur une réponse ouverte : ce qui est juste, ce qui manque. */
export function FeedbackView({ feedback, score, lang }: { feedback: Feedback | null; score: number | null; lang: Lang }) {
  if (!feedback) return null;
  const elements = feedback.elements ?? [];
  const criteria = feedback.criteres ?? [];
  const faults = feedback.fautes ?? [];
  return (
    <div className={`feedback feedback-${scoreTone(score)}`}>
      <div className="feedback-head">
        <span className={`badge badge-${scoreTone(score)}`}>{scoreLabel(score)}</span>
        <span className="muted">{Math.round((score ?? 0) * 100)} %</span>
      </div>
      {criteria.length > 0 && (
        <ul className="criteria">
          {criteria.map((c, i) => (
            <li key={i}>
              <span className="criteria-name">{c.nom}</span>
              <span className="criteria-dots" aria-label={`${c.note} sur 4`}>
                {[1, 2, 3, 4].map((n) => (
                  <span key={n} className={n <= Math.round(c.note) ? "pip on" : "pip"} />
                ))}
              </span>
              {c.commentaire && (
                <span className="muted criteria-comment">
                  <Md inline text={c.commentaire} lang={lang} />
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
      {faults.length > 0 && (
        <div className="faults">
          <strong className="warn-text">Tes fautes, à corriger toi-même :</strong>
          <ul className="plain">
            {faults.map((f, i) => (
              <li key={i} className="fault">
                {f.extrait && (
                  <q className="fault-quote" dir="auto">
                    {f.extrait}
                  </q>
                )}
                {f.type && <span className="tag">{f.type}</span>}
                <div>
                  <Md inline text={f.explication} lang={lang} />
                </div>
                {f.piste && (
                  <div className="muted">
                    <Md inline text={f.piste} lang={lang} />
                  </div>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}
      {elements.length > 0 && (
        <ul className="elements">
          {elements.map((e, i) => (
            <li key={i} className={`element element-${e.etat}`}>
              <span className="element-mark" title={STATE_LABEL[e.etat]}>
                {STATE_MARK[e.etat]}
              </span>
              <span>
                {e.attendu ? <Md inline text={e.attendu} lang={lang} /> : <span>Élément {i + 1} : {STATE_LABEL[e.etat].toLowerCase()}</span>}
                {e.commentaire && <span className="muted"> — <Md inline text={e.commentaire} lang={lang} /></span>}
              </span>
            </li>
          ))}
        </ul>
      )}
      {feedback.points_justes && (
        <p>
          <strong className="ok-text">Ce qui est juste : </strong>
          <Md inline text={feedback.points_justes} lang={lang} />
        </p>
      )}
      {feedback.manque && (
        <p>
          <strong className="warn-text">Ce qui manque : </strong>
          <Md inline text={feedback.manque} lang={lang} />
        </p>
      )}
      {(feedback.erreurs ?? []).length > 0 && (
        <div>
          <strong className="bad-text">Erreurs : </strong>
          <ul className="plain">
            {feedback.erreurs!.map((e, i) => (
              <li key={i}>
                <Md inline text={e} lang={lang} />
              </li>
            ))}
          </ul>
        </div>
      )}
      {feedback.conseil && (
        <p className="muted">
          <strong>Conseil : </strong>
          <Md inline text={feedback.conseil} lang={lang} />
        </p>
      )}
    </div>
  );
}
