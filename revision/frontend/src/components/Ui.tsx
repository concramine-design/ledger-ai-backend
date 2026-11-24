import { useEffect, type ReactNode } from "react";
import { api, type Generation } from "../api";

export function Spinner({ small }: { small?: boolean }) {
  return <span className={`spinner ${small ? "spinner-small" : ""}`} aria-hidden="true" />;
}

const ICONS: Record<string, string> = {
  check: "M5 12.5l4.5 4.5L19 7.5",
  lock: "M7 11V8a5 5 0 0110 0v3M6 11h12v9H6z",
  arrow: "M5 12h14M13 6l6 6-6 6",
  back: "M19 12H5M11 6l-6 6 6 6",
  clock: "M12 7v5l3 2M12 21a9 9 0 100-18 9 9 0 000 18z",
  chat: "M4 5h16v11H9l-5 4z",
  close: "M6 6l12 12M18 6L6 18",
  flag: "M5 21V4h11l-1.5 4L16 12H5",
  plus: "M12 5v14M5 12h14",
  trash: "M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13",
  print: "M7 9V4h10v5M7 17H4v-7h16v7h-3M7 14h10v6H7z",
  star: "M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z",
};

export function Icon({ name, size = 18 }: { name: keyof typeof ICONS | string; size?: number }) {
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={ICONS[name] ?? ""} />
    </svg>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "ok" | "warn" | "bad"; children: ReactNode }) {
  return (
    <div className={`notice notice-${tone}`} role={tone === "bad" ? "alert" : "status"}>
      {children}
    </div>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <div className="modal-head">
          <h2>{title}</h2>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer">
            <Icon name="close" />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

/** État de la génération : préparation en cours, nouvelle tentative automatique, ou panne à signaler. */
export function GenerationNotice({ lessonId, generation, onRetried }: { lessonId: number; generation: Generation; onRetried?: () => void }) {
  const { problem } = generation;
  const retry = async () => {
    try {
      await api.post(`/lessons/${lessonId}/retry`);
    } finally {
      onRetried?.();
    }
  };
  if (problem) {
    return (
      <Notice tone={problem.fatal ? "bad" : "warn"}>
        <p>
          <strong>{problem.label} :</strong> {problem.message}
        </p>
        <p className="muted">
          {problem.fatal
            ? "Ta progression est conservée."
            : `Ta progression est conservée. Nouvelle tentative${problem.retry_in ? ` dans ${problem.retry_in} s` : ""}…`}
        </p>
        <button className="btn btn-small" onClick={retry}>
          Réessayer maintenant
        </button>
      </Notice>
    );
  }
  if (!generation.active) return null;
  if (generation.claude && generation.claude.waiting > 0) {
    const until = new Date(generation.claude.until).toLocaleString("fr-FR", { weekday: "long", hour: "2-digit", minute: "2-digit" });
    const prepareNow = async () => {
      try {
        await api.post(`/lessons/${lessonId}/prepare-now`);
      } finally {
        onRetried?.();
      }
    };
    return (
      <Notice tone="info">
        <p>
          <strong>Claude prépare ta leçon pendant la nuit.</strong> Elle sera prête pour ta prochaine séance, au plus tard {until}.
        </p>
        <p className="muted">Tu veux commencer tout de suite ? La préparation automatique peut s'en charger maintenant.</p>
        <button className="btn btn-small" onClick={() => void prepareNow()}>
          Préparer maintenant
        </button>
      </Notice>
    );
  }
  return (
    <div className="preparing">
      <Spinner small />
      <span>
        Je prépare ta leçon{generation.current ? ` : ${generation.current.toLowerCase()}` : ""} ({generation.done}/{generation.total})
      </span>
    </div>
  );
}

export function Progress({ value, tone }: { value: number; tone?: "ok" }) {
  return (
    <div className="progress" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className={`progress-bar ${tone === "ok" ? "progress-ok" : ""}`} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function SubjectChip({ name, color }: { name: string; color: string }) {
  return (
    <span className="chip" style={{ borderColor: color, color }}>
      {name}
    </span>
  );
}
