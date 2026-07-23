# CLAUDE.md — Asistente de Equipos de Pokémon Champions

Este archivo es la guía operativa del proyecto para Claude Code. Léelo entero antes de tocar código. No sustituye a los documentos de referencia (sección 1) — los complementa diciéndote **cómo trabajar**, no **qué construir en detalle**.

---

## 1. Documentos de referencia (léelos primero, en este orden)

1. `docs/roadmap.md` — plan técnico completo de 14 fases (datos, scrapers, validación, calculadora de daño, búsqueda semántica, meta comunitario, counters). **Es la fuente de verdad de qué construir en cada fase.**
2. `docs/behavior_prompt.md` — define cómo debe razonar y responder el asistente una vez esté conectado a Claude vía tool use (Fase 7 en adelante). No lo implementes hasta llegar a esa fase, pero tenlo en cuenta al diseñar las tools de la API para que encajen con lo que ese prompt espera poder consultar.

Si en algún momento este `CLAUDE.md` contradice al roadmap, **gana el roadmap** en cuestión de alcance/orden, y este archivo en cuestión de cómo trabajar día a día.

---

## 2. Qué es este proyecto (contexto)

Un asistente personal, de uso **local**, para construir y optimizar equipos competitivos de **Pokémon Champions**. No depende del recuerdo del modelo: toda la legalidad, el meta y los cálculos de daño se apoyan en una base de datos propia alimentada por scrapers, más un motor de cálculo determinista (adaptado de `@smogon/calc`) y búsqueda semántica sobre el roster legal actual.

Es un proyecto de uso personal en tu propia máquina — **no** hay que preocuparse por autenticación, multiusuario, escalado ni despliegue en la nube. Prioriza simplicidad de setup y velocidad de iteración sobre robustez de producción.

---

## 3. Alcance de trabajo

El objetivo final es completar el **roadmap completo de 14 fases** descrito en `docs/roadmap.md`. Pero **no se construye todo de golpe**: se avanza fase por fase, en el orden indicado en la sección 6 de ese documento, validando cada fase antes de pasar a la siguiente.

**No empieces una fase nueva sin que la anterior tenga, como mínimo:**
- Código funcionando y probado manualmente al menos una vez.
- Tests básicos si la fase lo permite (obligatorio en Fases 6 y 11, el validador de equipos y el motor de daño, por ser las partes más críticas de corrección).
- Un resumen corto en `PROGRESS.md` (ver sección 5) de qué se hizo y qué quedó pendiente/decidido.

---

## 4. Stack: punto de partida, no dogma

El roadmap propone Python + FastAPI + SQLite/Postgres + Playwright/BeautifulSoup + `@smogon/calc` adaptado. **Tienes libertad para desviarte si tiene sentido**, pero con estas condiciones:

- Antes de cambiar una pieza importante del stack (lenguaje, base de datos, librería de cálculo de daño), **explica el motivo y las alternativas consideradas** en `PROGRESS.md` antes de implementarlo — no hace falta pedir permiso explícito en cada micro-decisión, pero sí dejar rastro de las decisiones grandes.
- Por ser uso local personal, evita añadir infraestructura innecesaria (no Docker Compose con 5 servicios si un solo proceso Python basta; no Postgres si SQLite + Chroma/LanceDB cubre la búsqueda semántica sin más complicación).
- Si decides no usar `@smogon/calc` como base de la calculadora de daño (Fase 11), justifícalo especialmente bien: es la pieza donde más fácil es introducir errores sutiles si se reimplementa desde cero.

---

## 5. Cómo trackear el progreso

Mantén un archivo `PROGRESS.md` en la raíz con este formato, actualizándolo al final de cada sesión de trabajo:

```markdown
## Fase X — [nombre]
Estado: en progreso / completa / bloqueada
Hecho: ...
Pendiente: ...
Decisiones tomadas (y por qué): ...
Discrepancias de datos encontradas (si aplica): ...
```

Esto es lo primero que debes leer al empezar una nueva sesión, para saber dónde se quedó el proyecto sin que yo tenga que repetirte el contexto.

---

## 6. Reglas de trabajo con datos (dominio Pokémon Champions)

- **Nunca inventes** un Pokémon, movimiento, objeto o dato de legalidad. Si no está confirmado por scraping/API, márcalo como pendiente de verificar.
- Todo dato scrapeado (roster, ítems, % de uso, opinión comunitaria) se guarda **con fuente y fecha** — sin excepción, incluso en el MVP.
- Separa siempre **datos duros** (uso real de torneos, Pikalytics) de **percepción comunitaria** (foros, Reddit) — son tablas distintas (`usage_stats`/`common_sets` vs `community_meta_snapshots`), no las mezcles.
- Antes de dar por buena la legalidad de algo, contrasta contra al menos 2 fuentes cuando el roadmap lo indique (Fase 2 especialmente).
- Diseña los scrapers para **fallar de forma visible** (log/excepción clara) en vez de guardar datos a medias o corruptos si una web cambia su HTML.

---

## 7. Estructura de carpetas sugerida

```
/docs
  roadmap.md
  behavior_prompt.md
/src
  /scrapers        # uno por fuente (pokemon_zone.py, serebii.py, pikalytics.py, ...)
  /db               # modelos SQLModel/SQLAlchemy + migraciones Alembic
  /damage_calc      # motor de daño (adaptación de @smogon/calc)
  /semantic         # generación de embeddings + búsqueda híbrida
  /api              # endpoints FastAPI / definición de tools
  /cli              # comandos typer para uso local
/data
  /raw              # HTML crudo cacheado de cada scraping, con fecha
/tests
PROGRESS.md
CLAUDE.md
```

Ajusta si tiene sentido, pero mantén separados claramente: scraping, base de datos, motor de daño, búsqueda semántica y capa de exposición (API/CLI) — son piezas que se testean y evolucionan de forma independiente.

---

## 8. Variables de entorno / secretos

- Usa un archivo `.env` (con `.env.example` versionado, sin valores reales) para: API key de Anthropic (si se usan embeddings o resúmenes de la Fase 13 vía Claude), credenciales de la API de Reddit/YouTube si se usan en la Fase 13.
- **Nunca** commitees el `.env` real ni ninguna clave en claro. Añade `.env` a `.gitignore` desde el primer commit.

---

## 9. Cómo debes proceder tú (Claude Code) en cada sesión

1. Lee `PROGRESS.md` para saber en qué fase estamos.
2. Lee la sección correspondiente de `docs/roadmap.md`.
3. Antes de escribir código, dime en 2-3 líneas qué vas a hacer en esta sesión y confírmalo conmigo si implica una decisión de arquitectura no trivial (cambio de stack, diseño de esquema de BD, etc.). Para tareas dentro de lo ya acordado (seguir implementando un scraper ya diseñado, añadir tests) puedes proceder directamente.
4. Al terminar, actualiza `PROGRESS.md` y dime qué quedó listo, qué falta y si encontraste algo que rompa un supuesto del roadmap (ej. una web cambió su estructura, o Champions añadió una mecánica nueva).
5. No avances de fase sin que yo lo confirme, salvo que explícitamente te diga "sigue tú solo hasta X".
