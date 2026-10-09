"""Direct outreach draft generation — replaces the Make webhook scenario.

Generates a personalized outreach draft via OpenAI, storing the full
"recipe" (prompt + inputs used) alongside the draft for transparency.
Ryan can see exactly what the AI was told for every draft.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

SYSTEM_PROMPT = """You are Ryan's outreach writer for The Shirtless Handyman, a microcement and Venetian plaster specialist in the New Orleans area.

Ryan's trade: microcement, Venetian plaster, tadelakt — seamless, mold-free surfaces for life. Specialist in waterproofing: showers, bathrooms, wet areas. Also does microcement/cement-look countertops and cement furniture.

Voice: casual, direct, one-to-one. Short texts, not emails. Never sound like a blast or template. Use the lead's name when you have it.

Rules:
- Name the job or project context specifically.
- Ask exactly ONE focused question.
- Keep it text-message length (under 50 words).
- Never invent project scope, replies, or history. Use only the details provided.
- No links, no attachments, no pressure tactics.
"""


def build_prompt(opp: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Build the user prompt from opportunity data. Returns (prompt, inputs_used)."""
    inputs = {
        "name": opp.get("name"),
        "company": opp.get("company"),
        "decision_maker": opp.get("decision_maker"),
        "project_address": opp.get("project_address"),
        "project_type": opp.get("project_type"),
        "evidence_summary": opp.get("evidence_summary"),
        "outreach_angle": opp.get("outreach_angle"),
        "permit_description": opp.get("permit_description"),
    }
    # Drop empty values so the recipe shows only what was actually used.
    inputs = {k: v for k, v in inputs.items() if v}

    lines = ["Write a first-touch outreach text for this lead.", ""]
    for key, value in inputs.items():
        lines.append(f"{key.replace('_', ' ').title()}: {value}")
    lines += [
        "",
        "Name the job plus ask one focused question, following the pattern that wins replies.",
    ]
    return "\n".join(lines), inputs


async def generate_draft(opp: Dict[str, Any]) -> Dict[str, Any]:
    """Generate a draft via OpenAI. Returns {draft, subject, recipe}."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    user_prompt, inputs = build_prompt(opp)

    resp = await client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=200,
        temperature=0.7,
    )
    draft = resp.choices[0].message.content.strip()

    recipe = {
        "model": MODEL,
        "system_prompt": SYSTEM_PROMPT,
        "user_prompt": user_prompt,
        "inputs_used": inputs,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Simple subject from the job context.
    subject_bits = [
        inputs.get("project_address"),
        inputs.get("company"),
        inputs.get("name"),
    ]
    subject = next((b for b in subject_bits if b), "outreach draft")

    return {
        "draft": draft,
        "subject": subject,
        "recipe": recipe,
    }


def recipe_to_field(recipe: Dict[str, Any]) -> str:
    """Serialize the recipe for the Airtable 'Draft Recipe' long-text field."""
    return json.dumps(recipe, indent=2, ensure_ascii=False)
