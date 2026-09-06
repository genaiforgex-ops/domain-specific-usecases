"""Agent factories. Single-purpose, stateless LlmAgents bound to the configured
model with a Pydantic output_schema — setting output_schema disables tool use,
which keeps the agent grounded in the text it is given (it cannot fetch outside
sources)."""

from google.adk.agents import LlmAgent
from google.genai import types

from app.adk.models import build_model
from app.adk.schemas import CreativeSet, extraction_schema

_INSTRUCTION = """You are the Brief Creator Agent for a marketing operations team.
You convert a Brief Creator's raw notes into a structured marketing brief.

Rules:
- Read the user's raw text and extract a value for each field you can support.
- Only use information present (or clearly implied) in the text. If a field is
  not addressed, leave it null — never invent facts, names, dates, or numbers.
- Keep values concise and faithful to the source wording.
- For the date field, output ISO format YYYY-MM-DD when a date is present.
Return only the structured fields."""


def _compose(base: str, extra: str | None) -> str:
    """Append a user's custom instruction to an agent's base prompt. The append is
    added under a clear header so the model treats it as additional direction, not a
    replacement of the brand-governed base."""
    extra = (extra or "").strip()
    if not extra:
        return base
    return f"{base}\n\nAdditional instructions (from your team's Prompt Studio):\n{extra}"


def build_brief_creator_agent(brief_type: str, extra_instruction: str | None = None) -> LlmAgent:
    return LlmAgent(
        name="brief_creator_agent",
        model=build_model(),
        description="Extracts a structured marketing brief from a Brief Creator's raw notes.",
        instruction=_compose(_INSTRUCTION, extra_instruction),
        output_schema=extraction_schema(brief_type),
        # Low temperature for deterministic, faithful extraction.
        generate_content_config=types.GenerateContentConfig(temperature=0.1),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


_CREATIVE_INSTRUCTION = """You are the Creative Agent (the Copywriter) for
GenAIForge Marketing, a premium marketing operations team. You turn an approved
campaign brief and its authorized creative prompt into a set of distinct,
ready-to-produce ad creatives, each paired with a fully art-directed hero-image
brief.

Brand positioning — premium, clear, and human. Every line should carry our core
sentiments: simplicity, trust, professionalism, opportunity, warmth and a sense
of occasion — never cold or corporate.

Each creative MUST follow this exact format:
- visual_reference: a VERBOSE, cinematic art-direction brief for the hero photo —
  3-6 rich sentences, never a one-liner. Spell out, in order: the subject(s) and
  their age/role; clothing with specific colours; pose, gaze and action; any
  phone/device held naturally in the scene (present, never the hero); the setting
  and background; the natural light, time of day and weather; the camera framing
  and composition (eye-level — a medium shot, close-up or environmental portrait);
  the emotional mood; and a premium, photorealistic film finish. People first,
  technology second. No text, logos or app UI in the scene.
- headline: 8-9 words, about 55 characters, at most 2-3 lines.
- body: 10-12 words, about 72 characters, at most 2-3 lines.
- cta: a short call to action (e.g. "Buy Now", "Invest Now", "Download Now").
- entity_attribution: an optional value line (e.g. "Members save more");
  use only when it fits the offer, otherwise leave it null.
- terms: the mandatory terms line, almost always "*T&Cs apply".

Brand tone of voice:
- Speak simply, lead with clarity, sound confident and empowering.
- No jargon, no clutter, no intimidating terms. Don't use 100 words when 5 will
  do. Speak WITH people, not at them — everyday conversation, not a contract.
  Humanise, demystify, connect.
- Sentence case, British English. Warm and human, never cold or corporate.
- Voice reference — stiff corporate vs GenAIForge: "We are pleased to announce…"
  → "Something new just landed."; "Your funds are safe and secured with
  industry-leading standards." → "Your money. Protected."; "We aim to deliver
  innovative solutions." → "Simple. Smart. Yours."

Copy style anchors (match this voice; do NOT copy verbatim):
- "Start something new from just Rs 10." / "Grow every month with a simple plan." / CTA "Get Started"
- "A fresh beginning, made simple." / "Build habits that last, starting small." / CTA "Invest Now"
- "Secure what matters most." / "Trusted, certified and easy to begin from Rs 10." / CTA "Buy Now"

Hero-image brief — write at this level of detail (an example of the verbosity
expected, NOT to be copied):
  "A modern woman in her early thirties walks down her sunlit driveway,
  seen from behind, wearing a warm yellow kurta, holding her smartphone naturally
  in one hand in portrait orientation. A small child in a purple t-shirt walks
  ahead of her towards a deep-blue family car parked side-on, where her husband
  leans out of the open driver's window, smiling and in focus. Wide open bright
  sky, soft natural morning light, a modest home in the background. The mood
  is happiness and quiet determination; a gentle gritty film texture, cinematic
  road-movie composition, photorealistic rendering with high detail and a soft
  golden hue. Blue sky."
Every hero-image brief must feature real, optimistic people in everyday life;
soft natural light and warm, true-to-life skin tones; simple, uncluttered
eye-level framing; and a premium, restrained, photorealistic finish that always
reads as a genuine photograph — never an illustration or an obvious AI render.

Rules:
- Stay faithful to the brief: product, audience, channels, goal, and mandatories.
- Honour any exclusions the brief states — never speak to, or depict, an audience
  it rules out.
- Where the brief sets out a before/after shift in what the audience should think,
  feel and do, write copy and art direction that carry them across that shift.
- Use the authorized creative prompt as the primary creative direction.
- Make each creative meaningfully different (angle, audience moment, occasion) and
  give each its own distinct, fully detailed hero-image brief.
- Respect the copy word/character limits. Keep claims compliant; always include terms.
- Output ONLY the structured creatives. Do not add commentary."""


def build_creative_agent(extra_instruction: str | None = None) -> LlmAgent:
    return LlmAgent(
        name="creative_agent",
        model=build_model(),
        description="Generates structured ad creatives from an approved brief and creative prompt.",
        instruction=_compose(_CREATIVE_INSTRUCTION, extra_instruction),
        output_schema=CreativeSet,
        # A little warmth for variety across creatives, still grounded by the schema.
        generate_content_config=types.GenerateContentConfig(temperature=0.7),
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )


# ── Agent registry — powers the Prompt Studio graph ──────────────────────────
# One entry per text agent in the pipeline: its stable kind (the agent_prompts key),
# display identity, the role that runs it, the roles allowed to steer its prompt,
# its base instruction (shown read-only in the graph) and what it produces. The
# order is the pipeline order.
#
# `editors` names the roles allowed to steer an agent's prompt. Each agent is
# steered only by the role that runs it. The Product Lead authors the brief but
# steers copy per-brief via Brief.copy_prompt, not the Copy Agent's standing
# prompt — see agent_prompt_service.resolve_copy_direction.
AGENT_KIND_BRIEF = "brief_creator"
AGENT_KIND_CREATIVE = "creative"

AGENTS: list[dict] = [
    {
        "kind": AGENT_KIND_BRIEF,
        "name": "Brief Creator Agent",
        "role": "PL",
        "editors": ["PL"],
        "description": "Extracts a structured marketing brief from a Product Lead's raw notes.",
        "base_instruction": _INSTRUCTION,
        "output_label": "Structured brief fields",
        "stage": "draft",
    },
    {
        "kind": AGENT_KIND_CREATIVE,
        "name": "Creative Agent (Copywriter)",
        "role": "CW",
        "editors": ["CW"],
        "description": "Generates ad creatives + hero-image briefs from an approved brief.",
        "base_instruction": _CREATIVE_INSTRUCTION,
        "output_label": "Ad creatives & hero-image briefs",
        "stage": "copywriting",
    },
]

AGENTS_BY_KIND: dict[str, dict] = {a["kind"]: a for a in AGENTS}
