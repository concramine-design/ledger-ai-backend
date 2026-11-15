"""Lance l'application et ouvre le navigateur. Utilisé par lancer.bat."""
from __future__ import annotations

import threading
import time
import webbrowser

import httpx
import uvicorn

from .config import get_config


def _is_ours(url: str) -> bool:
    try:
        data = httpx.get(f"{url}/api/health", timeout=1.5).json()
        return data.get("app") == "revision"
    except Exception:  # noqa: BLE001
        return False


def _open_when_ready(url: str) -> None:
    for _ in range(60):
        if _is_ours(url):
            webbrowser.open(url)
            return
        time.sleep(0.5)


def main() -> None:
    cfg = get_config()
    url = f"http://127.0.0.1:{cfg.port}"
    if _is_ours(url):
        print("L'application tourne deja : ouverture du navigateur.")
        webbrowser.open(url)
        return
    print("=" * 60)
    print("  Mes revisions")
    print(f"  Adresse : {url}")
    print("  Laisse cette fenetre ouverte pendant que tu revises.")
    print("  Pour arreter : ferme cette fenetre.")
    print("=" * 60)
    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run("app.main:app", host="127.0.0.1", port=cfg.port, log_level="warning")


if __name__ == "__main__":
    main()
