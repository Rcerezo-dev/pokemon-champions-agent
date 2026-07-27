"""Minimal REPL to manually exercise the Fase 7 tool integration end-to-end.
Fase 9 replaces this with a proper typer/rich CLI -- this is just enough to
talk to an LLM with the Fase 5-6 tools wired in and confirm it doesn't
hallucinate legality/usage data.

Provider is chosen via LLM_PROVIDER=claude|gemini (default: claude). Claude
and Gemini shape tool-calling completely differently (message/part formats,
how a tool result gets sent back), so this is two separate small loops
rather than one abstraction over both -- with only two providers and no
third planned, a shared interface would be speculative.

Run: python -m src.cli.chat
"""

import os
from pathlib import Path

from src.api.tools import TOOLS, run_tool

CLAUDE_MODEL = "claude-sonnet-5"
GEMINI_MODEL = "gemini-2.5-flash-lite"
_ROOT = Path(__file__).resolve().parents[2]
_BEHAVIOR_PROMPT_PATH = _ROOT / "docs" / "behavior_prompt.md"


def _load_env_file(path: Path) -> None:
    """Tiny stand-in for python-dotenv: this repo has no dotenv dependency
    and DATABASE_URL already gets by with a plain os.environ.get default, so
    a new dependency for a few KEY=VALUE lines isn't worth it."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _run_claude_loop(system_prompt: str) -> None:
    from anthropic import Anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("Falta ANTHROPIC_API_KEY en .env (ver .env.example).")
    client = Anthropic(api_key=api_key)
    messages: list[dict] = []

    print("Asistente de Pokemon Champions -- Claude (Ctrl+C para salir)")
    while True:
        try:
            user_input = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input.strip():
            continue
        messages.append({"role": "user", "content": user_input})

        while True:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                system=system_prompt,
                tools=TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                for block in response.content:
                    if block.type == "text":
                        print(block.text)
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input)
                    tool_results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": str(result)}
                    )
            messages.append({"role": "user", "content": tool_results})


def _run_gemini_loop(system_prompt: str) -> None:
    from google.genai import Client
    from google.genai import types

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("Falta GEMINI_API_KEY en .env (ver .env.example).")
    client = Client(api_key=api_key)
    gemini_tools = [
        types.Tool(
            function_declarations=[
                types.FunctionDeclaration(name=t["name"], description=t["description"], parameters_json_schema=t["input_schema"])
                for t in TOOLS
            ]
        )
    ]
    config = types.GenerateContentConfig(system_instruction=system_prompt, tools=gemini_tools)
    contents: list[types.Content] = []

    print("Asistente de Pokemon Champions -- Gemini 2.5 Flash-Lite (Ctrl+C para salir)")
    while True:
        try:
            user_input = input("\n> ")
        except (EOFError, KeyboardInterrupt):
            break
        if not user_input.strip():
            continue
        contents.append(types.Content(role="user", parts=[types.Part(text=user_input)]))

        while True:
            response = client.models.generate_content(model=GEMINI_MODEL, contents=contents, config=config)
            candidate = response.candidates[0]
            contents.append(candidate.content)

            function_calls = [p.function_call for p in candidate.content.parts if p.function_call]
            if not function_calls:
                for part in candidate.content.parts:
                    if part.text:
                        print(part.text)
                break

            response_parts = [
                types.Part.from_function_response(name=fc.name, response={"result": run_tool(fc.name, dict(fc.args or {}))})
                for fc in function_calls
            ]
            contents.append(types.Content(role="user", parts=response_parts))


def main() -> None:
    _load_env_file(_ROOT / ".env")
    provider = os.environ.get("LLM_PROVIDER", "claude").strip().lower()
    system_prompt = _BEHAVIOR_PROMPT_PATH.read_text(encoding="utf-8")

    if provider == "gemini":
        _run_gemini_loop(system_prompt)
    elif provider == "claude":
        _run_claude_loop(system_prompt)
    else:
        raise SystemExit(f"LLM_PROVIDER desconocido: '{provider}' (usa 'claude' o 'gemini').")


if __name__ == "__main__":
    main()
