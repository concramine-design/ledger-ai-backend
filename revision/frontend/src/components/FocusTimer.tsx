import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { Icon } from "./Ui";

const WORK = 25 * 60;
const BREAK = 5 * 60;

/** Minuteur de séance : 25 minutes de travail, puis 5 minutes de pause. Flottant, discret. */
export function FocusTimer() {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"work" | "break">("work");
  const [left, setLeft] = useState(WORK);
  const [running, setRunning] = useState(false);
  const counted = useRef(false);

  useEffect(() => {
    if (!running) return;
    const id = window.setInterval(() => setLeft((l) => Math.max(0, l - 1)), 1000);
    return () => window.clearInterval(id);
  }, [running]);

  useEffect(() => {
    if (left > 0) return;
    if (mode === "work" && !counted.current) {
      counted.current = true;
      void api.post("/activity/pomodoro", { minutes: 25 }).catch(() => undefined);
      try {
        new Audio("data:audio/wav;base64,UklGRhwAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=").play().catch(() => undefined);
      } catch {
        /* le son n'est pas indispensable */
      }
      setMode("break");
      setLeft(BREAK);
    } else if (mode === "break") {
      setMode("work");
      setLeft(WORK);
      setRunning(false);
      counted.current = false;
    }
  }, [left, mode]);

  const mm = Math.floor(left / 60);
  const ss = String(left % 60).padStart(2, "0");
  const reset = () => {
    setRunning(false);
    setMode("work");
    setLeft(WORK);
    counted.current = false;
  };

  if (!open) {
    return (
      <button className="timer-fab no-print" onClick={() => setOpen(true)} aria-label="Minuteur de séance">
        <Icon name="clock" />
      </button>
    );
  }
  return (
    <div className={`timer-card no-print ${mode === "break" ? "timer-break" : ""}`}>
      <div className="row between">
        <strong>{mode === "work" ? "Concentration" : "Pause"}</strong>
        <button className="icon-btn" onClick={() => setOpen(false)} aria-label="Fermer le minuteur">
          <Icon name="close" size={16} />
        </button>
      </div>
      <div className="timer-time">
        {mm}:{ss}
      </div>
      <div className="row center-row">
        <button className="btn btn-small" onClick={() => setRunning((r) => !r)}>
          {running ? "Pause" : "Démarrer"}
        </button>
        <button className="btn btn-ghost btn-small" onClick={reset}>
          Réinitialiser
        </button>
      </div>
      <p className="muted small">{mode === "work" ? "25 min de travail, puis une pause." : "Repose-toi 5 minutes."}</p>
    </div>
  );
}
