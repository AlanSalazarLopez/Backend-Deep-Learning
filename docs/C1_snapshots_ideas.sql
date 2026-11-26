-- =====================================================================
-- AGREGAR AL FINAL de docs/C1_esquema_bd.sql (es idempotente: init_db la vuelve a correr sin problema)
-- =====================================================================

-- Historial de vistas: una fila por video y por corrida semanal. Permite medir velocidad real de crecimiento
-- y, en unas semanas, repetir el backtest con datos futuros de verdad.
CREATE TABLE IF NOT EXISTS video_snapshots (
  video_id  INTEGER NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
  taken_at  TIMESTAMPTZ NOT NULL,
  views     BIGINT NOT NULL,
  PRIMARY KEY (video_id, taken_at)
);
CREATE INDEX IF NOT EXISTS idx_snapshots_taken ON video_snapshots(taken_at);

-- Resultado más reciente de "ideas que rinden" por nicho (lo calcula el job semanal; la API solo lo lee).
CREATE TABLE IF NOT EXISTS niche_ideas (
  niche_id     INTEGER PRIMARY KEY REFERENCES niches(id) ON DELETE CASCADE,
  computed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  payload      JSONB NOT NULL
);