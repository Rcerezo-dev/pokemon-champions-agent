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

## Fase 2 — Scraper del Regulation Set activo
Estado: completa

Hecho:
- Investigación previa de las 3 fuentes candidatas del roadmap antes de escribir código (`robots.txt` de las tres, estructura real de cada página):
  - **Bulbapedia**: fuente principal. Se scrapea vía wikitext crudo de MediaWiki (`action=raw`), no HTML renderizado — mucho más estable (`{{RegulationSetInfobox}}` para fechas, `{{CPCard|dex|nombre|ig=...}}` para el roster). `Crawl-delay: 5` de su `robots.txt` respetado con `time.sleep`.
  - **Victory Road**: solo se usa para contrastar nombre/fechas/`mega_allowed` (una frase de texto parseable por regex). Su roster son imágenes, no texto — no sirve para contrastar Pokémon individuales.
  - **Pokémon-Zone**: segunda fuente para contrastar el roster Pokémon-por-Pokémon. Bloquea `httpx` con 403 incluso con User-Agent de navegador y HTTP/2 (fingerprint TLS de Cloudflare, no las cabeceras) — confirmado con pruebas directas. `curl` sí pasa, así que ese scraper hace `subprocess` a `curl` en vez de añadir una dependencia nueva tipo `curl_cffi`.
- Modelos nuevos (`src/db/models.py`): `RegulationSet`, `RegulationLegalPokemon` (con `source`/`retrieved_at`/`verified`/`verification_note` — sí llevan estas columnas aunque el esquema ilustrativo del roadmap no las mostraba, porque CLAUDE.md exige fuente+fecha para todo dato scrapeado de roster).
- `PokemonSpecies` ganó una columna `is_default` (bool, viene directo del JSON de PokeAPI, ya cacheado — no hizo falta re-scrapear) — necesaria para resolver correctamente la "forma por defecto" cuando no coincide con el nombre base (ej. Aegislash por defecto es `aegislash-shield`, no `aegislash`).
- Scrapers (`src/scrapers/`): `bulbapedia.py`, `victory_road.py`, `pokemon_zone.py`, más `form_matching.py` con la lógica de emparejamiento entre las tres fuentes.
- Orquestador `src/db/seed_regulation.py` (`python -m src.db.seed_regulation`), idempotente vía cache diario en `data/raw/{bulbapedia,victory_road,pokemon_zone}/`.
- 16 tests (`tests/test_regulation_scrapers.py`), todos offline (wikitext/HTML de ejemplo embebido, sin red) — cubren parseo de `CPCard`, regex de Victory Road y Pokémon-Zone, y los casos límite del emparejamiento (mega X/Y, forma regional, forma de género, forma por defecto no-obvia, no resuelto).
- **Ejecución real contra las 3 fuentes en vivo**: Regulation Set activo detectado automáticamente = **M-B** (17 jun – 2 sep 2026), coincide con Victory Road en fechas y `mega_allowed=True`. Roster: 308/310 entradas de Bulbapedia guardadas (303 verificadas cruzando con Pokémon-Zone, 5 sin verificar, 2 sin resolver — ver discrepancias abajo).

Pendiente:
- Nada bloqueante para pasar a Fase 3. Quedan 2 formas cosméticas sin fila en `pokemon_species` (Vivillon-Fancy, Meowstic-Mega) y 5 formas verificadas=false — documentado abajo, no se inventó nada para rellenarlas.

Decisiones tomadas (y por qué):
- **Granularidad de contraste "forma por forma"**: decisión explícita del usuario (se le preguntó porque implicaba riesgo de fallos silenciosos). Implementado con una tabla de alias explícita para las familias sistemáticas (Alola/Galar/Hisui/Paldea/Mega/Mega X/Mega Y/formas de Rotom/género) más comparación por tokens normalizados contra los slugs de Pokémon-Zone. Cuando no hay forma de emparejar con confianza, la fila se guarda con `verified=false` y una nota explicando por qué — nunca se adivina en silencio.
- Detección automática del regulation activo: se listan los códigos del índice de Bulbapedia y se comprueba `start <= ahora < end` en cada uno (empezando por el más reciente), en vez de asumir que el último listado es el activo — más robusto si Bulbapedia lista el siguiente regulation por adelantado.
- `regulation_legal_pokemon` no lleva la columna `mega_allowed_for_this` que sugería el esquema ilustrativo del roadmap: como las formas mega ya son sus propias filas en `pokemon_species` (mismo criterio que PokeAPI), que la fila exista ya dice que es legal — la columna sería redundante.

Discrepancias de datos encontradas:
- **Tauros (dex 128), forma "Combat Breed"**: es la forma por defecto según Bulbapedia/PokeAPI, pero el roster actual de Pokémon-Zone para M-B solo lista las variantes Aqua y Blaze Breed — Combat Breed no aparece en absoluto. Confirmado a mano en el HTML cacheado, no es un bug del parser. Guardado igualmente (fuente: Bulbapedia) pero con `verified=false`.
- **Gourgeist** (dex 711): Bulbapedia/PokeAPI distinguen 4 tamaños (`average` default + `small`/`large`/`super`≡"Jumbo"); Pokémon-Zone solo tiene una entrada genérica `gourgeist` sin variantes de tamaño. Las 3 variantes no-default quedan `verified=false` (la default sí se verifica, matchea con la entrada genérica).
- **Vivillon-Fancy** y **Meowstic-Mega**: Bulbapedia los lista en el roster de M-B pero no existe fila correspondiente en `pokemon_species` (PokeAPI no modela los patrones cosméticos de Vivillon como especies separadas; "Mega Meowstic" no es una mecánica de los juegos principales, así que PokeAPI tampoco la tiene — parece ser una mega exclusiva de Champions). No se guardaron filas en `regulation_legal_pokemon` para estos dos porque no hay `pokemon_species_id` al que apuntar sin inventarlo. Pendiente de revisar manualmente si se quiere cubrir esto en una fase posterior (probablemente al tocar movepools/ítems en Fase 3, o si Champions sigue añadiendo megas nuevas no presentes en PokeAPI).

---

## Próxima sesión
Empezar Fase 3 — Scraper de objetos y movepools legales por regulation (Serebii/ChampsDex). Puede ser buen momento para decidir qué hacer con las 2 entradas sin `pokemon_species_id` (Vivillon-Fancy, Meowstic-Mega) si vuelven a aparecer.
