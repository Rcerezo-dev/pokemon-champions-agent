# ROADMAP TÉCNICO CONSOLIDADO — Asistente de Equipos de Pokémon Champions

> Documento único de ejecución para dárselo a Claude Code, fase por fase. Sustituye a los dos borradores anteriores (`roadmap_tecnico_pokemon_champions.md` y `roadmap_ampliacion_calculadora_ia.md`), que quedan integrados aquí. Combínalo con el prompt de comportamiento (`asistente_pokemon_champions_prompt.md`): ese define **cómo debe razonar** el asistente; este define **qué hay que construir** para que tenga datos frescos, cálculos fiables y capacidad de búsqueda/recomendación.

---

## 0. Filosofía del proyecto

Claude no debe "recordar" ni "opinar de memoria" sobre legalidad, daño o meta — todo eso caduca o se puede calcular mal. La arquitectura correcta es:

```
[Scrapers de reglas/roster/meta]      [Scraper mensual de "buzz" comunitario]
              ↓                                      ↓
   [BD: hechos verificados, versionados por Regulation Set]   [BD: percepción/opinión]
              ↓                                      ↓
   ┌────────────────────────────────────────────────────────────────┐
   │                     API interna (FastAPI)                       │
   │  · datos legales/uso   · motor de daño   · búsqueda semántica   │
   │  · validador de equipos · motor de counters/estrategia          │
   └────────────────────────────────────────────────────────────────┘
                                ↓
                Claude (tool use) — razona y explica, no memoriza
```

Cada afirmación estratégica (legalidad, % de uso, daño, counter) debe quedar respaldada por un dato consultado o un cálculo determinista, no por la memoria del modelo.

---

## 1. Stack tecnológico

| Capa | Tecnología sugerida | Por qué |
|---|---|---|
| Lenguaje principal | Python 3.11+ | Mejor ecosistema de scraping/datos |
| Scraping estático | `httpx` + `BeautifulSoup4` | Páginas HTML simples (Serebii, Bulbapedia) |
| Scraping dinámico (JS) | `Playwright` | Sitios con contenido cargado por JS (Pikalytics, ChampsDex) |
| Base de datos relacional | **SQLite** para empezar → **PostgreSQL** si escala | Postgres además permite `pgvector` para la parte semántica |
| Base de datos vectorial | `pgvector` (si Postgres) o `Chroma`/`LanceDB` (si SQLite) | Para la búsqueda semántica (Fase 12) |
| ORM / migraciones | `SQLModel`/`SQLAlchemy` + `Alembic` | Tipado y versionado de esquema |
| Motor de daño | Adaptación de **`@smogon/calc`** (librería open source de Pokémon Showdown) | Ya resuelve STAB, tipos, clima, objetos, habilidades, Dobles — no reinventar la rueda |
| API interna | `FastAPI` | Expone datos y cálculos como tools consultables |
| Programación de tareas | `cron` o `GitHub Actions` (schedule) | Scrapers automáticos |
| Capa conversacional | Claude API (tool use) sobre la API interna | El prompt de comportamiento ya escrito es el system prompt de esta integración |
| Frontend | CLI (`typer`/`rich`) para el MVP; web opcional más adelante | No bloquear el proyecto con UI al principio |
| Caché de contenido scrapeado | HTML crudo con fecha en `/data/raw/` | Permite reprocesar sin re-scrapear si cambia el parser |

---

## 2. Fuentes de datos

⚠️ Revisa `robots.txt` y términos de uso de cada sitio; limita frecuencia de peticiones, usa user-agent identificable y caché local; prioriza APIs oficiales cuando existan.

| Fuente | Qué obtener | Tipo |
|---|---|---|
| **PokeAPI** (API oficial gratuita) | Tabla de tipos, stats base, movepool general, habilidades — no cambia entre regulations | Estático, vía API real |
| **Pokémon-Zone (Champions)** | Regulation Set activo, fechas, roster/objetos legales, stats de meta | Scraping periódico |
| **Serebii (Champions)** | Roster oficial, movepools específicos, ítems | Scraping periódico |
| **ChampsDex** | Legalidad por regulation, tier lists, guías de formato | Scraping periódico |
| **Pikalytics (Champions)** | % de uso real en torneos, sets recomendados | Scraping periódico (Playwright) |
| **Victory Road** | Reglas oficiales de cada Regulation Set (bans, mecánicas activas) | Scraping puntual, cambia poco |
| **Bulbapedia** | Verificación cruzada del roster y vigencia del regulation | Scraping periódico, buena fuente de contraste |
| **Smogon/Victory Road foros, Reddit (API oficial), YouTube (Data API)** | Percepción/opinión de la comunidad sobre qué es meta ahora mismo | Scraping/API mensual (Fase 13) |
| **Reportes de torneos (Limitless VGC / MetaVGC)** | Equipos destacados en eventos recientes | Scraping puntual tras cada torneo grande |

**Regla de fiabilidad**: todo dato sensible (legalidad, % uso, percepción) se guarda con **fuente** y **fecha de obtención**, y se marca `verified = true` solo si se contrasta entre ≥2 fuentes.

---

## 3. Esquema de base de datos

```sql
-- Estáticos (PokeAPI, casi no cambian)
pokemon_species (id, name, types, base_stats_json)
moves (id, name, type, category, power, accuracy, pp, effect_text)
abilities (id, name, effect_text)
items (id, name, category, effect_text)
natures (id, name, boosted_stat, lowered_stat)
type_chart (attacking_type, defending_type, multiplier)

-- Propios de Champions, versionados por regulation
regulation_sets (id, name, start_date, end_date, mega_allowed, notes)
regulation_legal_pokemon (regulation_id, pokemon_species_id, mega_allowed_for_this)
regulation_legal_items (regulation_id, item_id)
regulation_legal_moves (regulation_id, pokemon_species_id, move_id)

-- Meta duro (con fuente y fecha)
usage_stats (regulation_id, pokemon_species_id, usage_pct, source, retrieved_at)
common_sets (regulation_id, pokemon_species_id, item_id, ability_id, nature_id,
             move_ids_json, sp_spread_json, usage_pct, source, retrieved_at)
notable_teams (id, regulation_id, name, source_event, placement, team_json, source_url, retrieved_at)

-- Percepción comunitaria (Fase 13) — separada de los datos duros a propósito
community_meta_snapshots (id, date, source, summary_text, mentioned_pokemon_json, sentiment)

-- Búsqueda semántica (Fase 12)
pokemon_embeddings (pokemon_species_id, regulation_id, doc_text, embedding_vector)

-- Generados por el usuario
user_teams (id, created_at, regulation_id, name, format, team_json)
```

---

## 4. Fases de construcción

### Fase 1 — Fundamentos de datos estáticos
Montar el proyecto, cliente de PokeAPI (tipos, stats base, habilidades, movimientos), seed de naturalezas, test de cálculo de efectividad de tipos.

### Fase 2 — Scraper del Regulation Set activo
Extraer nombre, fechas y roster legal desde Pokémon-Zone/Victory Road/Bulbapedia; guardar HTML crudo; contrastar entre ≥2 fuentes.

### Fase 3 — Scraper de objetos y movepools legales
Ítems permitidos por regulation y movepool real por Pokémon dentro de Champions (Serebii/ChampsDex).

### Fase 4 — Scraper de meta/uso competitivo (datos duros)
% de uso y sets comunes desde Pikalytics; equipos destacados de torneos (Limitless/MetaVGC) → `notable_teams`.

### Fase 5 — API interna (FastAPI)
Endpoints: `GET /regulation/active`, `GET /pokemon/legal`, `GET /pokemon/{id}/legal-moves`, `GET /meta/top-usage`, `POST /team/validate`.

### Fase 6 — Motor de validación de equipos
Reglas deterministas: sin especies repetidas, sin objetos repetidos, SP total 66 (máx 32/stat), máx. 1 Mega, movimientos/objetos legales según regulation activo.

### Fase 7 — Integración con Claude (capa conversacional)
Exponer las funciones de la API como tools de Claude; system prompt = documento de comportamiento ya escrito, adaptado para usar tools en vez de "buscar en la web" directamente.

### Fase 8 — Automatización de scrapers
Cron/GitHub Actions ejecutando Fases 2-4 periódicamente; job extra que detecte proximidad de cambio de Regulation Set; logging de cada ejecución (éxitos, filas actualizadas, discrepancias).

### Fase 9 — Interfaz de uso
MVP en CLI (`typer`/`rich`): `crear-equipo`, `validar-equipo`, `ver-meta`. Web opcional más adelante.

### Fase 10 — Pruebas y mantenimiento
Tests unitarios del validador (crítico), smoke tests de scrapers con selectores robustos y alertas si el parser falla.

### Fase 11 — Motor / agente de cálculo de daño
- **Entrada**: build completa de atacante y defensor (stats base + SP + naturaleza + nivel 50 fijo + objeto + habilidad + boosts -6/+6) + movimiento + condiciones de campo (clima, terreno, pantallas, Dobles con objetivo compartido).
- **Salida**: rango de daño mín-máx, % de HP, probabilidad de KO, desglose de modificadores aplicados (STAB, tipo, clima, objeto, habilidad, pantalla) para poder explicar el resultado.
- **Implementación**: adaptar `@smogon/calc` en vez de escribir la fórmula desde cero. Ajustar: nivel fijo 50, IVs fijos en 31, y sobre todo **SP en vez de EVs** — mejor reimplementar solo la fórmula de stats finales de Champions (1 SP = +1 directo) y pasarle a la librería los stats ya calculados, en vez de intentar convertir SP→EV clásico. Desactivar Tera/Dynamax/Z-Moves (no existen en Champions).
- **Pantallas**: ×0.5 (×0.66 en Dobles) al tipo de daño correspondiente, como un modificador más de campo.
- Tests contra casos conocidos comparando con la calculadora pública de Showdown/ChampsDex.
- Expuesto como tool: `calculate_damage(attacker_build, defender_build, move, field_conditions)`.

### Fase 12 — Búsqueda semántica
- Generar un documento de texto por Pokémon legal (tipos, stats, habilidades con su efecto, movimientos destacados, rol típico, ítems comunes).
- Embeddings guardados en `pgvector` (o Chroma/LanceDB si se usa SQLite).
- Búsqueda **híbrida**: filtro estructurado primero (tipo, legalidad en regulation activo) → ranking por similitud semántica sobre ese subconjunto.
- Regenerar documentos/embeddings cada vez que cambie el roster o los movesets (enganchado a la Fase 8).
- Tool: `semantic_search_pokemon(query, filters?)`.

### Fase 13 — Scraping mensual de percepción comunitaria
- Diferencia con la Fase 4: aquí es **opinión/tendencia**, no estadística de torneos.
- Fuentes: foros (Smogon, Victory Road), Reddit (API oficial), YouTube (Data API); Twitter/X opcional si la API lo permite.
- Proceso: recolectar texto reciente (~4 semanas) → resumen con Claude extrayendo Pokémon/estrategias más mencionados, sentimiento, y contraste con los datos duros de la Fase 4 (si algo "se dice fuerte" pero no aparece en el uso real, es una señal interesante a destacar).
- Guardar en `community_meta_snapshots`.
- Cadencia: cron mensual + disparo extra al empezar un Regulation Set nuevo.
- Tool: `get_community_buzz()`.

### Fase 14 — Motor de recomendación de estrategias y counters
- Entradas: uso duro (Fase 4), percepción comunitaria (Fase 13), motor de daño (Fase 11), tabla de tipos/roster (Fases 1-2).
- **Counters a un Pokémon/core dado**: filtro por resistencias de tipo → simulación de daño real con la Fase 11 (¿le hace >50%? ¿aguanta su golpe más fuerte?) → comparación de velocidad → contraste con lo que la comunidad ya reporta como respuesta → salida ordenada con explicación del matchup, no solo "esto es fuerte contra eso".
- **Sugerencia de equipo "anti-meta"**: identificar huecos que respondan bien a los Pokémon/cores más populares del momento (Fase 4+13) y proponer un equipo alrededor, usando el flujo de construcción ya definido en el prompt de comportamiento.
- Tools: `get_counters(target_pokemon_or_core)`, `suggest_meta_response_team(regulation_id)`.

---

## 5. Tools que el sistema expone a Claude (resumen)

| Tool | Fase | Qué hace |
|---|---|---|
| `get_active_regulation` | 5 | Regulation Set vigente y sus fechas |
| `get_legal_pokemon` / `get_legal_moves` | 5 | Roster y movepool legales ahora mismo |
| `get_meta_usage` | 5 | % de uso real y sets comunes |
| `validate_team` | 6 | Valida un equipo contra todas las reglas de Champions |
| `calculate_damage` | 11 | Rango de daño / HP% / KO-chance entre dos builds con condiciones de campo |
| `semantic_search_pokemon` | 12 | Búsqueda en lenguaje natural sobre el roster legal actual |
| `get_community_buzz` | 13 | Última percepción comunitaria sobre el meta |
| `get_counters` / `suggest_meta_response_team` | 14 | Recomendaciones de counters o equipos anti-meta |

---

## 6. Orden de trabajo recomendado con Claude Code

1. **Fases 1-6**: sin roster/legalidad/validación fiables, nada de lo demás tiene sentido — cerrarlas primero.
2. **Fase 7**: conectar Claude ya con datos reales, para evitar que "alucine" mientras se construye el resto.
3. **Fase 8**: automatizar el pipeline manual una vez funcione sin errores.
4. **Fase 9-10**: interfaz mínima + tests, para poder usar el sistema mientras se sigue ampliando.
5. **Fase 11 (calculadora de daño)**: siguiente prioridad — es independiente de las Fases 12-14 y aporta muchísimo valor por sí sola.
6. **Fase 12 (búsqueda semántica)**: depende de tener bien poblados los documentos de cada Pokémon (roster + habilidades + movimientos).
7. **Fase 13 (buzz comunitario)**: la menos crítica al principio, se puede dejar para más adelante.
8. **Fase 14 (counters/estrategia)**: la última, porque depende de que las tres anteriores ya funcionen.

---

## 7. Notas importantes

- No existe API oficial de Pokémon Champions: todo lo específico del juego depende de scraping a webs de comunidad, así que la fiabilidad depende de contrastar fuentes y fechar cada dato.
- Diseña los scrapers para que **fallen de forma visible** (log/alerta) en vez de guardar datos corruptos silenciosamente — los sitios de terceros cambian su HTML sin aviso.
- Mantén siempre separados los **datos duros** (uso real de torneos) de la **percepción comunitaria** (lo que se comenta en foros/redes) — son señales de fiabilidad distinta y mezclarlas produce conclusiones erróneas.
- Cada respuesta estratégica de Claude (legalidad, daño, counters) debe apoyarse en una tool, no en su memoria — es lo que hace el sistema auditable y evita alucinaciones.
