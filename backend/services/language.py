"""Idioma de un canal.

1) Lo que DECLARA YouTube en sus videos (defaultAudioLanguage / defaultLanguage): llega gratis en videos.list y es
   mucho más confiable que adivinarlo, pero solo existe si el creador lo llenó (y a veces queda en 'en' por defecto).
2) Respaldo: langdetect título por título (no el texto pegado), pasando todo a minúsculas: los títulos en MAYÚSCULAS,
   típicos de gaming y retos, se detectaban como inglés, alemán o portugués. Se suman las probabilidades de cada idioma.

channel_language() combina las dos y es lo que usa la ingesta (también POST /channels)."""
import re
from collections import Counter

from langdetect import DetectorFactory, detect_langs

DetectorFactory.seed = 0

_NOISE = re.compile(r"https?://\S+|[@#]\S+")
_NON_WORD = re.compile(r"[^\w\s]|\d|_")
MIN_TITLES = 3
MAX_TITLES = 100
SPANISH_MIN_SHARE = 0.40   # con este peso o más, el canal se considera en español aunque otro idioma lo supere
DECLARED_MIN_VIDEOS = 5    # videos con idioma declarado para fiarse de él
DECLARED_MIN_SHARE = 0.60  # y qué parte de ellos debe coincidir
_NO_LANGUAGE = {"zxx", "und", ""}   # "sin contenido lingüístico" e "indeterminado"


def _clean(title: str) -> str:
    t = _NON_WORD.sub(" ", _NOISE.sub(" ", title or ""))
    return " ".join(t.split()).lower()


def _norm(code: str | None) -> str | None:
    """'es-419' / 'es-MX' / 'es_ES' -> 'es'."""
    if not code:
        return None
    base = code.strip().lower().replace("_", "-").split("-")[0]
    return None if base in _NO_LANGUAGE else base


def declared_language(videos) -> str | None:
    """Idioma que declara el creador en la mayoría de sus videos (audio primero, texto si falta el audio)."""
    langs = [_norm(getattr(v, "audio_language", None) or getattr(v, "text_language", None)) for v in videos]
    langs = [x for x in langs if x]
    if len(langs) < DECLARED_MIN_VIDEOS:
        return None
    lang, n = Counter(langs).most_common(1)[0]
    return lang if n / len(langs) >= DECLARED_MIN_SHARE else None


def detect_language(titles: list[str]) -> str | None:
    cleaned = [c for c in (_clean(t) for t in titles[:MAX_TITLES]) if len(c) >= 12 and len(c.split()) >= 2]
    if len(cleaned) < MIN_TITLES:
        return None
    score: Counter = Counter()
    n = 0
    for t in cleaned:
        try:
            cands = detect_langs(t)
        except Exception:
            continue
        n += 1
        for c in cands:
            score[c.lang] += c.prob
    if n < MIN_TITLES:
        return None
    total = sum(score.values())
    if score["es"] / total >= SPANISH_MIN_SHARE:
        return "es"
    lang, s = score.most_common(1)[0]
    return lang if s / total >= 0.5 else None


def channel_language(videos) -> str | None:
    """Si YouTube declara español, es español. Si declara otro idioma (a veces es solo el valor por defecto de
    la cuenta), se confirma con langdetect antes de darlo por bueno. Sin dato declarado, decide langdetect."""
    declared = declared_language(videos)
    if declared == "es":
        return "es"
    detected = detect_language([v.title for v in videos])
    if detected == "es":
        return "es"
    return declared or detected