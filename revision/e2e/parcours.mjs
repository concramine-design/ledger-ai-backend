// Parcours complet dans un vrai navigateur, avec l'IA simulée.
// Lancer le serveur avec LLM_PROVIDER=mock et un dossier de données vide, puis :
//   node e2e/parcours.mjs [http://127.0.0.1:8765] [dossier-captures] [chemin de revision.db]
// Le chemin de la base sert à avancer les dates des rappels (sinon cette partie est ignorée).
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://127.0.0.1:8765";
const SHOTS = process.argv[3] || null;
const DB = process.argv[4] || null;

/** Fait comme si le temps avait passé : tous les rappels deviennent dus aujourd'hui. */
function makeReviewsDue() {
  const sql = "UPDATE review_items SET due = date('now', 'localtime') WHERE state = 'active'";
  execFileSync("python3", ["-c", `import sqlite3, sys; c = sqlite3.connect(sys.argv[1], timeout=30); c.execute(sys.argv[2]); c.commit()`, DB, sql]);
}

const LESSON = `Une fonction numérique associe à chaque nombre réel x au plus une image notée f(x).
L'ensemble de définition regroupe tous les réels x pour lesquels f(x) existe.
Pour une fonction rationnelle, le dénominateur doit être différent de zéro.
Pour une racine carrée, l'expression sous la racine doit être positive ou nulle.
La courbe représentative est l'ensemble des points de coordonnées (x ; f(x)).
Une fonction est paire lorsque f(-x) = f(x) pour tout x de son ensemble de définition.
Une fonction est impaire lorsque f(-x) = -f(x) pour tout x de son ensemble de définition.
Une fonction est croissante sur un intervalle lorsque les images sont rangées dans le même ordre que les antécédents.`;

const LECON_ARABE = `الدالة العددية علاقة تربط كل عدد حقيقي بصورة وحيدة على الأكثر.
مجموعة تعريف الدالة هي مجموعة الأعداد الحقيقية التي لها صورة.
في الدالة الجذرية يجب أن يكون المقام مخالفا للصفر.
في الجذر المربع يجب أن يكون ما تحت الجذر موجبا أو منعدما.
التمثيل المبياني للدالة هو مجموعة النقط ذات الإحداثيات المناسبة.
تكون الدالة زوجية إذا كانت صورة العدد وصورة مقابله متساويتين.`;

let step = 0;
const errors = [];
const ok = (label) => console.log(`  ✓ ${label}`);
function check(cond, label) {
  if (!cond) throw new Error(`ÉCHEC : ${label}`);
  ok(label);
}

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, locale: "fr-FR" });
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
// Les refus 403 sont voulus : le test vérifie que les étapes verrouillées sont bien refusées.
page.on("console", (m) => m.type() === "error" && !m.text().includes("status of 403") && errors.push(`console: ${m.text()}`));

async function shot(name) {
  if (!SHOTS) return;
  step += 1;
  await page.screenshot({ path: `${SHOTS}/${String(step).padStart(2, "0")}-${name}.png`, fullPage: true });
}
const btn = (name) => page.getByRole("button", { name });
const heading = (name) => page.getByRole("heading", { name });

/** Répond à la question affichée (règles de l'IA simulée). */
async function answerQuestion(good) {
  await page.locator(".question").waitFor();
  const radios = page.locator(".choice");
  if ((await radios.count()) > 0) {
    const texts = await radios.allTextContents();
    const right = texts.findIndex((t) => !t.includes("n'apparaît pas"));
    const wrong = texts.findIndex((t) => t.includes("n'apparaît pas"));
    await radios.nth(good ? right : wrong).click();
  } else {
    const enonce = await page.locator(".question .enonce").innerText();
    const quoted = enonce.match(/«\s*([\s\S]+?)\s*»/);
    await page.locator(".question textarea").fill(good ? quoted[1] : "aucune idée");
  }
  await btn("Valider ma réponse").click();
  await page.locator(".correction").waitFor();
}

async function takeTest(good, shotName) {
  for (;;) {
    await answerQuestion(good);
    if (shotName) {
      await shot(shotName);
      shotName = null;
    }
    const next = btn("Question suivante");
    if (await next.count()) await next.click();
    else break;
  }
  await btn("Voir mon résultat").click();
}

async function solveExercise(card, good) {
  const enonce = await card.locator(".enonce").innerText();
  const quoted = enonce.match(/«\s*([\s\S]+?)\s*»/);
  await card.locator("textarea").fill(good ? quoted[1] : "aucune idée");
  await card.getByRole("button", { name: /Vérifier/ }).click();
  await card.locator(".feedback").waitFor();
}

try {
  console.log("1. Premier lancement");
  await page.goto(BASE);
  await heading("Tes matières").waitFor();
  check(page.url().endsWith("/bienvenue"), "redirection vers le premier lancement");
  check((await page.locator(".row-item").count()) === 7, "7 matières préconfigurées");
  await shot("bienvenue-matieres");
  await btn("Suivant").click();
  await heading("La langue de chaque matière").waitFor();
  const pc = page.locator(".row-item", { hasText: "Physique-Chimie" });
  await pc.getByRole("button", { name: "Arabe" }).click();
  await page.waitForFunction(() => document.querySelectorAll('.row-item')[1]?.querySelector('button.active')?.textContent === 'Arabe');
  ok("langue de Physique-Chimie réglée sur l'arabe");
  await shot("bienvenue-langues");
  await btn("Suivant").click();
  await heading("Tes prochains contrôles").waitFor();
  const future = new Date(Date.now() + 6 * 86400000).toISOString().slice(0, 10);
  await page.getByLabel("Date du contrôle").fill(future);
  await page.getByPlaceholder(/Titre/).fill("DS n°1");
  await btn("Ajouter").click();
  await page.getByText("DS n°1").waitFor();
  await shot("bienvenue-controles");
  await btn("C'est parti").click();

  console.log("2. Accueil et import");
  await heading("Importe ta première leçon").waitFor();
  await shot("accueil-vide");
  await page.getByRole("link", { name: /Importer une leçon/ }).click();
  await heading("Importer une leçon").waitFor();
  const options = await page.locator("select").first().locator("option").evaluateAll((os) => os.map((o) => [o.textContent, o.disabled]));
  check(options.length === 7 && options.every(([, d]) => !d), "les 7 matières sont ouvertes à l'import");
  await page.getByPlaceholder("Ex. : Les fonctions").fill("Les fonctions");
  await page.getByPlaceholder("Ex. : Ensemble de définition").fill("Généralités sur les fonctions");
  await page.getByRole("tab", { name: "Texte collé" }).click();
  await page.locator("textarea").fill(LESSON);
  await shot("import");
  await btn("Importer et préparer ma leçon").click();

  console.log("3. Génération automatique en arrière-plan");
  await heading("Généralités sur les fonctions").waitFor();
  await page.getByRole("link", { name: /Continuer/ }).waitFor({ timeout: 30000 });
  ok("l'étape « Comprendre » est prête sans autre action");
  await page.waitForFunction(() => !document.querySelector(".preparing"), null, { timeout: 30000 });
  check((await page.locator(".step-locked").count()) === 9, "les étapes suivantes sont verrouillées");
  check(await page.getByRole("link", { name: /méthodes types/ }).isVisible(), "la fiche « méthodes types » est prête");
  await shot("parcours");

  await page.goto(BASE);
  await heading("Comprendre").waitFor();
  check(await page.getByText("Contrôle dans 6 jours").isVisible(), "l'accueil rappelle la date du contrôle");
  await shot("accueil-prochaine-etape");

  console.log("4. Étape verrouillée refusée par le serveur");
  const lessonId = await page.getByRole("link", { name: /Continuer/ }).getAttribute("href").then((h) => h.split("/")[2]);
  await page.goto(`${BASE}/lecon/${lessonId}/quiz`);
  await page.getByText(/Étape verrouillée/).waitFor();
  ok("accès direct au quiz refusé");

  console.log("5. Comprendre + chat");
  await page.goto(`${BASE}/lecon/${lessonId}/comprendre`);
  await page.locator(".lesson-card").waitFor();
  check((await page.locator(".katex").count()) > 0, "formules rendues avec KaTeX");
  check((await page.locator(".katex-error").count()) === 0, "aucune formule en erreur");
  check((await page.locator(".mindmap-branch").count()) >= 2, "la carte mentale de la leçon s'affiche");
  await shot("comprendre-carte-mentale");
  await btn("Poser une question").click();
  await page.getByPlaceholder("Écris ta question…").fill("C'est quoi une fonction paire ?");
  await btn("Envoyer").click();
  await page.locator(".bubble-assistant .md").waitFor();
  check((await page.locator(".bubble-assistant .md").innerText()).trim().endsWith("?"), "le chat répond d'abord par une question");
  await shot("comprendre-chat");
  await page.getByLabel("Fermer le chat").click();
  while (await btn("Suivant").count()) await btn("Suivant").click();
  await btn(/J'ai compris/).click();
  await page.getByText("Étape validée").waitFor();

  console.log("6. Mini-test réussi");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Mini-test").waitFor();
  await takeTest(true, "minitest-correction");
  await heading("Mini-test réussi").waitFor();
  await shot("minitest-reussi");
  await btn("Continuer").click();

  console.log("6b. Feuille blanche");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Feuille blanche").waitFor();
  await page.locator(".answer-box textarea").fill(LESSON);
  await btn("Comparer avec la leçon").click();
  await page.locator(".element-ok").first().waitFor();
  check(await page.locator(".badge", { hasText: "100 % de la leçon" }).first().isVisible(), "la feuille blanche est comparée à la leçon");
  await shot("feuille-blanche");
  await page.locator(".notice-ok").getByText("Continuer").click();

  console.log("7. Résumé");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await page.locator(".fiche").waitFor();
  check(await btn("Exporter en PDF").isVisible(), "bouton d'export PDF présent");
  const sizes = await page.locator(".fiche .katex").first().evaluate((el) => {
    const sup = el.querySelector(".msupsub .mtight");
    return [parseFloat(getComputedStyle(el).fontSize), sup ? parseFloat(getComputedStyle(sup).fontSize) : 0];
  });
  check(sizes[1] > 0 && sizes[1] < sizes[0] * 0.85, "les exposants des formules sont plus petits que la base");
  await shot("resume");
  await page.emulateMedia({ media: "print" });
  check(!(await page.locator(".topbar").isVisible()), "la barre de navigation disparaît à l'impression");
  if (SHOTS) await page.pdf({ path: `${SHOTS}/fiche.pdf`, format: "A4" });
  await page.emulateMedia({ media: "screen" });
  await btn(/J'ai lu ma fiche/).click();

  console.log("8. Quiz raté, ré-explication, puis quiz réussi");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Quiz complet").waitFor();
  check(await page.getByText("Objectif : 80 %").isVisible(), "seuil de 80 % affiché");
  await takeTest(false, null);
  await heading(/Pas encore/).waitFor();
  await page.locator(".lesson-card").first().waitFor({ timeout: 30000 });
  ok("les points ratés sont réexpliqués autrement");
  await btn(/Passer le nouveau quiz/).waitFor({ timeout: 30000 });
  await shot("quiz-rate-reexplication");
  await page.goto(`${BASE}/lecon/${lessonId}/ex1`);
  await page.getByText(/Étape verrouillée/).waitFor();
  ok("exercices toujours verrouillés après un quiz raté");
  await page.goto(`${BASE}/lecon/${lessonId}/quiz`);
  await btn(/Passer le nouveau quiz/).click();
  await takeTest(true, "quiz-question-ouverte");
  await heading("Quiz réussi").waitFor();
  await btn("Continuer").click();

  console.log("8b. Explique-moi");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Explique-moi").waitFor();
  const explanation = "Une fonction associe à chaque nombre une seule image. L'ensemble de définition regroupe les nombres qui ont une image, et la courbe montre tous les points.";
  for (let i = 0; i < 3; i++) {
    await page.locator(".chat-form textarea").fill(explanation + " Voila mon explication complete numero " + i + ".");
    await page.getByRole("button", { name: /Expliquer|Répondre/ }).click();
    await page.waitForFunction((n) => document.querySelectorAll(".talk .bubble-user").length > n, i, { timeout: 30000 });
  }
  await page.locator(".feedback").waitFor();
  check(await page.getByText(/C'est clair/).isVisible(), "l'IA évalue la clarté de l'explication");
  await shot("explique-moi");
  await page.getByRole("button", { name: /Continuer/ }).click();

  console.log("9. Exercices : tentative, retour, correction en dernier recours, nouvel exercice");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Exercices niveau 1").waitFor();
  const first = page.locator(".exercise").first();
  check(await first.getByText(/Essaie d'abord/).isVisible(), "pas de correction avant une tentative");
  await first.getByRole("button", { name: /Indice 1\/3/ }).click();
  await first.locator(".hints li").first().waitFor();
  await first.getByRole("button", { name: /Indice 2\/3/ }).click();
  await page.waitForFunction(() => document.querySelectorAll(".exercise")[0].querySelectorAll(".hints li").length === 2);
  check((await first.locator(".solution").count()) === 0, "les indices arrivent un par un, sans la correction");
  await shot("exercice-indices");
  await solveExercise(first, false);
  check(await first.getByText("À retenter").isVisible(), "une mauvaise réponse laisse l'exercice à retenter");
  check((await first.locator(".solution").count()) === 0, "la correction reste cachée");
  await first.getByRole("button", { name: "Voir la correction détaillée" }).click();
  await shot("exercice-confirmation");
  await page.getByRole("dialog").getByRole("button", { name: "Voir la correction" }).click();
  await first.locator(".solution").waitFor();
  await page.locator(".exercise").nth(3).waitFor({ timeout: 30000 });
  ok("un nouvel exercice du même type est préparé");
  await shot("exercice-correction");
  await solveExercise(page.locator(".exercise").nth(1), true);
  await solveExercise(page.locator(".exercise").nth(2), true);
  await page.getByText("Niveau validé.").waitFor();
  await shot("exercices-niveau-valide");
  await page.locator(".notice").getByRole("button", { name: /Continuer/ }).click();

  for (const level of [2, 3]) {
    await page.getByRole("link", { name: /Continuer/ }).click();
    await heading(`Exercices niveau ${level}`).waitFor();
    await solveExercise(page.locator(".exercise").nth(0), true);
    await solveExercise(page.locator(".exercise").nth(1), true);
    await page.getByText(level === 3 ? "Leçon maîtrisée." : "Niveau validé.").waitFor();
    await page.locator(".notice").getByRole("button", { name: /Continuer/ }).click();
  }

  console.log("10. Leçon maîtrisée");
  await page.locator(".path").waitFor();
  await page.locator(".notice").getByText(/Leçon maîtrisée/).waitFor();
  check((await page.locator(".step-done").count()) === 10, "toutes les étapes sont allumées");
  await shot("lecon-maitrisee");
  await page.goto(BASE);
  await heading("Tout est maîtrisé").waitFor();

  console.log("11. Leçon en arabe : écriture de droite à gauche");
  await page.goto(`${BASE}/importer`);
  await page.locator("select").first().selectOption({ label: "Physique-Chimie" });
  await page.getByText("Explications et exercices en arabe.").waitFor();
  await page.getByPlaceholder("Ex. : Les fonctions").fill("الدوال العددية");
  await page.getByPlaceholder("Ex. : Ensemble de définition").fill("عموميات حول الدوال");
  await page.getByRole("tab", { name: "Texte collé" }).click();
  await page.locator("textarea").fill(LECON_ARABE);
  await btn("Importer et préparer ma leçon").click();
  await page.getByRole("link", { name: /Continuer/ }).waitFor({ timeout: 30000 });
  await page.getByRole("link", { name: /Continuer/ }).click();
  await page.locator(".lesson-card").waitFor();
  const dir = await page.locator(".lesson-card .md").first().getAttribute("dir");
  check(dir === "rtl", "le contenu arabe s'affiche de droite à gauche");
  const katexDir = await page.locator(".katex").first().evaluate((el) => getComputedStyle(el).direction);
  check(katexDir === "ltr", "les formules restent de gauche à droite");
  await shot("lecon-arabe");

  console.log("12. Carnet d'erreurs, méthodes types");
  await page.goto(`${BASE}/erreurs`);
  await heading("Carnet d'erreurs").waitFor();
  check((await page.locator(".mistake").count()) === 7, "les 6 erreurs du quiz raté et l'exercice corrigé sont au carnet");
  await page.locator(".mistake summary").first().click();
  await shot("carnet-erreurs");
  await page.goto(`${BASE}/lecons`);
  await page.getByRole("link", { name: /Généralités sur les fonctions/ }).click();
  await page.getByRole("link", { name: /méthodes types/ }).click();
  await heading("Méthodes types").waitFor();
  check((await page.locator(".method-type").count()) >= 1, "la fiche « méthodes types » liste les types d'exercices");
  await shot("methodes-types");

  /** Avance une leçon par l'API jusqu'à l'étape voulue (les écrans correspondants sont déjà testés plus haut). */
  async function fastForward(id, until) {
    const post = async (path, data) => (await page.request.post(`${BASE}/api${path}`, data ? { data } : undefined)).json();
    const get = async (path) => (await page.request.get(`${BASE}/api${path}`)).json();
    const quoted = (text) => text.match(/«\s*([\s\S]+?)\s*»/)[1];
    const answerTest = async (key, skipSchema) => {
      const step = await get(`/lessons/${id}/steps/${key}`);
      for (const q of step.set.questions) {
        if (q.type === "schema") {
          if (!skipSchema) await post(`/questions/${q.id}/answer`, { labels: q.schema.banque });
        } else if (q.type === "qcm") {
          await post(`/questions/${q.id}/answer`, { choice_index: q.choix.findIndex((c) => !c.includes("n'apparaît pas")) });
        } else {
          await post(`/questions/${q.id}/answer`, { answer_text: quoted(q.enonce) });
        }
      }
    };
    const order = ["comprendre", "minitest", "feuille", "resume", "quiz", "explique", "ex1", "ex2", "ex3"];
    const longText = "Je pense que cette idee est importante parce qu'elle explique le monde. ".repeat(6);
    for (const key of order.slice(0, order.indexOf(until))) {
      if (key === "comprendre" || key === "resume") await post(`/lessons/${id}/steps/${key}/validate`);
      else if (key === "minitest" || key === "quiz") await answerTest(key, false);
      else if (key === "feuille") await post(`/lessons/${id}/steps/feuille/submit`, { text: LESSON });
      else if (key === "explique") { for (let k = 0; k < 3; k++) await post(`/lessons/${id}/steps/explique/message`, { text: longText }); }
      else {
        const step = await get(`/lessons/${id}/steps/${key}`);
        for (const ex of step.exercises.slice(0, step.progress.required)) await post(`/questions/${ex.id}/answer`, { answer_text: quoted(ex.enonce) });
      }
    }
  }

  async function importLesson(subject, chapter, title, text) {
    await page.goto(`${BASE}/importer`);
    await page.locator("select").first().selectOption({ label: subject });
    await page.getByPlaceholder("Ex. : Les fonctions").fill(chapter);
    await page.getByPlaceholder("Ex. : Ensemble de définition").fill(title);
    await page.getByRole("tab", { name: "Texte collé" }).click();
    await page.locator("textarea").fill(text);
    await btn("Importer et préparer ma leçon").click();
    await heading(title).waitFor();
    await page.waitForFunction(() => !document.querySelector(".preparing"), null, { timeout: 60000 });
    return page.url().split("/").pop();
  }

  console.log("13. Français : fiche avec vocabulaire, production écrite corrigée sans réécriture");
  const fr = await importLesson("Français", "La phrase", "L'accord du participe passé", LESSON);
  await fastForward(fr, "resume");
  await page.goto(`${BASE}/lecon/${fr}/resume`);
  await heading("Vocabulaire").waitFor();
  check(await heading("Règles").isVisible(), "la fiche d'une langue parle de règles, pas de formules");
  await shot("francais-fiche");
  await fastForward(fr, "ex3");
  await page.goto(`${BASE}/lecon/${fr}/ex3`);
  const sujet = page.locator(".exercise").first();
  await sujet.locator("textarea").waitFor();
  check((await sujet.locator(".symbols").count()) === 0, "pas de barre de symboles mathématiques en français");
  await sujet.locator("textarea").fill("Je pense que cette idée est importante pour nous tous.");
  await sujet.getByRole("button", { name: /Vérifier/ }).click();
  await sujet.locator(".faults").waitFor();
  check((await sujet.locator(".criteria li").count()) === 4, "la copie est notée sur 4 critères");
  check(await sujet.getByText("Tes fautes, à corriger toi-même").isVisible(), "les fautes sont expliquées, pas corrigées à sa place");
  await shot("francais-production-ecrite");
  await sujet.locator("textarea").fill(Array(8).fill("Je pense que cette idée est importante parce qu'elle explique le monde.").join(" "));
  await sujet.getByRole("button", { name: /Vérifier/ }).click();
  await page.getByText("Leçon maîtrisée.").waitFor();

  console.log("14. SVT : schéma à légender et analyse de documents");
  const svt = await importLesson("SVT", "La respiration", "Les échanges gazeux", LESSON);
  await fastForward(svt, "quiz");
  await page.goto(`${BASE}/lecon/${svt}/quiz`);
  await page.locator(".question").waitFor();
  for (;;) {
    if (await page.locator(".schema").count()) break;
    await answerQuestion(true);
    await btn("Question suivante").click();
  }
  check((await page.locator(".schema-box").count()) === 4, "le schéma affiche ses cases numérotées");
  const selects = page.locator(".schema-box select");
  for (let i = 0; i < 4; i++) await selects.nth(i).selectOption({ label: `Étape ${i === 3 ? 1 : i + 1}` });
  await btn("Valider ma réponse").click();
  await page.locator(".correction").waitFor();
  check((await page.locator(".schema-box.right").count()) === 3 && (await page.locator(".schema-box.wrong").count()) === 1, "chaque case du schéma est corrigée");
  await shot("svt-schema");
  await btn("Voir mon résultat").click();
  await heading("Quiz réussi").waitFor();
  await fastForward(svt, "ex2");
  await page.goto(`${BASE}/lecon/${svt}/ex2`);
  await page.locator(".document table").first().waitFor();
  ok("les exercices de SVT donnent un document à analyser");
  await shot("svt-document");

  if (DB) {
    console.log("15. Révision du jour : rappels, erreurs reposées, cartes mémoire");
    await page.waitForTimeout(1500); // laisse la file préparer les questions des rappels
    makeReviewsDue();
    await page.goto(BASE);
    await heading("Révision du jour").waitFor();
    check(await page.getByText(/à revoir aujourd'hui/).isVisible(), "l'accueil propose d'abord la révision du jour");
    await shot("accueil-revision");
    await page.goto(`${BASE}/planning`);
    await heading("Mon planning").waitFor();
    check((await page.locator(".calendar li").count()) === 14, "le planning montre les 14 prochains jours");
    await shot("planning");
    await page.getByRole("link", { name: /Commencer/ }).click();
    const subjects = new Set();
    let questions = 0;
    let cards = 0;
    const counter = page.locator(".page > .row.between > .muted").first();
    const stepChanged = (previous) =>
      page.waitForFunction(
        (prev) => {
          const done = document.querySelector(".next h1")?.textContent === "Séance terminée";
          const now = document.querySelector(".page > .row.between > .muted")?.textContent;
          return done || (now && now !== prev);
        },
        previous,
        { timeout: 30000 },
      );
    await counter.waitFor();
    for (;;) {
      if (await heading("Séance terminée").count()) break;
      const position = await counter.innerText();
      subjects.add(await page.locator(".page .chip").first().innerText());
      if (await page.locator(".flashcard").count()) {
        if (cards === 0) await shot("revision-carte");
        await btn("Voir la réponse").click();
        await btn(cards % 2 ? "Pas encore" : "Je savais").click();
        cards += 1;
      } else {
        await answerQuestion(true);
        if (questions === 0) await shot("revision-question");
        questions += 1;
        await page.getByRole("button", { name: /Suivant|Terminer la séance/ }).click();
      }
      await stepChanged(position);
    }
    check(questions > 0 && cards > 0, `la séance enchaîne ${questions} questions et ${cards} cartes mémoire`);
    check(subjects.size >= 2, `la séance mélange plusieurs matières (${[...subjects].join(", ")})`);
    await shot("revision-terminee");
  } else {
    console.log("15. Révision du jour : ignorée (chemin de la base non fourni)");
  }

  console.log("16. Contrôle blanc chronométré, noté sur 20");
  await page.goto(`${BASE}/controles`);
  await page.getByRole("heading", { name: "Contrôle blanc", exact: true }).waitFor();
  await page.locator("select").first().selectOption({ label: "Maths" });
  await btn("Préparer le sujet").click();
  await heading("Prête pour l'épreuve ?").waitFor({ timeout: 40000 });
  await shot("controle-salle-attente");
  await btn(/Commencer l'épreuve/).click();
  await page.locator(".exam-timer").waitFor();
  check(await page.locator(".exam-timer").isVisible(), "le chronomètre de l'épreuve tourne");
  const examQuestions = await page.locator(".exam-question").count();
  check(examQuestions >= 2, "le sujet contient plusieurs questions");
  for (let i = 0; i < examQuestions; i++) {
    const q = page.locator(".exam-question").nth(i);
    const head = await q.locator(".exam-question-head").innerText();
    const answer = head.includes("«") ? head.split("«")[1].split("»")[0].trim() : "une reponse";
    await q.locator("textarea").fill(answer);
  }
  await shot("controle-epreuve");
  page.once("dialog", (d) => d.accept());
  await btn("Rendre ma copie").click();
  await page.locator(".result-score").waitFor({ timeout: 40000 });
  const note = await page.locator(".result-score").innerText();
  check(/\/20$/.test(note.trim()), `la copie est notée sur 20 (${note.trim()})`);
  check(await page.getByText("Points à retravailler").isVisible(), "le bilan des points à retravailler s'affiche");
  await shot("controle-resultat");

  console.log("17. Mode parent protégé par code");
  await page.goto(`${BASE}/parent`);
  await heading("Espace parent / frère").waitFor();
  await page.getByPlaceholder("Code", { exact: true }).fill("2468");
  await page.getByPlaceholder("Confirme le code").fill("2468");
  await btn("Créer le code").click();
  await page.locator(".mastery-table tbody tr").first().waitFor({ timeout: 20000 });
  check((await page.locator(".mastery-table tbody tr").count()) >= 1, "la progression par leçon s'affiche dans l'espace parent");
  check((await page.locator(".mastery-pill").count()) >= 1, "le score de maîtrise est coloré (rouge/orange/vert)");
  await shot("mode-parent");
  // Le code protège l'accès : nouvelle visite sans jeton -> retour à l'écran de code.
  await page.goto(`${BASE}/parent`);
  await page.getByPlaceholder("Code", { exact: true }).waitFor();
  ok("l'espace parent redemande le code à chaque visite");

  console.log("18. Série de jours et minuteur sur l'accueil");
  await page.goto(BASE);
  await page.locator(".streak").waitFor();
  check(await page.locator(".streak").isVisible(), "la série de jours est affichée");
  await page.locator(".timer-fab").click();
  await page.locator(".timer-time").waitFor();
  check(await page.getByText("25:00").isVisible(), "le minuteur de séance (25 min) s'ouvre");
  await shot("minuteur");

  console.log("19. Mes leçons et réglages");
  await page.goto(`${BASE}/lecons`);
  await page.getByText("Maîtrisée").first().waitFor();
  check((await page.locator(".chapter-dot").count()) >= 1, "les chapitres ont une pastille rouge/orange/vert");
  await shot("mes-lecons");
  await page.goto(`${BASE}/reglages`);
  await heading("Réglages").waitFor();
  await shot("reglages");

  check(errors.length === 0, `aucune erreur JavaScript${errors.length ? " : " + errors.join(" | ") : ""}`);
  console.log("\nParcours complet réussi.");
} catch (e) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/ECHEC.png`, fullPage: true });
  console.error(`\n${e.message}`);
  if (errors.length) console.error(errors.join("\n"));
  process.exitCode = 1;
} finally {
  await browser.close();
}
