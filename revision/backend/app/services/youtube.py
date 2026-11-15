"""Recherche de vidéos avec la YouTube Data API v3.

L'application cherche elle-même : l'élève ne cherche jamais. Les sous-titres ne sont pas
téléchargeables par l'API officielle pour les vidéos d'autrui ; on tente une méthode non
officielle, et on s'en passe si elle échoue.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

import httpx

from .llm import LLMError

log = logging.getLogger("revision.youtube")

API_ROOT = "https://www.googleapis.com/youtube/v3"
MIN_SECONDS, MAX_SECONDS = 120, 45 * 60
_QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}
# Mots qui signalent le bon niveau dans un titre (français et arabe).
_LEVEL_WORDS = ("tronc commun", "tcs", "tcsf", "tct", "tc ", "جذع مشترك", "الجذع المشترك", "جدع مشترك")
_WRONG_LEVEL = ("bac", "terminale", "1ère", "1bac", "2bac", "collège", "3ème", "باك", "الثالثة إعدادي")


class YouTubeUnavailable(Exception):
    """La recherche est impossible pour une raison durable (clé absente ou refusée, quota du jour épuisé)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason  # no_key | key | quota | other


def _get(path: str, params: dict[str, Any], key: str) -> dict[str, Any]:
    try:
        resp = httpx.get(f"{API_ROOT}/{path}", params={**params, "key": key}, timeout=30.0)
    except httpx.TimeoutException as exc:
        raise LLMError("network", f"délai dépassé : {exc}") from exc
    except httpx.TransportError as exc:
        raise LLMError("network", str(exc)) from exc
    if resp.status_code == 200:
        return resp.json()
    try:
        err = resp.json().get("error", {})
    except (ValueError, AttributeError):
        err = {}
    reasons = {e.get("reason") for e in err.get("errors", []) if isinstance(e, dict)}
    message = str(err.get("message") or resp.text[:200])
    if resp.status_code >= 500:
        raise LLMError("server", message)
    if reasons & _QUOTA_REASONS or resp.status_code == 429:
        raise YouTubeUnavailable("quota", message)
    if resp.status_code in (400, 401, 403):
        raise YouTubeUnavailable("key", message)
    raise YouTubeUnavailable("other", message)


def parse_duration(iso: str) -> int:
    """« PT1H2M30S » -> secondes."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    days, hours, minutes, seconds = (int(g or 0) for g in m.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def search(query: str, language: str, key: str, max_results: int = 10) -> list[str]:
    data = _get(
        "search",
        {
            "part": "snippet",
            "type": "video",
            "q": query,
            "maxResults": max_results,
            "relevanceLanguage": language,
            "regionCode": "MA",
            "videoEmbeddable": "true",
            "safeSearch": "strict",
        },
        key,
    )
    return [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]


def details(ids: list[str], key: str) -> list[dict[str, Any]]:
    if not ids:
        return []
    data = _get("videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids[:50])}, key)
    out = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        out.append(
            {
                "id": item.get("id", ""),
                "title": snippet.get("title", ""),
                "channel": snippet.get("channelTitle", ""),
                "description": snippet.get("description", ""),
                "language": snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or "",
                "duration_s": parse_duration(item.get("contentDetails", {}).get("duration", "")),
                "views": int(item.get("statistics", {}).get("viewCount", 0) or 0),
            }
        )
    return out


def heuristic_score(video: dict[str, Any], language: str) -> float:
    """Premier tri sans IA : niveau dans le titre, durée, langue déclarée, audience."""
    text = f"{video.get('title', '')} {video.get('description', '')[:300]}".lower()
    score = 0.0
    if any(w in text for w in _LEVEL_WORDS):
        score += 3
    if any(w in video.get("title", "").lower() for w in _WRONG_LEVEL):
        score -= 2
    duration = video.get("duration_s", 0)
    if 5 * 60 <= duration <= 30 * 60:
        score += 2
    elif MIN_SECONDS <= duration <= MAX_SECONDS:
        score += 1
    if video.get("language", "").lower().startswith(language):
        score += 1
    views = video.get("views", 0)
    score += 1 if views > 10_000 else 0.5 if views > 1_000 else 0
    return score


def transcript_excerpt(video_id: str, languages: list[str], max_chars: int = 800) -> Optional[str]:
    """Début des sous-titres, si la bibliothèque non officielle est installée et que YouTube répond."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001
        return None
    try:
        if hasattr(YouTubeTranscriptApi, "fetch"):  # versions récentes
            fetched = YouTubeTranscriptApi().fetch(video_id, languages=languages)
            parts = [getattr(s, "text", "") or (s.get("text", "") if isinstance(s, dict) else "") for s in fetched]
        else:  # anciennes versions
            parts = [s.get("text", "") for s in YouTubeTranscriptApi.get_transcript(video_id, languages=languages)]
    except Exception as exc:  # noqa: BLE001 - sous-titres absents, vidéo bloquée, réseau...
        log.info("sous-titres indisponibles pour %s : %s", video_id, type(exc).__name__)
        return None
    text = " ".join(p.strip() for p in parts if p).strip()
    return text[:max_chars] or None
