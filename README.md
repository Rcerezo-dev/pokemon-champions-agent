# Asistente de Equipos de Pokémon Champions

Asistente personal, de uso local, para construir y optimizar equipos competitivos de
**Pokémon Champions**. La legalidad, el meta y (más adelante) los cálculos de daño se
apoyan en una base de datos propia alimentada por scrapers, no en el recuerdo del modelo.

Ver `CLAUDE.md` (guía operativa) y `docs/roadmap.md` (plan técnico completo de 14 fases)
para el contexto completo. `PROGRESS.md` tiene el estado fase a fase.

## Setup (PC nuevo)

```bash
git clone https://github.com/Rcerezo-dev/pokemon-champions-agent.git
cd pokemon-champions-agent

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -e ".[dev]"

copy .env.example .env        # Windows
# cp .env.example .env        # Linux/Mac
# edita .env: ANTHROPIC_API_KEY y/o GEMINI_API_KEY, LLM_PROVIDER=claude|gemini

# Fase 11 (calculadora de daño) necesita Node.js instalado y adapta la
# libreria real @smogon/calc via un subproceso -- ver PROGRESS.md Fase 11
cd src/damage_calc/node && npm install && cd ../../..
```

La base de datos (`data/pokemon_champions.db`) y el cache crudo de scraping (`data/raw/`)
**no viajan en el repo** (están en `.gitignore`, son regenerables) — hay que sembrarlos:

```bash
python -m src.db.seed              # Fase 1: species/moves/abilities/natures/items (PokeAPI)
python -m src.db.seed_regulation   # Fase 2: Regulation Set activo + roster legal
python -m src.db.seed_movepool     # Fase 3: items/movepool legales
python -m src.db.seed_usage        # Fase 4: % de uso real + equipos de torneos

# o los tres últimos de una vez, con logging (Fase 8):
python -m src.db.run_pipeline
```

Cada seed cachea sus respuestas en `data/raw/<fuente>/` (por fecha), así que reejecutarlo
el mismo día no vuelve a golpear la web.

## Probar que funciona

```bash
pytest                              # 80+ tests, todos offline o contra la BD ya sembrada
pytest -m live                      # opcional: smoke tests contra las webs reales (Fase 10)

uvicorn src.api.main:app --reload   # API en http://127.0.0.1:8000/docs

python -m src.cli.chat              # chat con tools (Claude o Gemini, según LLM_PROVIDER)

python -m src.cli.main ver-meta                 # top de uso real en torneos
python -m src.cli.main crear-equipo             # construir un equipo paso a paso
python -m src.cli.main validar-equipo <nombre>  # revalidar un equipo ya guardado
```

## Automatización (Fase 8, opcional)

Para que `run_pipeline.py` corra solo cada día (Windows Task Scheduler):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\register_scheduled_task.ps1
```

## Estructura

```
/docs             roadmap.md, behavior_prompt.md
/src
  /scrapers       un módulo por fuente
  /db             modelos SQLModel + scripts de seed + orquestador (Fase 8)
  /validation      motor de validación de equipos (Fase 6)
  /damage_calc    calculadora de daño (Fase 11): stats.py (formula SP) + calculator.py
                  (bridge a node/calc.js, que adapta la libreria real @smogon/calc)
  /api            FastAPI + definición de tools para el LLM (Fase 5/7/11)
  /cli            chat REPL (Fase 7)
/data/raw         HTML/JSON cacheado por scraper y fecha (gitignored)
/tests
```
