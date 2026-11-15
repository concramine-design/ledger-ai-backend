import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import type { Lang } from "../api";

/** L'IA écrit parfois \( ... \) ou \[ ... \] : on ramène tout à $ ... $. */
function normalize(text: string): string {
  return text
    .replace(/\\\[([\s\S]+?)\\\]/g, (_m, f: string) => "$$" + f + "$$")
    .replace(/\\\(([\s\S]+?)\\\)/g, (_m, f: string) => "$" + f + "$");
}

interface Props {
  text: string;
  lang?: Lang;
  inline?: boolean;
  className?: string;
}

/** Texte généré : Markdown, formules KaTeX, sens d'écriture selon la langue de la matière. */
export function Md({ text, lang, inline, className }: Props) {
  const dir = lang === "ar" ? "rtl" : lang ? "ltr" : "auto";
  const Tag = inline ? "span" : "div";
  return (
    <Tag className={`md ${inline ? "md-inline" : ""} ${className ?? ""}`} dir={dir} lang={lang}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }]]}
        components={inline ? { p: ({ children }) => <span>{children}</span> } : undefined}
      >
        {normalize(text ?? "")}
      </ReactMarkdown>
    </Tag>
  );
}
