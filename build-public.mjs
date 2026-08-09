// Regenerates public/index.html from the Artifact source (../ledger-app.html).
// The Artifact source is a fragment (no <html>/<head>/<body> — the Artifact
// platform wraps it); this script wraps it properly for standalone hosting,
// adding the PWA head (manifest, icons, theme-color) and service-worker
// registration. Run this after every edit to ledger-app.html, then commit
// both files together — this is the fix for the two copies drifting apart.
import { readFileSync, writeFileSync } from 'fs';

const fragment = readFileSync('../ledger-app.html', 'utf8');

const head = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>LEDGER — Productivity Terminal</title>
<meta name="description" content="A dark, data-dense habit tracker with XP, streaks, goals-as-portfolios, and an AI productivity analyst.">
<meta name="theme-color" content="#050505">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="LEDGER">
<link rel="manifest" href="/manifest.json">
<link rel="icon" href="/icons/favicon-32.png" sizes="32x32">
<link rel="icon" href="/icons/favicon-16.png" sizes="16x16">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
</head>
<body>
`;

const foot = `
<script>
  if('serviceWorker' in navigator){
    window.addEventListener('load', function(){
      navigator.serviceWorker.register('/sw.js').catch(function(){});
    });
  }
</script>
</body>
</html>
`;

writeFileSync('./public/index.html', head + fragment + foot);
console.log('Built public/index.html from ../ledger-app.html ('+fragment.length+' bytes of app content)');
