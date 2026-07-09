#!/usr/bin/env python3
"""Refresh infrastructure/ai/model_context.py from lobehub/lobe-chat model metadata.

Pulls every packages/model-bank/src/aiModels/*.ts file at a given tag (default:
latest stable), extracts per-model contextWindowTokens + maxOutput, and rewrites
the data dicts in infrastructure/ai/model_context.py while preserving the resolver
functions below the data.

On id conflicts the model's own vendor (by id-family prefix) wins over
proxy/aggregate providers.

Usage:
    scripts/refresh_model_context.py                 # latest stable tag
    scripts/refresh_model_context.py --tag v2.2.9    # specific tag
    scripts/refresh_model_context.py --dry-run       # print summary, no write
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path

REPO = "lobehub/lobe-chat"
AI_MODELS_DIR = "packages/model-bank/src/aiModels"
OUTPUT = Path(__file__).resolve().parents[1] / "infrastructure/ai/model_context.py"

# id-family prefix -> the vendor that actually produces the model. Used to break
# ties when the same id appears in multiple providers (vendor > proxy).
FAMILY = {
    "glm": "zhipu", "chatglm": "zhipu",
    "qwen": "qwen", "qwq": "qwen",
    "deepseek": "deepseek",
    "gpt": "openai", "o1": "openai", "o3": "openai", "o4": "openai",
    "claude": "anthropic",
    "gemini": "google", "gemma": "google",
    "moonshot": "moonshot", "kimi": "moonshot",
    "yi-": "zeroone", "yi1": "zeroone",
    "doubao": "volcengine",
    "mixtral": "mistral", "mistral": "mistral", "magistral": "mistral", "codestral": "mistral",
    "minimax": "minimax", "abab": "minimax",
    "spark": "spark",
    "hunyuan": "hunyuan",
    "ernie": "wenxin", "wenxin": "wenxin",
    "command": "cohere",
    "grok": "xai",
    "internlm": "internlm",
    "upstage": "upstage", "solar": "upstage",
    "taichu": "taichu",
    "baichuan": "baichuan",
    "step": "stepfun",
    "sensenova": "sensenova",
    "phi": "openai",
}


def _http_json(url: str):
    with urllib.request.urlopen(url, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _http_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=30) as resp:
        return resp.read().decode()


def latest_stable_tag() -> str:
    tags = _http_json(f"https://api.github.com/repos/{REPO}/tags?per_page=100")
    # first non-canary tag is the latest stable
    for t in tags:
        name = t["name"]
        if "canary" not in name:
            return name
    return tags[0]["name"]


def owner_of(model_id: str) -> str | None:
    mid = model_id.lower()
    for prefix, prov in FAMILY.items():
        if mid.startswith(prefix) or f"-{prefix}" in mid or f"/{prefix}" in mid:
            return prov
    return None


def _eval_expr(s: str) -> int | None:
    total = 0
    for part in s.strip().rstrip(",").split("+"):
        part = part.strip().replace("_", "")
        if not part:
            continue
        try:
            total += int(part)
        except ValueError:
            return None
    return total


def _split_objects(text: str) -> list[str]:
    blocks, depth, start = [], 0, None
    for i, c in enumerate(text):
        if c == "{":
            if depth == 0:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0 and start is not None:
                blocks.append(text[start : i + 1])
                start = None
    return blocks


def extract(files: dict[str, str]) -> tuple[dict[str, int], dict[str, int]]:
    context: dict[str, int] = {}
    max_output: dict[str, int] = {}
    sources: dict[str, tuple[str, int]] = {}

    def priority(provider: str, model_id: str) -> int:
        owner = owner_of(model_id)
        if owner and provider == owner:
            return 3
        if owner and provider != owner:
            return 0
        canonical = {
            "openai", "anthropic", "google", "deepseek", "qwen", "zhipu", "minimax", "moonshot",
            "mistral", "xai", "perplexity", "ai21", "zeroone", "stepfun", "baichuan", "spark",
            "hunyuan", "wenxin", "sensenova", "internlm", "upstage", "taichu", "cohere", "nvidia",
        }
        return 2 if provider in canonical else 1

    for provider, text in files.items():
        for blk in _split_objects(text):
            id_m = re.search(r"id:\s*['\"]([^'\"]+)['\"]", blk)
            tok_m = re.search(r"contextWindowTokens:\s*([^,\n]+)", blk)
            out_m = re.search(r"maxOutput:\s*(\d[\d_]*)", blk)
            if not id_m or not tok_m:
                continue
            mid = id_m.group(1)
            tokens = _eval_expr(tok_m.group(1))
            if tokens is None:
                continue
            pr = priority(provider, mid)
            cur = sources.get(mid)
            if cur is None or pr > cur[1] or (pr == cur[1] and provider == owner_of(mid)):
                context[mid] = tokens
                if out_m:
                    max_output[mid] = int(out_m.group(1).replace("_", ""))
                sources[mid] = (provider, pr)
    return context, max_output


# The resolver functions live below the data and are never regenerated.
_FUNCTIONS = '''

import re as _re

# Variant suffixes lobehub appends; stripping them often yields the base id
# users actually configure (e.g. "claude-opus-4-1-20250805" -> "claude-opus-4-1").
_VARIANT_SUFFIX = _re.compile(
    r"-\d{4,}$"                                  # -20250805 style date tails
    r"|(?:-(?:latest|preview|exp|turbo|vision|thinking|reasoning))$"
    r"|-\d{2,4}-\d{2}-\d{2}$"                    # dated releases
)


def get_model_context_limit(model_id: str) -> int | None:
    """Resolve a model id to its context-window token limit, or None if unknown.

    Exact match first, then strips variant suffixes (-latest/-preview/-20250805)
    so configuring a base/older id still resolves.
    """
    if not model_id:
        return None
    mid = model_id.strip()
    if MODEL_CONTEXT_LIMITS.get(mid) is not None:
        return MODEL_CONTEXT_LIMITS[mid]
    candidate = mid
    for _ in range(3):
        stripped = _VARIANT_SUFFIX.sub("", candidate)
        if stripped == candidate:
            break
        candidate = stripped
        if MODEL_CONTEXT_LIMITS.get(candidate) is not None:
            return MODEL_CONTEXT_LIMITS[candidate]
    return None


def get_model_max_output(model_id: str) -> int | None:
    """Resolve a model id to its max output tokens, or None if unknown."""
    if not model_id:
        return None
    mid = model_id.strip()
    if MODEL_MAX_OUTPUT.get(mid) is not None:
        return MODEL_MAX_OUTPUT[mid]
    candidate = mid
    for _ in range(3):
        stripped = _VARIANT_SUFFIX.sub("", candidate)
        if stripped == candidate:
            break
        candidate = stripped
        if MODEL_MAX_OUTPUT.get(candidate) is not None:
            return MODEL_MAX_OUTPUT[candidate]
    return None


def format_context_window_note(model_id: str) -> str:
    """One-line context-window (and max-output, if known) hint, or '' if unknown."""
    limit = get_model_context_limit(model_id)
    if not limit:
        return ""
    parts = [f"\U0001fa9f {limit:,} context tokens"]
    max_out = get_model_max_output(model_id)
    if max_out:
        parts.append(f"↗ {max_out:,} max output")
    return " · ".join(parts)
'''


def render_module(tag: str, context: dict[str, int], max_output: dict[str, int]) -> str:
    lines = [
        '"""Per-model context-window and max-output token limits.',
        "",
        f"Extracted from {REPO} {tag} (MIT) — {AI_MODELS_DIR}/*.ts. "
        f"{len(context)} model ids. On id conflicts the model's own vendor",
        "(by id-family) wins over proxy/aggregate providers. Regenerate via",
        "scripts/refresh_model_context.py. Resolve at runtime via",
        "get_model_context_limit() (exact, then variant-suffix fallback);",
        "max-output via get_model_max_output().",
        '"""',
        "",
        "from __future__ import annotations",
        "",
        "",
        "MODEL_CONTEXT_LIMITS: dict[str, int] = {",
    ]
    for k in sorted(context):
        lines.append(f'    "{k}": {context[k]},')
    lines += ["}", "", "MODEL_MAX_OUTPUT: dict[str, int] = {"]
    for k in sorted(max_output):
        lines.append(f'    "{k}": {max_output[k]},')
    lines.append("}")
    return "\n".join(lines) + _FUNCTIONS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="lobe-chat tag (default: latest stable)")
    parser.add_argument("--dry-run", action="store_true", help="print summary, don't write")
    args = parser.parse_args()

    tag = args.tag or latest_stable_tag()
    print(f"Fetching {AI_MODELS_DIR}/ at tag {tag} ...")
    listing = _http_json(f"https://api.github.com/repos/{REPO}/contents/{AI_MODELS_DIR}?ref={tag}")
    names = [it["name"] for it in listing if it["name"].endswith(".ts") and it["name"] != "index.ts"]

    files: dict[str, str] = {}
    for name in names:
        files[name[:-3]] = _http_text(
            f"https://raw.githubusercontent.com/{REPO}/{tag}/{AI_MODELS_DIR}/{name}"
        )
    print(f"  downloaded {len(files)} provider files")

    context, max_output = extract(files)
    print(f"  context: {len(context)} models | maxOutput: {len(max_output)} models")

    sample = ["gpt-5.2", "claude-opus-4-8", "gemini-2.5-pro", "deepseek-v4-pro", "glm-4.6", "qwen3-max"]
    print("  sample:")
    for m in sample:
        if m in context:
            print(f"    {m:24} {context[m]:>10,}" + (f" (out {max_output[m]:,})" if m in max_output else ""))

    if args.dry_run:
        return 0

    module_text = render_module(tag, context, max_output)
    OUTPUT.write_text(module_text)
    print(f"Wrote {OUTPUT.relative_to(Path.cwd()) if OUTPUT.is_relative_to(Path.cwd()) else OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
