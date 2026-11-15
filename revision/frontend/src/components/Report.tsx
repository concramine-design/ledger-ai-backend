import { useState } from "react";
import { api } from "../api";
import { Icon, Modal } from "./Ui";

/** Rappel visible + bouton « Signaler une erreur » sous chaque explication ou correction. */
export function TrustNote({ lessonId, target, excerpt }: { lessonId: number; target: string; excerpt?: string }) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  const send = async () => {
    try {
      await api.post("/reports", { lesson_id: lessonId, target, excerpt: (excerpt ?? "").slice(0, 1500), comment });
      setSent(true);
      setOpen(false);
      setComment("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Erreur");
    }
  };

  return (
    <div className="trust no-print">
      <span>En cas de désaccord avec ton cours, c'est ton professeur qui a raison.</span>
      {sent ? (
        <span className="ok-text">Merci, c'est noté.</span>
      ) : (
        <button className="link-btn" onClick={() => setOpen(true)}>
          <Icon name="flag" size={14} /> Signaler une erreur
        </button>
      )}
      {open && (
        <Modal title="Signaler une erreur" onClose={() => setOpen(false)}>
          <p className="muted">Qu'est-ce qui te semble faux ou différent de ton cours ?</p>
          <textarea className="input" rows={4} dir="auto" value={comment} onChange={(e) => setComment(e.target.value)} autoFocus />
          {error && <p className="bad-text">{error}</p>}
          <div className="row end">
            <button className="btn btn-ghost" onClick={() => setOpen(false)}>
              Annuler
            </button>
            <button className="btn" onClick={send} disabled={!comment.trim()}>
              Envoyer
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}
