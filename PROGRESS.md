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

## Fase 6 — Motor de validación de equipos
Estado: completa

Hecho:
- Investigación previa de dos reglas que **no** estaban ya en nuestros datos scrapeados (`RegulationSet.notes` de Fase 2 solo cubre ítems duplicados, mega por batalla y timers — nada de tamaño de equipo ni del sistema SP):
  - **Tamaño de equipo**: confirmado en Serebii (`pokemonchampions/rankedbattle/regulationm-b.shtml`, ya fuente conocida): "Team of 3 to 6 Pokémon" (Singles) / "Team of 4 to 6 Pokémon" (Doubles).
  - **Sistema SP** (reemplazo de EVs): 66 puntos totales, máx. 32 por stat — no lo dice ninguna fuente "oficial" que ya scrapeamos, pero coincide exactamente entre 5+ guías independientes (game8.co, ChampDex, Switchblade Gaming, BattleWise AI, GameCards), ninguna menciona variación entre regulations → tratado como mecánica fija del juego (igual que la tabla de tipos/naturalezas de Fase 1), documentada como constante con cita en el código en vez de fila de BD con fuente/fecha (no es "legalidad versionada por regulation").
- **Descubrimiento importante que corrige el roadmap**: el roadmap dice "máx. 1 Mega" como regla de equipo, pero el texto real ya scrapeado de Bulbapedia (`RegulationSet.notes`) dice literalmente *"a player may only Mega Evolve once per battle"* — es una restricción de **uso en batalla**, no de **composición de equipo**. Un equipo puede legalmente llevar dos Pokémon Mega-capaces (cada uno legal por separado, con Piedras Mega distintas); solo no puedes evolucionar a los dos en la misma batalla. Implementar "máx. 1 Mega en el equipo" habría rechazado equipos legales de verdad — **no se implementó esa regla**, documentado en el docstring de `team_validator.py`.
- `src/validation/team_validator.py`: motor puro (`validate_team(session, regulation, format, members) -> ValidationResult`), sin dependencias de FastAPI, reutilizable también desde el CLI (Fase 9) o tests. Reglas: tamaño de equipo por formato, Species Clause, Item Clause, especie/movimiento/ítem legal en la regulation consultada (reutiliza el cruce `pokemon_movepool ∩ regulation_legal_moves` ya usado en la Fase 5), SP por stat/total, 1-4 movimientos sin duplicados, existencia de habilidad/naturaleza (no su legalidad para esa especie en concreto — mismo hueco de Fase 5, no hay tabla especie→habilidad).
- Endpoint `POST /team/validate` conectado en `src/api/main.py` (ahora si, la Fase 5 queda completa del todo).
- **22 tests obligatorios** (`tests/test_team_validator.py`) con una base de datos SQLite en memoria con datos de fixture controlados a mano (no la BD real) — para poder probar cada regla con un escenario exacto e inmutable en vez de depender de qué esté legal hoy en M-B. Cubre los 22 casos: equipo válido completo, tamaño fuera de rango (por formato), especie/ítem duplicado, especie/movimiento/ítem no legal, movimiento inexistente, movimiento que la especie no puede aprender, SP fuera de rango (por stat/total/negativo), nombre de stat desconocido, demasiados movimientos, movimiento repetido, sin movimientos, habilidad/naturaleza inexistente, formato desconocido.
- 69/69 tests en verde en total.
- **Verificación manual real**: servidor levantado, un equipo Dobles real y legal (Garchomp/Incineroar/Kingambit/Sinistcha — los 4 más usados de M-B según la Fase 4, con movimientos/ítems/naturaleza/SP reales) validado como `"valid": true` sin ningún issue; un segundo equipo deliberadamente roto (Garchomp repetido, mismo ítem repetido, SP 40/74 total, movimiento inventado) devolvió los 6 issues esperados con mensajes correctos.

Pendiente:
- Nada bloqueante. El hueco de habilidad-por-especie (ya anotado en Fase 5) sigue sin resolver — el validador solo comprueba que la habilidad exista, no que sea válida para esa especie.

Decisiones tomadas (y por qué):
- SP (66/32) como constante citada en código, no fila de BD — no es un dato que varíe por regulation según todo lo investigado, y CLAUDE.md solo exige fuente+fecha en BD para "datos scrapeados de fuentes comunitarias" de legalidad/uso/percepción, no para mecánicas fijas del juego (mismo criterio que Fase 1 aplicó al type_chart).
- "Máx. 1 Mega" del roadmap **no implementado tal cual** — se prioriza el texto real scrapeado sobre el resumen del roadmap, según la regla del propio CLAUDE.md de "nunca inventes... si no está confirmado, márcalo pendiente" (aquí el dato SÍ está confirmado, y contradice la regla propuesta).
- Tests con BD en memoria + fixture a mano en vez de la BD real (a diferencia de `test_api.py` en Fase 5) — al ser una de las dos fases críticas de corrección, hace falta control exacto de cada escenario, no depender de qué esté legal hoy en el M-B real.

---

## Fase 7 — Integración conversacional (Claude + Gemini)
Estado: completa (falta verificación manual real con API key del usuario, ver Pendiente)

Hecho:
- Antes de escribir código, se separaron en 4 commits distintos (uno por fase) el trabajo de las Fases 3-6 que llevaba varias sesiones sin commitear — el repo solo tenía commits hasta Fase 2. Reconstrucción manual del contenido intermedio de cada fase en los archivos compartidos (`models.py`, `seed.py`, `pyproject.toml`, `src/api/main.py`, `src/api/schemas.py`, `PROGRESS.md`), ya que no todos eran hunks de git limpios. Verificado que el estado final del working tree tras los 4 commits es idéntico al de antes (69/69 tests siguen en verde).
- `docs/behavior_prompt.md` no existía en ningún sitio (ni en el repo ni fuera) — el usuario pidió que lo redactara yo, basado en el roadmap sección 0 (filosofía: no memorizar legalidad/daño/meta) y sección 5 (tabla de tools). Deja explícito qué tools existen ya (las 5 de Fases 5-6) y qué NO existe todavía (`calculate_damage`, `common_sets`, `semantic_search_pokemon`, `get_community_buzz`, `get_counters`/`suggest_meta_response_team`) para que el asistente no las aproxime de memoria cuando se le pidan.
- 2 decisiones de arquitectura confirmadas con el usuario antes de codificar:
  1. Las tools llaman **directamente a las funciones Python** de `src/api/main.py` (in-process), no vía HTTP — más simple para uso local, evita levantar uvicorn aparte para poder chatear. Esto funciona sin ningún refactor: los decoradores de FastAPI (`@app.get`, `@app.post`) devuelven la función original sin modificar, así que `get_legal_pokemon(regulation_id=..., session=...)` etc. se pueden llamar igual que si no tuvieran `@app.get` encima (los sentinels `Depends(...)`/`Query(...)` en los defaults se ignoran al pasar los argumentos explícitos) — se evaluó extraer la lógica a un módulo `logic.py` separado (planteado inicialmente) pero no aportaba nada real, así que se descartó.
  2. La Fase 7 incluye un mini chat loop (`src/cli/chat.py`) para poder probar las tools de verdad con una conversación real, no solo con tests — la Fase 9 lo sustituirá por una CLI típer/rich más completa.
- `src/api/tools.py`: definiciones de las 6 tools en formato Anthropic-style JSON schema (`get_active_regulation`, `get_legal_pokemon`, `get_pokemon_detail`, `get_legal_moves`, `get_meta_usage`, `validate_team`) + `run_tool(name, input) -> dict` que abre su propia `Session`, llama a la función de `main.py` correspondiente y serializa con `.model_dump(mode="json")`. Errores de id/regulation no encontrados (que en `main.py` son `HTTPException`) se capturan y devuelven como `{"error": ...}` en vez de propagar la excepción — el modelo puede reaccionar en vez de que el proceso se caiga.
- **Añadido en la misma sesión, a petición del usuario**: soporte para **Gemini** además de Claude, para poder usar el tier gratuito de Google AI Studio. Confirmado con el usuario: se mantienen ambos proveedores (no se reemplaza Claude), seleccionables vía `LLM_PROVIDER=claude|gemini` en `.env`, con Gemini 2.5 Flash-Lite como modelo por defecto para ese proveedor (el más barato/rápido del catálogo 2.5, con el tier gratuito más generoso en peticiones/día). `src/api/tools.py` no cambió — la misma lista `TOOLS` (JSON schema) sirve para ambos SDKs: el de Anthropic la consume tal cual como `input_schema`, y el de Gemini (`google-genai`) acepta el mismo dict directamente vía `FunctionDeclaration(parameters_json_schema=...)`, sin necesidad de convertir a su tipo `Schema` propio.
- `src/cli/chat.py`: REPL mínimo (`input()`/`print()`), carga `docs/behavior_prompt.md` como system prompt (documento ya escrito de forma agnóstica al proveedor). Dos bucles separados (`_run_claude_loop`/`_run_gemini_loop`), no una interfaz común: Claude y Gemini estructuran el tool-calling de forma bastante distinta (bloques `tool_use`/`tool_result` con `tool_use_id` en Claude vs `Part.function_call`/`Part.from_function_response` dentro de `Content` en Gemini), y con solo 2 proveedores y ninguno más previsto, una abstracción compartida sería especular de más. `main()` elige el bucle según `LLM_PROVIDER` (por defecto `claude` si no se define, para no cambiar de comportamiento a quien no toque `.env`). Sin persistencia de historial en disco en ningún caso — es un REPL de prueba, no la Fase 9. Un pequeño loader manual de `.env` (unas líneas, sin añadir `python-dotenv`) porque el resto del proyecto tampoco cargaba `.env` hasta ahora (`database.py` solo usa `os.environ.get` con default).
- Dependencias nuevas: `anthropic` y `google-genai` en `pyproject.toml`. `.env.example` documenta `LLM_PROVIDER`, `ANTHROPIC_API_KEY` y `GEMINI_API_KEY` (con nota de que la clave de Gemini es gratuita vía Google AI Studio, rate-limited).
- 8 tests nuevos (`tests/test_tools.py`), mismo patrón que `tests/test_api.py` (contra la BD real, aserciones laxas) — no llaman a ninguna API de LLM real (eso se prueba a mano con el chat loop, con cualquiera de los dos proveedores). Se verificó además, sin necesitar API key, que los 6 esquemas de `TOOLS` construyen `FunctionDeclaration`/`Tool`/`GenerateContentConfig` de Gemini sin errores. 77/77 tests en verde en total.

Pendiente:
- **Verificación manual real con el chat loop** (`python -m src.cli.chat`, con `claude` o `gemini`): no se pudo hacer esta sesión porque no hay ningún `.env` con claves configuradas en este entorno. Falta que el usuario añada su clave (Anthropic y/o Gemini) a `.env` y pruebe al menos una pregunta real que dispare una tool call, con cada proveedor que vaya a usar, antes de dar la Fase 7 por verificada del todo.
- Nada más bloqueante para pasar a Fase 8.

Decisiones tomadas (y por qué): ver los puntos confirmados con el usuario arriba (tools in-process sin HTTP, chat loop mínimo incluido en esta fase, soporte dual Claude/Gemini vía `LLM_PROVIDER` en vez de reemplazar uno por otro).

---

## Fase 8 — Automatización de scrapers
Estado: completa

Hecho:
- Decisión confirmada con el usuario antes de codificar: el roadmap sugiere Cron/GitHub Actions, pero `*.db` y `data/raw/` están en `.gitignore` — todo vive solo en la máquina local, así que un workflow de GitHub Actions correría los scrapers contra una BD efímera del runner, no la real. Se descartó GitHub Actions y se usa **Windows Task Scheduler** (uso local personal, sin infra de CI innecesaria — mismo criterio de CLAUDE.md sección 4).
- `src/db/run_pipeline.py` (`python -m src.db.run_pipeline`): orquesta `seed_regulation` → `seed_movepool` → `seed_usage` en orden. Cada paso captura su propio stdout (los tres ya imprimen resúmenes ricos de éxitos/discrepancias desde las Fases 2-4, no hacía falta añadir nada ahí) y sigue con el siguiente paso aunque uno falle — un fallo se registra con traceback completo en vez de abortar en silencio (regla de CLAUDE.md de fallar de forma visible). Escribe un log con timestamp por ejecución en `data/logs/pipeline_<fecha>.log` y devuelve exit code 1 si algo falló.
- Job extra de proximidad de Regulation Set: `_check_regulation_proximity()` calcula días restantes hasta `end_date` de la regulation activa (reutiliza `get_active_regulation` de la Fase 4) y marca `WARNING` si quedan ≤7 días (constante `REGULATION_WARNING_DAYS`).
- `scripts/register_scheduled_task.ps1`: registra una tarea diaria (09:00, working directory = raíz del proyecto) en el Task Scheduler de Windows vía `Register-ScheduledTask`, apuntando al Python del venv. No se ejecutó automáticamente — es el usuario quien la registra corriendo el script una vez, ya que crear una tarea programada es un cambio persistente del sistema fuera del repo.
- 3 tests nuevos (`tests/test_run_pipeline.py`): captura OK/FAILED de un paso (con funciones dummy, no re-ejecuta los scrapers reales — serían lentos y dependientes de red en CI/tests) y el aviso de proximidad contra la BD real ya sembrada. 80/80 tests en verde en total.
- Verificación manual real: `python -m src.db.run_pipeline` ejecutado contra las fuentes en vivo. Regulation (Fase 2) y movepool (Fase 3) → OK, mismos números que sus fases originales. Usage (Fase 4) → **FAILED**, ver discrepancia abajo. El paso falló limpio: el log tiene el traceback completo y, al comprobar la BD después, las 50 filas de `usage_stats` de la Fase 4 (24 jul) seguían intactas — `seed_usage.main()` lanza la excepción al hacer el fetch, antes de borrar ninguna fila existente, así que no hay pérdida ni corrupción de datos. Esto confirma que el pipeline cumple la regla de CLAUDE.md de "fallar de forma visible" tal como estaba pensado.

Pendiente:
- El usuario debe correr `scripts/register_scheduled_task.ps1` él mismo si quiere que la tarea quede programada de verdad en su máquina (no se ha registrado en esta sesión).
- Re-ejecutar `seed_usage` (o el pipeline completo) cuando ChampionsMeta vuelva a tener datos de M-B (ver discrepancia abajo) — no bloqueante para pasar a Fase 9, los `usage_stats` existentes de la Fase 4 se mantienen válidos mientras tanto.

Decisiones tomadas (y por qué): Windows Task Scheduler en vez de GitHub Actions — confirmado con el usuario (ver punto de "Hecho" arriba, motivo: BD/cache no versionados, GitHub Actions no tendría BD real contra la que trabajar).

Discrepancias de datos encontradas:
- **ChampionsMeta `/meta` no tiene datos para M-B ahora mismo** (27 jul): la página renderiza "No Regulation M-B usage rankings yet. Run the tournament sync once M-B events appear on Limitless, then this table will populate from real tournament data." — no es un cambio de estructura HTML (el parser sigue buscando las filas correctas), es que el propio backend de ChampionsMeta no tiene el ranking poblado para esta regulation en este momento, pese a que sí lo tenía el 24 jul (sesión de la Fase 4, 50/50 resueltas). Parece un problema temporal de sincronización de su lado (su propio mensaje lo sugiere). No se tocó `seed_usage.py` para "adivinar" datos alternativos — se deja fallando visiblemente hasta la próxima re-ejecución, según la regla de CLAUDE.md de no inventar ni tapar discrepancias.

---

## Fase 9 — Interfaz de uso (CLI)
Estado: completa

Hecho:
- Modelo nuevo `UserTeam` (`src/db/models.py`), tal cual lo esbozaba el esquema ilustrativo del roadmap (`user_teams`) — sin columnas `source`/`verified` porque un equipo del usuario no es dato scrapeado (mismo criterio ya usado en `NotableTeam` para su `team_json` libre).
- `src/cli/main.py` (`python -m src.cli.main --help`), typer + rich, 3 comandos:
  - `ver-meta [--regulation-id] [--limit]`: tabla rich con el % de uso real (reutiliza directamente la tabla `UsageStat` de la Fase 4).
  - `crear-equipo`: constructor interactivo Pokémon a Pokémon (especie/objeto/habilidad/naturaleza/SP/movimientos), valida con el motor de la Fase 6 al terminar y opcionalmente guarda el equipo en `UserTeam`.
  - `validar-equipo <nombre> [--regulation-id]`: recarga un equipo guardado y lo revalida — por defecto contra la regulation activa (no la que tenía al guardarlo), para poder detectar equipos que dejaron de ser legales tras un cambio de Regulation Set.
  - Reutiliza `resolve_regulation` de `src/api/main.py` importándola directamente (mismo criterio in-process que ya adoptó `src/api/tools.py` en la Fase 7) en vez de duplicar la lógica de "regulation activa vs por id".
- Deps nuevas: `typer`, `rich`.
- 3 tests nuevos (`tests/test_cli.py`, vía `typer.testing.CliRunner` contra la BD real, mismo criterio laxo que el resto de tests de esta fase del proyecto) — cubren `ver-meta`, `validar-equipo` con nombre inexistente, y el roundtrip completo `crear-equipo` → `validar-equipo`. 83/83 tests en verde en total.
- Verificación manual real: `crear-equipo` ejecutado a mano con un Garchomp (Doubles, Jolly, SP en Speed, Earthquake/Dragon Claw/Swords Dance/Protect) — el validador señaló correctamente `team_size` (solo 1 Pokémon) e `illegal_item` (`rocky-helmet` no está en los 141 ítems legales de M-B ya scrapeados en la Fase 3 — confirmado que es un dato real, no un bug). `validar-equipo` releyó el mismo equipo guardado y reprodujo los mismos issues. Probado también en PowerShell real (no solo en la consola de la sesión) para descartar problemas de encoding con "Pokémon" — se ve correcto.

Pendiente:
- Nada bloqueante para pasar a Fase 10. La Fase 10 (tests/mantenimiento) ya viene parcialmente cubierta por los tests que cada fase fue añadiendo por su cuenta.

Decisiones tomadas (y por qué):
- `UserTeam` como tabla SQLModel (no JSON en disco) — reutiliza la misma BD/engine que todo lo demás en vez de inventar un segundo mecanismo de persistencia, y encaja con el `user_teams` que el propio roadmap ya proponía.
- `validar-equipo` revalida contra la regulation **activa** por defecto, no la de creación — es lo que le da valor a tener el comando separado de `crear-equipo` (que ya valida al momento de crear): detectar cuando un Regulation Set nuevo invalida un equipo guardado.

---

## Fase 10 — Pruebas y mantenimiento
Estado: completa

Hecho:
- El roadmap pedía "tests unitarios del validador (crítico)" — ya hecho en la Fase 6 — y "smoke tests de scrapers con selectores robustos y alertas si el parser falla". Cada scraper (Fases 2-4) ya lanzaba su propia excepción `*ScrapeError` cuando un selector no encuentra nada (regla de CLAUDE.md de fallar de forma visible, aplicada desde el principio); lo que faltaba era una comprobación deliberada y periódica contra los sitios reales, separada de sembrar la BD.
- `tests/test_smoke_scrapers.py`: 10 tests (uno por función pública de cada scraper: bulbapedia, victory_road, pokemon_zone, metavgc, serebii ×3, championsmeta ×2, pikalytics), marcados `@pytest.mark.live` — golpean los sitios reales de verdad, no fixtures. Excluidos de la ejecución normal de `pytest` (`addopts = "-m 'not live'"` en `pyproject.toml`), se corren aparte con `pytest -m live`.
- `src/db/smoke_test_scrapers.py` (`python -m src.db.smoke_test_scrapers`): script standalone que llama a las mismas funciones, sin tocar la BD para nada (más rápido y ligero que `run_pipeline.py`, que sí escribe en BD y solo distingue fallos a nivel de sus 3 pasos, no por fuente individual). Escribe `data/logs/smoke_<fecha>.log` con OK/FAILED por fuente y el traceback completo si falla — mismo patrón de alerta que ya usaba `run_pipeline.py` desde la Fase 8.
- Detectado que esta sesión partía de un checkout sin `.venv` ni `data/` (ninguno de los dos viaja en git, correcto según `.gitignore`, pero tampoco estaban ya creados en esta máquina/sesión) — se creó `.venv` (Python 3.11) e instalaron dependencias para poder verificar. La suite offline (66 tests que no dependen de la BD ya sembrada: `type_effectiveness`, `regulation_scrapers`, `movepool_scrapers`, `usage_scrapers`, `team_validator`) pasa en verde. Los tests que sí requieren la BD real ya sembrada (`test_api.py`, `test_cli.py`, `test_tools.py`, `test_run_pipeline.py`) fallan aquí solo porque no hay `data/pokemon_champions.db` en este checkout — no es una regresión de esta sesión, es que faltaba sembrar. No se ejecutó el pipeline completo de seeding para no dar por hecho que había que reconstruir esa base de datos sin comentarlo contigo primero.
- **Ejecución real de `pytest -m live`**: 8/10 fuentes OK (bulbapedia, victory_road, pokemon_zone, metavgc, las 3 de serebii, pikalytics). 2/10 fallaron — ver discrepancia abajo.

Pendiente:
- Confirmar en tu máquina habitual si `.venv`/`data/pokemon_champions.db` existen ahí (deberían, según sesiones anteriores) — si no, hay que re-sembrar (`python -m src.db.seed` → `seed_regulation` → `seed_movepool` → `seed_usage`, o `run_pipeline`) antes de poder correr la suite completa en verde.
- Revisar `championsmeta.py` cuando su sitio confirme que ya no está en el estado "cached data — live results temporarily unavailable" (ver discrepancia) — probablemente no haga falta cambiar nada si es solo una caída temporal de su backend, pero si sigue así varias sesiones más habrá que investigar si de verdad cambiaron a un layout que no expone las tarjetas de torneo como HTML plano.
- Nada bloqueante para pasar a Fase 11.

Decisiones tomadas (y por qué):
- `pytest -m live` como opt-in (no en la ejecución por defecto) — necesitan red real contra sitios de terceros, no tiene sentido que un `pytest` normal dependa de que 7 webs externas estén arriba en ese momento.
- Script standalone (`smoke_test_scrapers.py`) además de los tests de pytest, no solo uno de los dos — los tests de pytest son para verificación manual/CI-style durante desarrollo; el script es para programarlo aparte (Task Scheduler, más barato que el pipeline completo porque no escribe en BD) como chequeo de salud más frecuente que el pipeline diario de la Fase 8.

Discrepancias de datos encontradas:
- **ChampionsMeta (`/meta` y `/tournaments`) sin datos utilizables para M-B ahora mismo (29 jul)**: `/meta` sigue mostrando el mismo hueco que la Fase 8 ya documentó ("Regulation M-B data will appear here as tournament results are imported" — texto distinto al de entonces, mismo hueco de fondo). `/tournaments` es nuevo: la página dice literalmente "Showing cached data — live results temporarily unavailable" y ya no tiene ninguna tarjeta `<div class="rounded-2xl border...">` en el HTML crudo — los datos parecen haberse movido a un payload de Next.js (`self.__next_f.push(...)`) mientras su backend está caído. No se tocó el parser para adivinar el nuevo formato mientras el sitio admite explícitamente que está en un estado degradado/temporal — se deja fallando de forma visible (regla de CLAUDE.md), a revisar si persiste.

---

## Fase 11 — Motor de cálculo de daño
Estado: completa

Hecho:
- **Decisión de stack confirmada contigo antes de codificar** (CLAUDE.md exige justificar especialmente esta pieza): `@smogon/calc` es TypeScript/JS, el proyecto es Python. Se descartó reimplementar la fórmula traducida a mano a Python (mayor superficie para un bug sutil de traducción, justo lo que CLAUDE.md pide evitar en esta fase) a favor de usar la librería real en Node.js vía subprocess — mismo patrón que `pokemon_zone.py` ya usa con `curl` para un problema distinto (Fase 2). Se confirmó que esta máquina tiene Node v24 instalado antes de decidir.
- `src/damage_calc/node/`: subproyecto npm mínimo (`package.json` + `package-lock.json`, ambos versionados; `node_modules/` gitignored) con `@smogon/calc@0.11.0` instalado, y `calc.js`, el puente — lee un request JSON por stdin, valida que especie/habilidad/ítem/movimiento existen en los datos reales de la librería (`gen.species/abilities/items/moves.get(...)`) y falla alto y claro si no (ver discrepancia/bug de items exclusivos abajo), construye `Pokemon`/`Move`/`Field` y llama a `calc.calculate()` sin tocar la fórmula.
- `src/damage_calc/stats.py`: fórmula de stats finales de Champions (nivel 50, IV 31 fijos, SP en vez de EVs). Verificada cruzando 2 fuentes independientes que la dan en formas distintas pero algebraicamente equivalentes: ChampsDex la da paso a paso con floors explícitos (`floor(floor((2*base+31)*50/100)+5+sp)*nature`), RotomLabs la da ya simplificada (`HP=base+75+sp`, `otros=(base+20+sp)*nature`) — se comprobó a mano que la primera se reduce exactamente a la segunda a nivel 50/IV 31 (el floor intermedio desaparece porque `2*base+31` siempre es impar). Implementado con aritmética entera (`(x*11)//10` / `(x*9)//10` en vez de `x*1.1`/`x*0.9`) para no depender de que el float64 nunca redondee un pelo por debajo de un entero — comprobado que no pasa en el rango realista, pero mejor que sea exacto por construcción.
- `src/damage_calc/calculator.py`: `calculate_damage(session, attacker, defender, move_name, field)` — resuelve especie/naturaleza contra la BD real (Fase 1), calcula los stats finales con `stats.py`, arma el request y lo manda al bridge de Node por subprocess (`cwd` fijado al subproyecto para que `require` resuelva). Construye el desglose de modificadores en Champions (ítem/habilidad/naturaleza/SP/boosts/estado/clima/terreno/pantallas) a partir del `rawDesc` estructurado de la librería en vez de su `desc()`/`fullDesc()` con vocabulario de EVs, que no tiene sentido para Champions.
- **Bug real encontrado y corregido durante la verificación, antes de fijar los valores esperados de los tests**: el primer enfoque asignaba `pokemon.rawStats = {...}` después de construir el objeto. Parecía funcionar (los números salían plausibles) hasta que se aisló con un caso de números redondos ajenos a cualquier Pokémon real (Machamp/Snorlax con stats inventados) — el resultado no cambiaba pasara lo que pasara en `rawStats`. Traza completa: `calc.calculate()` clona `attacker`/`defender` internamente (`attacker.clone()`) antes de calcular, y `clone()` reconstruye el Pokémon vía el constructor normal (`ivs`/`evs`/`nature`/`level`), que descarta cualquier mutación manual de `.rawStats` hecha después de construir — es decir, el SP y la naturaleza nunca se estaban aplicando de verdad, silenciosamente. Arreglado usando el único canal que sí sobrevive al clone: `overrides.baseStats`, que parchea los stats base de la especie que ve el propio `calcStat()` interno de la librería. Como a IV 31/EV 0/naturaleza neutra/nivel 50 la fórmula de la librería se reduce a `stat = base+20+sp` (`+75` para HP), el "base falso" a enviar es simplemente `stat_final - 20` (`- 75` para HP) — una inversión algebraica exacta, no la conversión SP→EV con pérdida que el roadmap ya advertía evitar.
- Endpoint `POST /damage/calculate` (`src/api/main.py`) y tool `calculate_damage` (`src/api/tools.py`), mismo patrón in-process que el resto desde la Fase 7. `docs/behavior_prompt.md` actualizado: la tool pasa de la lista "todavía no puedes hacer" a la tabla de tools disponibles, con una nota de que puede fallar en contenido exclusivo de Champions (ver siguiente punto) y que ese fallo hay que decirlo tal cual, no aproximarlo.
- 15 tests nuevos (`tests/test_stats.py`: 6: fórmula HP/stats/flooring exactos a mano; `tests/test_damage_calc.py`: 9, contra la librería real sin mocks, con una BD SQLite en memoria igual que `test_team_validator.py`). El caso `test_regression_case_matches_hand_derived_formula` (Machamp Fighting usando Tackle Normal = sin STAB, para aislar la fórmula) es el que detectó el bug de arriba: con el bug, pasaba con números plausibles pero incorrectos; con el fix, coincide exactamente con el cálculo a mano de `getBaseDamage` (rango 31-37). 2 tests más cubren que un objeto exclusivo de Champions (`Sceptileite`) y una especie/movimiento inexistente fallan de forma visible en vez de devolver un número silenciosamente incorrecto. 99/99 tests offline en verde (+ los que dependen de la BD real sembrada, no verificables en este checkout — ver Fase 10).
- Verificación manual cruzada con fuentes externas (no automatizable con estas herramientas — las calculadoras públicas de Champions son SPA renderizadas en cliente): se contrastó la fórmula de stats (no el motor de daño en sí) contra ChampsDex y RotomLabs como se describe arriba. El motor de daño en sí se verifica por construcción al ser literalmente `@smogon/calc` sin tocar, más el caso de regresión con números redondos hand-verificado independientemente.

Pendiente:
- **Limitación conocida, no arreglable sin datos que no existen**: las 7 Mega Piedras exclusivas de Champions encontradas en la Fase 3 (Barbaracleite, Dragalgeite, Mawileite, Sceptileite, Scolipedeite, Scraftyite, Staraptorite) no están en los datos de `@smogon/calc` (confirmado, ninguna aparece en `gen.items`) porque no existen en los juegos principales. `calculate_damage` falla de forma clara para ellas (`Unknown item '...'`) en vez de calcular sin el efecto de la Mega — correcto según la regla de fallar visible, pero significa que el daño de esas 7 Megas concretas no se puede calcular hasta que se modele su contenido a mano (mismo hueco ya anotado en Fases 2-3, ahora con un tercer sitio afectado).
- No se implementó el golpe crítico como variante aparte (solo el rango estándar no-crítico, que es lo que pide el roadmap explícitamente) — se podría añadir un flag `is_crit` más adelante si hace falta, no se ha añadido de forma especulativa.
- Los tests de `test_api.py`/`test_tools.py` para `/damage/calculate`/`calculate_damage` siguen el mismo patrón que el resto (BD real, no fixture) — no verificables en este checkout por el mismo motivo que el resto de tests de BD real (Fase 10: sin `data/pokemon_champions.db` sembrada aquí).
- Nada bloqueante para pasar a Fase 12.

Decisiones tomadas (y por qué):
- Node.js real vía subprocess, no traducción a Python — confirmado contigo antes de codificar (ver arriba).
- Devolver el `rawDesc` estructurado de la librería y construir el desglose de modificadores en Python, en vez de usar `desc()`/`fullDesc()` de la librería (pensados para builds con EVs/naturaleza clásicas, vocabulario que no encaja con SP).
- `overrides.baseStats` como canal de inyección de stats en vez de mutar `.rawStats` tras construir — no es una preferencia de estilo, es la única forma que sobrevive al `clone()` interno de `calculate()` (ver bug arriba).

---

## Sesión post-Fase 11 — columna `in_champions`
Motivada por tu pregunta de si `pokemon_species` guarda solo el roster de Champions o los ~1350 de PokeAPI (era lo segundo). Confirmado contigo antes de tocar el esquema: mantener la tabla completa (no borrar nada — una regulation futura puede reactivar cualquier especie, y borrar filas rompería `UsageStat`/`NotableTeam` de regulations pasadas), y añadir un flag booleano en vez de filtrar solo en la capa de API.

Hecho:
- `PokemonSpecies.in_champions: bool` (`src/db/models.py`) — a diferencia de `RegulationLegalPokemon` (legalidad de UNA regulation concreta), este flag es acumulado: se pone `True` la primera vez que la especie aparece en el roster legal de CUALQUIER regulation ya scrapeada (M-A, M-B, la que sea), y nunca se resetea a `False` si luego rota fuera de la regulation activa — confirmado contigo que esa era la semántica que querías, no "legal ahora mismo" (eso ya lo daba `RegulationLegalPokemon`).
- `seed_regulation.py` marca `in_champions=True` para cada especie resuelta (verificada o no) cada vez que corre — se automantiene solo, no hay que tocarlo a mano, así que no puede quedar desactualizado como sí le pasaría a un flag puesto una sola vez.
- `GET /pokemon/{id}` / tool `get_pokemon_detail` ahora devuelven `in_champions` junto a `legal_in_regulation` (que ya existía) — distinción explicada en `docs/behavior_prompt.md`, que de paso ganó la fila que le faltaba para `get_pokemon_detail` (estaba definida en `tools.py` desde la Fase 7 pero nunca se documentó en el prompt de comportamiento).
- No se tocó `calculate_damage`: a propósito sigue sin comprobar legalidad de ningún tipo (ni `RegulationLegalPokemon` ni `in_champions`), igual que ya no comprobaba legalidad de ítems/movimientos — es una calculadora para cualquier build que YA has decidido, no un segundo validador.
- Cambio de esquema en una tabla ya existente, sin Alembic todavía (roadmap lo deja "más adelante") — se documenta aquí en vez de escribir una migración ad-hoc: si tienes ya una `data/pokemon_champions.db` sembrada, hace falta borrarla y volver a sembrar (`python -m src.db.seed` → `seed_regulation` o `run_pipeline`) para que SQLite tenga la columna nueva; `SQLModel.metadata.create_all()` no altera tablas ya existentes.
- 86/86 tests offline en verde tras el cambio (mismos 16 fallos preexistentes de siempre por falta de BD real sembrada en este checkout, ver Fase 10 — ninguno nuevo).

Pendiente:
- Nada bloqueante. Si en algún momento se quiere consultar "todo lo que ha sido de Champions alguna vez" desde el CLI/chat (no solo por id), se puede añadir un endpoint/tool `GET /pokemon/champions-roster` que filtre por `in_champions=true` — no se ha añadido porque nadie lo ha pedido todavía.

---

## Próxima sesión
Borrar y re-sembrar `data/pokemon_champions.db` en tu máquina habitual para que recoja la columna `in_champions` nueva (ver arriba) antes de fiarte de la suite completa de Fases 5-9/11. Correr `npm install` en `src/damage_calc/node/` si no se ha hecho ya en esa máquina. Re-correr `pytest -m live` en unos días para ver si ChampionsMeta ya salió de su estado "cached data/temporarily unavailable" (Fase 10). Después, empezar Fase 12 — búsqueda semántica sobre el roster legal (embeddings + Chroma/LanceDB, búsqueda híbrida filtro-estructurado + similitud).
