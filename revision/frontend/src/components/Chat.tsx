import { useEffect, useRef, useState } from "react";
import { api, ApiError, type Lang } from "../api";
import { Md } from "./Md";
import { Icon, Spinner } from "./Ui";

interface Message {
  role: "user" | "assistant";
  content: string;
}

/** Chat sur la leçon. Il ne donne pas la réponse : il commence par une question. */
export function ChatPanel({ lessonId, lang, onClose }: { lessonId: number; lang: Lang; onClose: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .get<{ messages: Message[] }>(`/lessons/${lessonId}/chat`)
      .then((d) => setMessages(d.messages))
      .catch(() => undefined);
  }, [lessonId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages, busy]);

  const send = async () => {
    const question = text.trim();
    if (!question || busy) return;
    setBusy(true);
    setError("");
    try {
      const { reply } = await api.post<{ reply: string }>(`/lessons/${lessonId}/chat`, { message: question });
      setMessages((m) => [...m, { role: "user", content: question }, { role: "assistant", content: reply }]);
      setText("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Une erreur est survenue.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <aside className="chat no-print" aria-label="Chat sur la leçon">
      <div className="chat-head">
        <strong>Une question sur la leçon ?</strong>
        <button className="icon-btn" onClick={onClose} aria-label="Fermer le chat">
          <Icon name="close" />
        </button>
      </div>
      <div className="chat-body">
        {messages.length === 0 && (
          <p className="muted">
            Pose ta question. Je ne te donne pas la réponse tout de suite : je commence par une question pour t'aider à la trouver.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`bubble bubble-${m.role}`}>
            <Md text={m.content} lang={m.role === "assistant" ? lang : undefined} />
          </div>
        ))}
        {busy && (
          <div className="bubble bubble-assistant">
            <Spinner small />
          </div>
        )}
        {error && (
          <p className="bad-text" role="alert">
            {error} Ton message est conservé : tu peux le renvoyer.
          </p>
        )}
        <div ref={endRef} />
      </div>
      <form
        className="chat-form"
        onSubmit={(e) => {
          e.preventDefault();
          void send();
        }}
      >
        <textarea
          className="input"
          dir="auto"
          rows={2}
          value={text}
          placeholder="Écris ta question…"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
        />
        <button className="btn" disabled={busy || !text.trim()}>
          Envoyer
        </button>
      </form>
    </aside>
  );
}
