import { useEffect, useState } from "react";
import { ApiError, type ParentOverview } from "../api";
import { formatDate } from "../components/Editors";
import { Icon, Spinner } from "../components/Ui";
import { useLoad } from "../hooks";
import { api } from "../api";

const COLOR_CLASS = { vert: "m-vert", orange: "m-orange", rouge: "m-rouge" } as const;
const SETTINGS: { key: string; label: string; min: number; max: number }[] = [
  { key: "minitest_threshold", label: "Seuil du mini-test", min: 40, max: 100 },
  { key: "quiz_threshold", label: "Seuil du quiz complet", min: 50, max: 100 },
  { key: "exercise_threshold", label: "Seuil d'un exercice réussi", min: 40, max: 100 },
  { key: "feuille_threshold", label: "Seuil de la feuille blanche", min: 20, max: 100 },
  { key: "explique_threshold", label: "Seuil d'« Explique-moi »", min: 40, max: 100 },
];

/** Appels authentifiés de l'espace parent : le jeton va dans l'en-tête X-Parent-Token. */
async function parentFetch<T>(path: string, token: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`/api${path}`, {
    ...init,
    headers: { ...(init?.headers ?? {}), "Content-Type": "application/json", "X-Parent-Token": token },
  });
  if (!resp.ok) throw new ApiError(resp.status, "Accès refusé. Entre à nouveau le code.");
  return (await resp.json()) as T;
}

function Gate({ codeSet, onToken }: { codeSet: boolean; onToken: (t: string) => void }) {
  const [code, setCode] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const submit = async () => {
    setErr("");
    try {
      if (codeSet) {
        onToken((await api.post<{ token: string }>("/parent/login", { code })).token);
      } else {
        if (code !== confirm) return setErr("Les deux codes ne correspondent pas.");
        onToken((await api.post<{ token: string }>("/parent/setup", { code })).token);
      }
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : "Erreur");
    }
  };
  return (
    <div className="onboarding">
      <div className="card card-wide parent-gate">
        <Icon name="lock" size={28} />
        <h1>Espace parent / frère</h1>
        <p className="muted">
          {codeSet ? "Entre le code pour voir la progression et régler les seuils." : "Choisis un code. Il protège l'accès à la progression et aux réglages."}
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
        >
          <input className="input input-number parent-code" type="password" inputMode="numeric" autoFocus value={code} onChange={(e) => setCode(e.target.value)} placeholder="Code" aria-label="Code" />
          {!codeSet && (
            <input className="input input-number parent-code" type="password" inputMode="numeric" value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="Confirme le code" aria-label="Confirmer le code" />
          )}
          {err && <p className="bad-text">{err}</p>}
          <button className="btn btn-big" disabled={code.length < 4}>
            {codeSet ? "Entrer" : "Créer le code"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Overview({ token, onExpired }: { token: string; onExpired: () => void }) {
  const [over, setOver] = useState<ParentOverview | null>(null);
  const [settings, setSettings] = useState<Record<string, number>>({});
  const [saved, setSaved] = useState("");

  useEffect(() => {
    parentFetch<ParentOverview>("/parent/overview", token)
      .then((d) => {
        setOver(d);
        setSettings(d.settings);
      })
      .catch(() => onExpired());
  }, [token, onExpired]);

  if (!over) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }

  const maxDay = Math.max(1, ...over.history.map((d) => d.actions + d.pomodoros));
  const saveSetting = async (key: string, value: number) => {
    try {
      setSettings(await parentFetch<Record<string, number>>("/settings", token, { method: "PATCH", body: JSON.stringify({ [key]: value }) }));
      setSaved("Enregistré.");
    } catch {
      setSaved("Valeur refusée (reste entre les bornes).");
    }
  };

  return (
    <div className="page">
      <div className="row between">
        <h1>Espace parent</h1>
        <span className="muted row">
          <Icon name="star" size={16} /> Série : {over.streak} jour{over.streak > 1 ? "s" : ""}
        </span>
      </div>

      <section className="card">
        <h2 className="flush">Activité des 14 derniers jours</h2>
        <div className="activity-bars">
          {over.history.map((d) => (
            <div key={d.date} className="activity-day" title={`${formatDate(d.date)} : ${d.actions} actions, ${d.pomodoros} séances`}>
              <div className="activity-bar" style={{ height: `${Math.max(4, (100 * (d.actions + d.pomodoros)) / maxDay)}%` }} />
            </div>
          ))}
        </div>
      </section>

      {over.subjects.map((s) => (
        <section key={s.subject.id} className="card">
          <div className="row between">
            <h2 className="flush" style={{ color: s.subject.color }}>
              {s.subject.name}
            </h2>
            {s.exam && <span className="exam-pill">Contrôle {formatDate(s.exam.date)}</span>}
          </div>
          <table className="mastery-table">
            <thead>
              <tr>
                <th>Leçon</th>
                <th>Étape</th>
                <th>Maîtrise</th>
              </tr>
            </thead>
            <tbody>
              {s.lessons.map((l) => (
                <tr key={l.id}>
                  <td dir="auto">
                    {l.title}
                    {l.open_mistakes > 0 && <span className="muted"> · {l.open_mistakes} erreur{l.open_mistakes > 1 ? "s" : ""}</span>}
                  </td>
                  <td className="muted">{l.step}</td>
                  <td>
                    <span className={`mastery-pill ${COLOR_CLASS[l.color]}`}>{l.mastery} %</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}

      {over.mock_exams.length > 0 && (
        <section className="card">
          <h2 className="flush">Contrôles blancs</h2>
          <ul className="rows">
            {over.mock_exams.map((m) => (
              <li key={m.id} className="row-item">
                <span className="grow">
                  {m.subject} · {formatDate(m.date)}
                </span>
                {m.note !== null && <span className={`badge ${m.note >= 10 ? "badge-ok" : "badge-warn"}`}>{m.note}/20</span>}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="card">
        <h2 className="flush">Seuils de réussite</h2>
        <p className="muted">Pourcentage à atteindre pour valider chaque étape. Baisse-les si c'est trop dur, monte-les pour viser plus haut.</p>
        {SETTINGS.map((s) => (
          <div key={s.key} className="row setting-row">
            <span className="grow">{s.label}</span>
            <input
              className="input input-number"
              type="number"
              min={s.min}
              max={s.max}
              step={5}
              value={settings[s.key] ?? ""}
              onChange={(e) => setSettings((x) => ({ ...x, [s.key]: Number(e.target.value) }))}
              onBlur={(e) => void saveSetting(s.key, Number(e.target.value))}
            />
            <span className="muted">%</span>
          </div>
        ))}
        {saved && <p className="muted">{saved}</p>}
      </section>

      {over.reports.length > 0 && (
        <section className="card">
          <h2 className="flush">Erreurs signalées par l'élève ({over.reports.length})</h2>
          <ul className="rows">
            {over.reports.map((r) => (
              <li key={r.id} className="row-item">
                <span className="grow" dir="auto">
                  <strong>{r.lesson}</strong> — {r.comment}
                </span>
                <span className="muted">{formatDate(r.date)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** Mode parent / frère, protégé par code : progression, maîtrise par chapitre, seuils, signalements. */
export default function Parent() {
  const status = useLoad(() => api.get<{ code_set: boolean }>("/parent/status"), []);
  const [token, setToken] = useState<string | null>(null);
  if (!status.data) {
    return (
      <div className="center">
        <Spinner />
      </div>
    );
  }
  if (!token) return <Gate codeSet={status.data.code_set} onToken={setToken} />;
  return <Overview token={token} onExpired={() => setToken(null)} />;
}
