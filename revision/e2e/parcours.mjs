// Parcours complet dans un vrai navigateur, avec l'IA simulée.
// Lancer le serveur avec LLM_PROVIDER=mock et un dossier de données vide, puis :
//   node e2e/parcours.mjs [http://127.0.0.1:8765] [dossier-captures]
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { chromium } = require("playwright");

const BASE = process.argv[2] ?? "http://127.0.0.1:8765";
const SHOTS = process.argv[3] ?? null;

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
  check(options.filter(([, d]) => !d).length === 2 && options.some(([t]) => t.includes("SVT (bientôt)")), "seules Maths et Physique-Chimie sont ouvertes en V1");
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
  check((await page.locator(".step-locked").count()) === 7, "les étapes suivantes sont verrouillées");
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

  console.log("9. Exercices : tentative, retour, correction en dernier recours, nouvel exercice");
  await page.getByRole("link", { name: /Continuer/ }).click();
  await heading("Exercices niveau 1").waitFor();
  const first = page.locator(".exercise").first();
  check(await first.getByText(/Essaie d'abord/).isVisible(), "pas de correction avant une tentative");
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
  check((await page.locator(".step-done").count()) === 8, "toutes les étapes sont allumées");
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

  console.log("12. Mes leçons et réglages");
  await page.goto(`${BASE}/lecons`);
  await page.getByText("Maîtrisée").waitFor();
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
