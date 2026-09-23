"""LLM mapping layer.

Rules that must never be broken:
  1. The model PROPOSES only. It never transforms or writes customer data.
  2. It sees column names, statistics and MASKED samples - never full records.
  3. Its output must be valid JSON matching our schema, or we ignore it.
"""
import json
import os

from anthropic import Anthropic
from dotenv import load_dotenv

from pipeline.canonical import CUSTOMER_FIELDS

load_dotenv()

MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You map messy source columns onto a canonical schema for a data onboarding pipeline.

You will receive:
- The canonical schema (field name, type, description)
- A profile of each source column (name, null %, distinct count, masked sample values)

For each canonical field, decide which source column is the best match, or null if none fits.

Rules:
- Judge on BOTH the column name and what the sample values look like.
- Be honest about uncertainty. A wrong confident mapping is far worse than an honest low score.
- confidence is 0.0-1.0. Use below 0.6 when you are guessing.
- Never invent a source column. Use only names from the profile.
- If a required field has no match, say so in the reason.

Reply with JSON only, no markdown fences, in exactly this shape:
{"fields": [{"canonical_field": "...", "source_column": "... or null",
             "confidence": 0.0, "reason": "one short sentence"}]}"""


def mask(value: str) -> str:
    """Reduce a sample to its shape so no real customer data leaves our system."""
    if "@" in value:
        local, _, domain = value.partition("@")
        return f"{local[0]}***@{domain}"
    if len(value) <= 4:
        return value
    return f"{value[:2]}***{value[-2:]}"


def build_user_prompt(profiles: list[dict]) -> str:
    schema = [
        {"field": name, "type": spec["type"], "required": spec["required"],
         "description": spec["description"]}
        for name, spec in CUSTOMER_FIELDS.items()
    ]
    columns = [
        {"column": p["column"], "null_pct": p["null_pct"],
         "distinct_values": p["distinct_values"],
         "masked_samples": [mask(s) for s in p["samples"]]}
        for p in profiles
    ]
    return (
        f"CANONICAL SCHEMA:\n{json.dumps(schema, indent=2)}\n\n"
        f"SOURCE COLUMN PROFILE:\n{json.dumps(columns, indent=2)}"
    )


def propose_with_llm(profiles: list[dict]) -> dict[str, dict]:
    """Return {canonical_field: {source_column, confidence, reason}}.

    Returns {} on any failure, so the pipeline still works without the LLM.
    """
    try:
        client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(profiles)}],
        )
        text = response.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        parsed = json.loads(text)

        valid_columns = {p["column"] for p in profiles}
        result = {}
        for item in parsed.get("fields", []):
            field = item.get("canonical_field")
            column = item.get("source_column")
            # Reject anything that is not in our schema or invents a column
            if field not in CUSTOMER_FIELDS:
                continue
            if column is not None and column not in valid_columns:
                continue
            result[field] = {
                "source_column": column,
                "confidence": float(item.get("confidence", 0)),
                "reason": item.get("reason", ""),
            }
        return result
    except Exception as exc:  # network error, bad JSON, no key
        print(f"[llm_mapper] falling back to heuristics only: {exc}")
        return {}