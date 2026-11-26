"""services/language.py: idioma declarado por YouTube y respaldo con langdetect."""
from types import SimpleNamespace as NS

import pytest

from services import language as L


def V(audio=None, text=None, title="Un titulo cualquiera de prueba"):
    return NS(audio_language=audio, text_language=text, title=title)


def test_normaliza_codigos_de_idioma():
    assert L._norm("es-419") == "es" and L._norm("es-MX") == "es" and L._norm("es_ES") == "es"
    assert L._norm("zxx") is None and L._norm("und") is None and L._norm("") is None and L._norm(None) is None


def test_idioma_declarado():
    assert L.declared_language([V("es-MX")] * 50) == "es"
    assert L.declared_language([V("es")] * 3) is None                      # muy pocos datos
    assert L.declared_language([V(None, "es-ES")] * 10) == "es"            # sin audio, usa el idioma del texto
    assert L.declared_language([V("es")] * 5 + [V("en")] * 5) is None      # sin mayoría clara
    assert L.declared_language([V("es")] * 8 + [V("nl")] * 2) == "es"


def test_si_youtube_declara_espanol_no_se_llama_a_langdetect(monkeypatch):
    def boom(titles):
        raise AssertionError("no debía llamarse")
    monkeypatch.setattr(L, "detect_language", boom)
    assert L.channel_language([V("es-419")] * 20) == "es"


def test_si_declara_otro_idioma_se_confirma_con_langdetect(monkeypatch):
    vids = [V("en")] * 20
    monkeypatch.setattr(L, "detect_language", lambda t: "es")
    assert L.channel_language(vids) == "es"          # 'en' era el valor por defecto de la cuenta
    monkeypatch.setattr(L, "detect_language", lambda t: None)
    assert L.channel_language(vids) == "en"
    monkeypatch.setattr(L, "detect_language", lambda t: "en")
    assert L.channel_language(vids) == "en"


def test_sin_dato_declarado_decide_langdetect(monkeypatch):
    monkeypatch.setattr(L, "detect_language", lambda t: "pt")
    assert L.channel_language([V()] * 20) == "pt"
    monkeypatch.setattr(L, "detect_language", lambda t: None)
    assert L.channel_language([V()] * 20) is None


def test_limpieza_pasa_a_minusculas_y_quita_ruido():
    assert L._clean("COMPRÉ ALGO #shorts https://x.co 100!") == "compré algo"


def test_espanol_claro_con_langdetect_real():
    titulos = ["Cómo hacer una receta de tacos al pastor en casa", "Probando el nuevo videojuego con mis amigos hoy",
               "Mi rutina de la mañana para estar más productivo", "LO QUE PASÓ CUANDO ABRÍ LA CAJA MISTERIOSA"]
    assert L.detect_language(titulos) == "es"