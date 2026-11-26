"""Utilidades de texto: normalización y stopwords (español e inglés)."""
import re
import unicodedata


def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


_STOP_ES = """a al algo algun alguna ante aqui asi aun aunque cada como con contra cual cuando de del desde donde dos
el ella ellas ellos en entre era eran es esa ese eso esta estas este esto estos fue ha han hasta hay la las le les lo
los mas me mi mis muy ni no nos nuestro o otra otro para pero poco por porque que quien se ser si sin sobre su sus
tambien tan te tengo tiene todo todos tu tus un una unas uno unos usted va vez y ya yo"""
_STOP_EN = """a an and are as at be but by for from has have i if in is it its my of on or our so than that the their
them then there these they this to was we were what when which who will with you your"""

# Normalizadas igual que el texto (minúsculas, sin acentos) para que TfidfVectorizer no advierta inconsistencias.
STOPWORDS = sorted({strip_accents(w.lower()) for w in (_STOP_ES + " " + _STOP_EN).split()})

EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B50\u2B06\u2705]")

_HASHTAG = re.compile(r"#\w+", re.UNICODE)
_EPISODE = re.compile(
    r"\b(?:parte|part|cap[ií]tulo|cap|episodio|ep|temporada|vol|volumen)\.?\s*\d+\b",
    re.IGNORECASE,
)


def clean_title(title: str) -> str:
    """Quita hashtags y numeración de serie ("Parte 2", "Ep. 5", "Capítulo 3") y normaliza espacios.

    Solo borra la numeración, no el resto del título. Los separadores sueltos (| - –) no se tocan:
    el vectorizador los ignora. Debe aplicarse igual al entrenar, al predecir y en topic_ranking.
    """
    t = _HASHTAG.sub(" ", title or "")
    t = _EPISODE.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()