import type { Lang, MindMap as MindMapData } from "../api";
import { Md } from "./Md";

const COLORS = ["#7c9cff", "#4fd1a5", "#f5b84a", "#ff8fa3", "#c79bff", "#5cc8f0"];

/** Carte mentale : un centre, des branches colorées, des feuilles. Lisible et imprimable. */
export function MindMap({ map, lang }: { map: MindMapData; lang: Lang }) {
  const dir = lang === "ar" ? "rtl" : "ltr";
  return (
    <div className="mindmap" dir={dir}>
      <div className="mindmap-center">
        <Md inline text={map.centre} lang={lang} />
      </div>
      <div className="mindmap-branches">
        {map.branches.map((b, i) => (
          <div key={i} className="mindmap-branch" style={{ ["--branch" as string]: COLORS[i % COLORS.length] }}>
            <div className="mindmap-branch-title">
              <Md inline text={b.titre} lang={lang} />
            </div>
            <ul>
              {b.feuilles.map((f, j) => (
                <li key={j}>
                  <Md inline text={f} lang={lang} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}
