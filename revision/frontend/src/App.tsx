import { createContext, useContext, useEffect } from "react";
import { BrowserRouter, Navigate, NavLink, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { api, type AppState } from "./api";
import { Notice, Spinner } from "./components/Ui";
import { useLoad } from "./hooks";
import Home from "./pages/Home";
import ImportPage from "./pages/ImportPage";
import LessonPage from "./pages/LessonPage";
import ControleBlanc, { ControlesList } from "./pages/ControleBlanc";
import Devoirs from "./pages/Devoirs";
import Lessons from "./pages/Lessons";
import Methods from "./pages/Methods";
import Mistakes from "./pages/Mistakes";
import Onboarding from "./pages/Onboarding";
import Parent from "./pages/Parent";
import Planning from "./pages/Planning";
import Revision from "./pages/Revision";
import Settings from "./pages/Settings";
import StepPage from "./pages/StepPage";
import { FocusTimer } from "./components/FocusTimer";

interface AppCtx {
  state: AppState;
  refresh: () => Promise<void>;
}

const Ctx = createContext<AppCtx | null>(null);

export function useApp(): AppCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("contexte absent");
  return ctx;
}

function Shell() {
  const { state } = useApp();
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0); // chaque écran s'ouvre en haut de page
  }, [pathname]);
  if (!state.onboarded) return <Navigate to="/bienvenue" replace />;
  return (
    <div className="shell">
      <header className="topbar no-print">
        <NavLink to="/" className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          Mes révisions
        </NavLink>
        <nav>
          <NavLink to="/" end>
            Accueil
          </NavLink>
          <NavLink to="/planning">Planning</NavLink>
          <NavLink to="/lecons">Mes leçons</NavLink>
          <NavLink to="/controles">Contrôle blanc</NavLink>
          <NavLink to="/importer">Importer</NavLink>
          <NavLink to="/reglages">Réglages</NavLink>
        </nav>
      </header>
      {state.ai.demo && (
        <div className="banner banner-demo no-print">
          Mode démonstration : l'IA est simulée. Les contenus sont factices. Ajoute une clé dans le fichier .env pour de vraies explications.
        </div>
      )}
      {!state.ai.configured && (
        <div className="banner banner-warn no-print">
          Aucune clé d'IA n'est configurée : rien ne peut être généré. Remplis le fichier .env, puis relance l'application.
        </div>
      )}
      <main className="main">
        <Outlet />
      </main>
      <FocusTimer />
    </div>
  );
}

export default function App() {
  const { data, error, reload } = useLoad(() => api.get<AppState>("/state"), []);
  if (error) {
    return (
      <div className="center-screen">
        <Notice tone="bad">
          <p>{error.message}</p>
          <button className="btn btn-small" onClick={() => void reload()}>
            Réessayer
          </button>
        </Notice>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="center-screen">
        <Spinner />
      </div>
    );
  }
  return (
    <Ctx.Provider value={{ state: data, refresh: reload }}>
      <BrowserRouter>
        <Routes>
          <Route path="/bienvenue" element={<Onboarding />} />
          <Route element={<Shell />}>
            <Route index element={<Home />} />
            <Route path="importer" element={<ImportPage />} />
            <Route path="lecons" element={<Lessons />} />
            <Route path="lecon/:id" element={<LessonPage />} />
            <Route path="lecon/:id/:step" element={<StepPage />} />
            <Route path="revision" element={<Revision />} />
            <Route path="planning" element={<Planning />} />
            <Route path="erreurs" element={<Mistakes />} />
            <Route path="chapitre/:id/methodes" element={<Methods />} />
            <Route path="controles" element={<ControlesList />} />
            <Route path="controle/:id" element={<ControleBlanc />} />
            <Route path="anciens-devoirs" element={<Devoirs />} />
            <Route path="parent" element={<Parent />} />
            <Route path="reglages" element={<Settings />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </Ctx.Provider>
  );
}
