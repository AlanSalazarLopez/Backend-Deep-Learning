"""Diagnóstico de idioma de un canal (~8 unidades de cuota por canal).

Uso (desde backend/):
  python -m scripts.lang_debug '@auron' '@godeik' '@alfredolarin'
Para cada canal imprime:
  - lo que DECLARA YouTube: defaultLanguage del canal y defaultAudioLanguage / defaultLanguage de sus videos
    (cuántos videos lo traen y con qué valores). Es gratis en la ingesta, pero solo existe si el creador lo llenó.
  - lo que DETECTA langdetect: reparto de idiomas y la decisión de detect_language.
"""
import sys
from collections import Counter

from langdetect import detect_langs

from services import language as L
from services.youtube_client import YouTubeClient


def _declared(yt: YouTubeClient, channel_id: str, uploads: str) -> tuple[str, Counter, Counter, int]:
    ch = yt._get("channels", {"part": "snippet", "id": channel_id})
    ch_lang = ((ch.get("items") or [{}])[0].get("snippet") or {}).get("defaultLanguage") or "-"
    ids = yt._playlist_video_ids(uploads, 50)
    audio, text, n = Counter(), Counter(), 0
    for i in range(0, len(ids), 50):
        data = yt._get("videos", {"part": "snippet", "id": ",".join(ids[i:i + 50]), "maxResults": 50})
        for it in data.get("items", []):
            sn = it.get("snippet") or {}
            n += 1
            audio[sn.get("defaultAudioLanguage") or "-"] += 1
            text[sn.get("defaultLanguage") or "-"] += 1
    return ch_lang, audio, text, n


def main() -> None:
    handles = sys.argv[1:]
    if not handles:
        raise SystemExit("Pasa uno o más handles entre comillas, por ejemplo: python -m scripts.lang_debug '@auron'")
    yt = YouTubeClient()
    for h in handles:
        info = yt.resolve_channel(h)
        if info is None:
            print(f"{h}: no existe\n")
            continue
        ch_lang, audio, text, n = _declared(yt, info.yt_channel_id, info.uploads_playlist_id)
        titles = [v.title for v in yt.recent_videos(info.uploads_playlist_id, 100)]
        cleaned = [c for c in (L._clean(t) for t in titles[:L.MAX_TITLES]) if len(c) >= 12 and len(c.split()) >= 2]
        score: Counter = Counter()
        for t in cleaned:
            try:
                for c in detect_langs(t):
                    score[c.lang] += c.prob
            except Exception:
                pass
        total = sum(score.values()) or 1
        print(f"{h}")
        print(f"   YouTube declara -> canal: {ch_lang} | audio de {n} videos: {dict(audio.most_common(4))} "
              f"| texto: {dict(text.most_common(4))}")
        print(f"   langdetect      -> {len(cleaned)} títulos útiles: "
              + ", ".join(f"{k} {v / total:.0%}" for k, v in score.most_common(5))
              + f" => detect_language: {L.detect_language(titles)}")
        for t in titles[:3]:
            print(f"   ej: {t}")
        print()


if __name__ == "__main__":
    main()