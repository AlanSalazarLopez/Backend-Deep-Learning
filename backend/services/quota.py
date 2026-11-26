"""Presupuesto de cuota de YouTube para los trabajos semanales (descubrimiento, ingesta...).

BudgetedYouTube es un YouTubeClient que cobra cada llamada contra un Budget ANTES de hacerla. Como las dos
excepciones heredan de YouTubeQuotaError, el código que ya existe (ingest_service, weekly.py...) las trata igual que
una cuota agotada de verdad: se detiene y conserva lo guardado.

  QuotaStop       -> se acabó el presupuesto TOTAL de la corrida: hay que parar todo.
  StepCapReached  -> se acabó el tope de UN paso: ese paso termina y los siguientes pueden seguir.

Costos (YouTube Data API v3): search.list = 100 unidades; videos.list, channels.list y playlistItems = 1.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from services.youtube_client import (YouTubeClient, YouTubeError, YouTubeQuotaError,
                                     long_form_playlist_id)

COST = {"search": 100}   # cualquier otro endpoint que usamos cuesta 1 unidad por llamada


class QuotaStop(YouTubeQuotaError):
    """Se acabó el presupuesto total de la corrida."""


class StepCapReached(YouTubeQuotaError):
    """Se acabó el tope de un paso (los demás pasos pueden continuar)."""


class Budget:
    def __init__(self, total: int):
        self.total = total
        self.used = 0
        self.by_step: Counter = Counter()
        self._step: str | None = None
        self._cap: int | None = None

    @contextmanager
    def step(self, name: str, cap: int | None = None):
        """Todo lo que se gaste dentro del with se anota en `name` y no puede pasar de `cap` (si se da)."""
        prev = (self._step, self._cap)
        self._step, self._cap = name, cap
        try:
            yield
        finally:
            self._step, self._cap = prev

    def spend(self, units: int) -> None:
        name = self._step or "otros"
        if self.used + units > self.total:
            raise QuotaStop(f"Se alcanzó el presupuesto total de {self.total} unidades")
        if self._cap is not None and self.by_step[name] + units > self._cap:
            raise StepCapReached(f"Se alcanzó el tope del paso '{name}' ({self._cap} unidades)")
        self.used += units
        self.by_step[name] += units

    @property
    def left(self) -> int:
        return self.total - self.used


def _int(v) -> int | None:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _dt(value) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


class BudgetedYouTube(YouTubeClient):
    def __init__(self, budget: Budget, **kw):
        super().__init__(**kw)
        self.budget = budget

    def _get(self, endpoint: str, params: dict) -> dict:
        self.budget.spend(COST.get(endpoint, 1))   # se cobra aunque la llamada falle: YouTube también la cuenta
        return super()._get(endpoint, params)

    # ------------------------------------------------------------------ descubrimiento
    def most_popular(self, region: str, category_id: int, pages: int = 2) -> list[dict]:
        """Videos 'más populares' de una región y categoría. 1 unidad por página de 50 (mucho más barato que
        search.list). Sesga hacia canales grandes. Algunas combinaciones región/categoría no tienen lista y
        YouTube responde 400: eso lanza YouTubeError y quien llama decide saltarla."""
        out, token = [], None
        for _ in range(pages):
            params = {"part": "snippet", "chart": "mostPopular", "regionCode": region,
                      "videoCategoryId": str(category_id), "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = self._get("videos", params)
            for it in data.get("items", []):
                sn = it.get("snippet") or {}
                if sn.get("channelId"):
                    out.append({"channel_id": sn["channelId"], "title": sn.get("title", "")})
            token = data.get("nextPageToken")
            if not token:
                break
        return out

    def search_videos(self, params: dict) -> list[dict]:
        """search.list (100 unidades). Devuelve [{channel_id, title}] de los videos encontrados."""
        data = self._get("search", {"part": "snippet", "maxResults": 50, **params})
        out = []
        for it in data.get("items", []):
            sn = it.get("snippet") or {}
            if sn.get("channelId"):
                out.append({"channel_id": sn["channelId"], "title": sn.get("title", "")})
        return out

    def channels_by_ids(self, ids: list[str]) -> dict[str, dict]:
        """Datos de muchos canales a la vez: 1 unidad por cada 50. subscribers = None si están ocultos."""
        out: dict[str, dict] = {}
        for i in range(0, len(ids), 50):
            batch = ids[i:i + 50]
            data = self._get("channels", {"part": "snippet,statistics", "id": ",".join(batch), "maxResults": 50})
            for it in data.get("items", []):
                sn, st = it.get("snippet") or {}, it.get("statistics") or {}
                subs = None if st.get("hiddenSubscriberCount") else (_int(st.get("subscriberCount")) or 0)
                out[it["id"]] = {"handle": sn.get("customUrl") or "", "title": sn.get("title", ""),
                                 "country": sn.get("country") or "", "subscribers": subs,
                                 "video_count": _int(st.get("videoCount")) or 0, "created": _dt(sn.get("publishedAt"))}
        return out

    # ------------------------------------------------------------------ preselección
    def recent_long_form_count(self, channel_id: str, days: int = 180, min_dur: int = 180, max_dur: int = 7200,
                               min_age_days: int = 3, now: datetime | None = None) -> int | None:
        """Cuántos videos publicó el canal en los últimos `days` días con el MISMO criterio del modelo: duración
        entre min_dur y max_dur y al menos min_age_days de edad. Mira sus 50 más recientes (el tope es 50).

        Lee el playlist de videos largos (UULF, 1 unidad) y se queda con los ids dentro de la ventana; si hay
        alguno, mide sus duraciones con videos.list (1 unidad). Si YouTube responde 404 (el canal no tiene UULF),
        cae a las últimas 50 subidas (3 unidades en total). Devuelve None si no se pudo saber (error pasajero):
        en ese caso no se debe rechazar al canal."""
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=days)
        newest = now - timedelta(days=min_age_days)
        if not channel_id.startswith("UC"):
            return None
        uploads = "UU" + channel_id[2:]
        ids: list[str] | None = None
        try:
            data = self._get("playlistItems", {"part": "contentDetails", "maxResults": 50,
                                               "playlistId": long_form_playlist_id(uploads)})
            ids = []
            for it in data.get("items", []):
                cd = it.get("contentDetails") or {}
                d = _dt(cd.get("videoPublishedAt"))
                if cd.get("videoId") and d is not None and d >= cutoff:
                    ids.append(cd["videoId"])
        except YouTubeQuotaError:
            raise
        except YouTubeError as e:
            if "404" not in str(e):
                return None
        if ids is None:   # respaldo: el canal no tiene playlist de videos largos
            try:
                ids = self._playlist_video_ids(uploads, 50)
            except YouTubeQuotaError:
                raise
            except YouTubeError:
                return None
        if not ids:
            return 0
        try:
            vids = self._video_details(ids)
        except YouTubeQuotaError:
            raise
        except YouTubeError:
            return None
        return sum(1 for v in vids if cutoff <= v.published_at <= newest and min_dur <= v.duration_s <= max_dur)