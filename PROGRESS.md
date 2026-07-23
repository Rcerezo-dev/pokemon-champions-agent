# PROGRESS

## Fase 1 — Fundamentos de datos estáticos
Estado: completa

Hecho:
- Estructura de carpetas creada (`docs/`, `src/{scrapers,db,damage_calc,semantic,api,cli}`, `data/raw/`, `tests/`), repo git inicializado localmente.
- `docs/roadmap.md` (movido desde la raíz, donde estaba como `roadmap_pokemon_champions_completo.md`, para que coincida con la ruta que referencia este CLAUDE.md).
- Proyecto Python 3.11 con venv (`.venv/`) y `pyproject.toml` (deps: `httpx`, `sqlmodel`, `pytest`).
- Modelos SQLModel (`src/db/models.py`): `PokemonSpecies`, `Ability`, `Move`, `Nature`, `TypeChart` — solo las tablas que necesita esta fase; el resto del esquema (regulation_sets, usage_stats, etc.) se añade cuando la fase correspondiente lo use.
- Cliente PokeAPI (`src/db/pokeapi_client.py`): async, cachea cada respuesta JSON cruda en `data/raw/pokeapi/` (idempotente — reejecutar el seed no vuelve a golpear la API si el cache existe).
- Script de seed (`src/db/seed.py`, `python -m src.db.seed`) — poblado real ejecutado contra la PokeAPI:
  - `type_chart`: 361 pares (19 tipos, incluye `stellar` de Gen9 aunque Champions desactiva Tera — inofensivo, no se usa)
  - `natures`: 25
  - `abilities`: 373
  - `moves`: 937
  - `species`: 1351 (incluye formas alternativas — ver discrepancia abajo)
- Calculadora de efectividad de tipos (`src/damage_calc/type_effectiveness.py`) + 5 tests (`tests/test_type_effectiveness.py`), todos en verde.
- Verificación manual: Charizard (fire/flying, stats correctos), Thunderbolt (electric/special/90/100), Adamant (+atk/-spatk), Water→Fire = 2.0×.

Pendiente:
- `.env` real (no hace falta aún — Fase 1 no usa ninguna API key; `.env.example` ya deja `DATABASE_URL` documentada).
- Nada bloqueante para pasar a Fase 2.

Decisiones tomadas (y por qué):
- **SQLModel** en vez de `sqlite3` a pelo — confirmado con el usuario al empezar la sesión. Sigue lo que ya recomendaba el roadmap (tipado + migraciones con Alembic más adelante).
- Usé el endpoint `/pokemon` de PokeAPI (no `/pokemon-species`) para poblar `pokemon_species`, porque los stats base viven ahí, no en species. Efecto secundario: la tabla incluye formas alternativas (megas, formas regionales, etc.) como filas separadas con su propio id — el roadmap no distingue esto explícitamente. Se resolverá en Fase 2 al filtrar por roster legal de Champions (probablemente habrá que decidir qué formas son relevantes para el formato).
- El esquema de la Fase 1 (`pokemon_species`, `moves`, `abilities`, `natures`, `type_chart`) no lleva columnas `source`/`retrieved_at` — a propósito: la regla de "fuente y fecha" del CLAUDE.md aplica a datos scrapeados de fuentes comunitarias (roster, uso, opinión), no a esta referencia estática de la API oficial. La procedencia queda igual en el cache crudo de `data/raw/pokeapi/` (con fecha de modificación del archivo).
- Cache crudo de PokeAPI (`data/raw/pokeapi/`, ~207MB) excluido de git vía `.gitignore` — es regenerable con `python -m src.db.seed` y no aporta nada versionado.

Discrepancias de datos encontradas:
- Ninguna relevante para el juego. Sí hubo un bug técnico: los nombres de archivo de cache no podían contener `?` en Windows (falló en el primer intento con `type?limit=100000.json` → `OSError`); arreglado saneando esos caracteres en `pokeapi_client._cache_path`.

---

## Próxima sesión
Empezar Fase 2 — Scraper del Regulation Set activo (Pokémon-Zone/Victory Road/Bulbapedia): nombre del regulation, fechas, roster legal, contraste entre ≥2 fuentes. Ahí habrá que decidir qué hacer con las formas alternativas de `pokemon_species` mencionadas arriba.
