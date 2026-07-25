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

## Fase 3 — Scraper de objetos y movepools legales
Estado: completa

Hecho:
- Investigación previa (igual que en Fase 2, antes de escribir código): ChampsDex.com resultó ser un blog sin páginas por Pokémon (descartado); ChampDex.com (dominio distinto, casi homónimo) tiene páginas por Pokémon pero sin método de aprendizaje ni legalidad de ítems (descartado); Serebii sí tiene lo necesario pero repartido en 3 sitios (`pokemonchampions/moves.shtml`, `pokemonchampions/items.shtml`, `pokedex-champions/{slug}/`) y **sin** distinción level-up/TM/huevo (Champions la eliminó: es solo "puede usarlo o no"). Se encontró **MetaVGC** (no estaba en el roadmap) como fuente con snapshot completo y fechado por regulation (Legal Pokémon/Allowed items/Allowed moves con conteos) — sustituye a ChampsDex/ChampDex como fuente principal de esta fase, con Serebii como segunda fuente de contraste. Confirmado con el usuario antes de codificar (decisión de arquitectura no trivial).
- **Hallazgo que cambió el esquema del roadmap**: el pool de movimientos habilitados sí varía por regulation (467 en M-A → 502 en M-B, confirmado cruzando snapshots de MetaVGC), pero es una lista plana global, no por especie — mientras que el movepool de cada especie (qué puede aprender) es fijo, no versionado por regulation. Por eso `regulation_legal_moves` quedó como tabla plana `(regulation_id, move_id)` en vez de `(regulation_id, pokemon_species_id, move_id)` como sugería el roadmap, y se creó `pokemon_movepool(pokemon_species_id, move_id)` aparte, sin `regulation_id`. La legalidad real por especie es la intersección de ambas (cálculo para la Fase 5/API, no se guarda ya cruzado).
- Hueco cerrado de la Fase 1: `items` estaba en el esquema estático del roadmap (junto a moves/abilities) pero nunca se sembró. Añadido `Item` a `models.py` + `seed_items()` en `src/db/seed.py` reutilizando el cliente de PokeAPI ya existente (2223 ítems).
- Scrapers nuevos: `src/scrapers/metavgc.py` (snapshot por regulation, HTML server-rendered de Next.js, sin JS necesario) y `src/scrapers/serebii_champions.py` (catálogo en vivo de moves/items + movepool por especie).
- Orquestador `src/db/seed_movepool.py` (`python -m src.db.seed_movepool`), idempotente vía caché diario en `data/raw/{metavgc,serebii_champions}/`. Toma la regulation activa ya sembrada por la Fase 2 (no re-scrapea Bulbapedia).
- 11 tests nuevos (`tests/test_movepool_scrapers.py`, offline), 27/27 en verde en total.
- **Ejecución real contra las 3 fuentes en vivo** (M-B): 502/502 moves resueltos (485 verificados cruzando con Serebii, 17 sin verificar), 141/148 ítems resueltos (140 verificados, 1 sin verificar, 7 sin resolver), movepool completo para 207/207 especies actualmente legales (19215 filas `pokemon_movepool`).
- Dos bugs reales encontrados y arreglados corriendo en vivo (no se habrían visto con datos de ejemplo): (1) un 404 de una sola especie tumbaba todo el orquestador porque `httpx.HTTPStatusError` no estaba envuelto en la excepción propia del scraper — ahora se captura por especie y el resto continúa; (2) nombres tipo "BrightPowder" (sin espacio) o "King's Rock" no cruzaban con los slugs de PokeAPI (`bright-powder`, `kings-rock`) — añadida `_match_slug()` con separación de camelCase y eliminación de apóstrofes, solo para este matching.

Pendiente:
- Nada bloqueante para pasar a Fase 4. Quedan 7 ítems sin `item_id` (mega stones exclusivas de Champions no presentes en PokeAPI, ver discrepancias) y el mapeo especie→slug de Serebii tiene overrides puntuales (`_KNOWN_FORM_SUFFIXES`, `_SEREBII_SLUG_OVERRIDES` en `seed_movepool.py`) que probablemente necesiten un entrada más si una regulation futura trae una especie con un patrón de forma-por-defecto nuevo — mismo mantenimiento que ya requería `IG_ALIAS` de la Fase 2.

Decisiones tomadas (y por qué):
- MetaVGC como fuente principal de items/moves (en vez de ChampsDex que sugería el roadmap) — confirmado con el usuario tras comprobar que ChampsDex no tiene páginas por Pokémon.
- Esquema partido (`pokemon_movepool` sin regulation + `regulation_legal_moves`/`regulation_legal_items` planas) en vez del esquema ilustrativo del roadmap — confirmado con el usuario.
- El movepool solo se scrapea para especies actualmente legales (207), no las 1351 de PokeAPI — no tiene sentido cachear el movepool de especies que ni siquiera están en Champions ahora mismo; se amplía por delta cuando una regulation nueva añada especies (mismo criterio de alcance que ya aplicaba Fase 2 al roster).

Discrepancias de datos encontradas:
- **7 Mega Stones exclusivas de Champions no existen en PokeAPI**: Barbaracleite, Dragalgeite, Mawileite, Sceptileite, Scolipedeite, Scraftyite, Staraptorite — corresponden a Megas nuevas que Champions introdujo para especies que nunca tuvieron Mega Evolución en los juegos principales (Mega Barbaracle, Mega Dragalge, etc., ya vistos como discrepancia similar en Fase 2 con Vivillon-Fancy/Meowstic-Mega). No se guardó `item_id` inventado — quedan fuera de `regulation_legal_items` hasta que se decida cómo modelar contenido exclusivo de Champions que no existe en PokeAPI (probablemente entradas manuales con `source="champions-exclusive"` en una fase posterior).
- Serebii usa un slug con punto literal (`mr.rime`) en vez de guión para "Mr. Rime" — inconsistente con el resto de su propio sitio; documentado como override puntual, no una regla general.

---

## Fase 4 — Scraper de meta/uso competitivo (datos duros)
Estado: completa (usage_stats + notable_teams; common_sets pendiente, ver abajo)

Hecho:
- Investigación previa de las fuentes que sugería el roadmap: **Pikalytics** sí tiene sección Champions y robots.txt permisivo, pero su tabla completa de % de uso por Pokémon vive detrás de renderizado cliente (sólo su widget "Top 20 Pokemon" —rank+nombre, sin %— es HTML plano); además su landing page mezcla enlaces a un slug `regma` heredado (posible resto de una migración interna) con el dataset real y correcto `battledataregmbs3`, confirmado cruzando el texto "Format:" visible en la página. **Limitless VGC** (`limitlessvgc.com`) delega los standings/decklists reales a `standings.limitlessvgc.com`, que es una app SvelteKit sin datos en el HTML crudo (necesitaría Playwright o su API interna, no localizada). Se encontró **ChampionsMeta** (championsmeta.io, no estaba en el roadmap) como sustituto: Next.js SSR con datos reales sin JS, cita explícitamente "Data sourced from Limitless TCG", con página `/meta` (ranking de uso completo por regulation) y `/tournaments` (torneos recientes con top standings + equipo real por jugador, ya con el link a la página original de Limitless). Se descartó `championsmeta.io/teams` para `notable_teams` porque es contenido **enviado por usuarios y votado** (percepción/comunidad, no resultado de torneo real) — encaja mejor en la Fase 13, no aquí, según la regla del CLAUDE.md de separar datos duros de percepción comunitaria.
- Modelos nuevos (`src/db/models.py`): `UsageStat`, `NotableTeam` (con `source`/`retrieved_at`/`verified` igual que las tablas de legalidad de Fases 2-3).
- Pequeño refactor: `_get_active_regulation` (duplicado en `seed_movepool.py`) se movió a `src/db/active_regulation.py` para reutilizarse aquí también.
- Scrapers nuevos: `src/scrapers/championsmeta.py` (primario: usage rankings + torneos con equipos) y `src/scrapers/pikalytics.py` (segundo, solo para contrastar el Top 20 por nombre).
- Orquestador `src/db/seed_usage.py` (`python -m src.db.seed_usage`), idempotente vía caché diario en `data/raw/{championsmeta,pikalytics}/`.
- 15 tests nuevos (offline), 38/38 en verde en total.
- **Ejecución real en vivo** (M-B): 50/50 entradas de usage_stats resueltas (20/20 verificadas contra el Top 20 de Pikalytics — coincidencia total, buena señal de que ambas fuentes son consistentes), 160 filas en `notable_teams` desde 20 torneos recientes, con 0 Pokémon sin resolver en los equipos.
- Un bug real de regex arreglado en vivo (no visible con datos de ejemplo simplificados hasta que reproduje la clase real): el badge de rango de cada jugador en `/tournaments` tiene más clases CSS de las que asumí (`text-yellow-400 border-yellow-600/40 bg-yellow-500/10` en vez de una sola clase `text-yellow-400`), lo que rompía `_PLAYER_ROW_RE`; corregido a un match de clase más laxo (`class="[^"]*font-bold shrink-0[^"]*"`).
- Segundo problema real (mismo patrón que Fase 3, pero esta vez en el lado de ChampionsMeta en vez de Serebii): sus slugs a veces ponen el descriptor de forma **antes** del nombre de especie (`Alolan-Ninetales`, `Wash-Rotom`, `Eternal-Flower-Floette`) mientras PokeAPI lo pone **después** (`ninetales-alola`, `rotom-wash`, `floette-eternal`); y algunas especies (`Basculegion`, `Maushold`, `Pyroar`, `Palafin`) no tienen forma base sin sufijo en PokeAPI, igual que Aegislash/Gourgeist en Fase 3. Resuelto con `_resolve_species_id()` en `seed_usage.py`: reordena prefijos regionales/Rotom conocidos, cae a la forma `is_default` cuando el slug plano no existe, y un override puntual para Floette-Eternal.

Pendiente:
- **`common_sets`** (objeto/habilidad/naturaleza/movimientos típicos por Pokémon) no se implementó esta sesión — ChampionsMeta no expone esa granularidad en las páginas ya scrapeadas (`/meta` da solo % de uso agregado; `/tournaments` da equipos reales pero sin desglose completo de set por Pokémon en la vista de lista). Necesitaría o bien las páginas de detalle `/pokemon/{slug}` de ChampionsMeta (no investigadas todavía) o volver a intentar la ruta de "sets" de Pikalytics. Queda para retomar si se necesita antes de la Fase 11 (calculadora de daño), que sí se beneficia de tener sets típicos.
- El resolver de slugs (`_resolve_species_id`, `_REGIONAL_PREFIX_TO_SUFFIX`, `_ROTOM_FORMS`, `_SLUG_OVERRIDES` en `seed_usage.py`) es igual de puntual que `IG_ALIAS`/`_SEREBII_SLUG_OVERRIDES` — mismo mantenimiento esperado si aparecen especies/formas nuevas.

Decisiones tomadas (y por qué):
- ChampionsMeta como fuente principal de usage_stats/notable_teams en vez de Pikalytics/Limitless directamente (que sugería el roadmap) — decisión tomada de forma autónoma (el usuario dio luz verde explícita a "seguir solo" en esta fase), documentada aquí en vez de confirmarse en vivo como en Fases 2-3.
- `championsmeta.io/teams` (equipos votados por la comunidad) descartado para `notable_teams` y anotado como candidato de Fase 13 en vez de Fase 4 — mantiene la separación datos-duros/percepción que exige el CLAUDE.md.
- Pikalytics se degrada a fuente de contraste (solo Top 20 por nombre) en vez de fuente primaria, porque su tabla completa de % requiere JS que no se investigó (no bloqueante: no se añadió Playwright para esto, evaluar en una sesión futura si hace falta más profundidad de Pikalytics).

Discrepancias de datos encontradas:
- Ninguna relevante sobre legalidad/datos del juego. Las dos discrepancias fueron de convención de nombres entre fuentes (ver "Hecho" arriba), no de contenido.

---

## Fase 5 — API interna (FastAPI)
Estado: completa (solo lectura; `/team/validate` diferido a Fase 6 a propósito, ver Decisiones)

Hecho:
- 3 decisiones confirmadas con el usuario antes de escribir código (pidió explícitamente que preguntara):
  1. `POST /team/validate` se difiere a la Fase 6 — el motor de reglas es trabajo de esa fase (tests obligatorios según CLAUDE.md), no se adelanta sin pasar por su propio checkpoint.
  2. Los endpoints de listado devuelven resumen ligero (id/nombre/tipos/verified); el detalle completo vive en un endpoint `GET /pokemon/{id}` nuevo (no estaba en el roadmap tal cual, pero hace falta para que `/pokemon/{id}/legal-moves` tenga contexto).
  3. `docs/behavior_prompt.md` no existe todavía en el repo (solo `docs/roadmap.md`) — se sigue sin él, ya que no se usa hasta la Fase 7 de todas formas; los endpoints se revisarán entonces si hace falta.
- Deps nuevas: `fastapi`, `uvicorn[standard]` (ya estaban en el stack sugerido por el roadmap, sección 1 — no es un cambio de stack que requiera justificación aparte).
- `src/api/schemas.py` (modelos de respuesta Pydantic) + `src/api/main.py` (5 endpoints):
  - `GET /regulation/active`
  - `GET /pokemon/legal?regulation_id=` (resumen; default = regulation activa)
  - `GET /pokemon/{id}` (detalle: stats base, tipos, `is_default`, si es legal en la regulation consultada) — **nuevo, no estaba en el roadmap**
  - `GET /pokemon/{id}/legal-moves?regulation_id=` — implementa el cruce `pokemon_movepool ∩ regulation_legal_moves` decidido en Fase 3 (hasta ahora vivían como dos tablas separadas sin combinar; este es el primer sitio que las junta)
  - `GET /meta/top-usage?regulation_id=&limit=`
- 9 tests (`tests/test_api.py`) vía `TestClient` contra la base de datos real ya sembrada (no una BD de fixtures aparte — es un proyecto de un solo entorno, montar una BD de test separada sería infraestructura innecesaria para uso local). Aserciones laxas (formas y "al menos una fila plausible"), no conteos exactos, para no romperse cada vez que un scraper se re-ejecute y cambie un número real.
- Verificación manual real: servidor levantado con `uvicorn src.api.main:app` y probado con `curl` contra los 6 endpoints (incluyendo `/docs` y `/openapi.json`) — todas las respuestas con datos reales correctos (Charizard, Garchomp al 34.9% de uso, 308 Pokémon legales, etc.) y los 404 esperados (especie inexistente, regulation inexistente).
- 47/47 tests en verde en total.

Pendiente:
- Cada especie no tiene sus habilidades posibles modeladas (`PokemonSpecies` nunca guardó la relación con `Ability` en la Fase 1 — el propio esquema ilustrativo del roadmap tampoco la mostraba). No bloqueaba nada hasta ahora, pero se nota en `GET /pokemon/{id}`, que no puede listar qué habilidades puede tener esa especie. Se deja pendiente hasta que una fase que la necesite de verdad la pida (probablemente Fase 6 o la 11, calculadora de daño, donde la habilidad si importa para el cálculo).
- `POST /team/validate` — Fase 6.

Decisiones tomadas (y por qué): ver los 3 puntos confirmados con el usuario arriba.

---

## Próxima sesión
Empezar Fase 6 — Motor de validación de equipos.
