"""Model pricing — derive INR cost from token usage.

Rates are approximate published Gemini prices (USD per 1M tokens), converted to
INR. Image models are billed per generated image, so they carry a flat per-call
charge. Tune these to your real contract; they're the single source of cost.
"""

USD_TO_INR = 83.0

# model -> (input USD / 1M tokens, output USD / 1M tokens, flat USD / call)
_RATES: dict[str, tuple[float, float, float]] = {
    "gemini-2.5-flash": (0.30, 2.50, 0.0),
    # Image model: $0.30/1M input (text prompt) + $30/1M output (image) tokens.
    # An image is ~1290 output tokens, i.e. ~$0.039 each — but billed per token.
    "gemini-2.5-flash-image": (0.30, 30.0, 0.0),
}
_DEFAULT = (0.30, 2.50, 0.0)


def cost_inr(model: str, input_tokens: int, output_tokens: int) -> float:
    """INR cost for one call, from its token usage (plus any per-call flat fee)."""
    pin, pout, flat = _RATES.get(model, _DEFAULT)
    usd = (input_tokens / 1_000_000) * pin + (output_tokens / 1_000_000) * pout + flat
    return round(usd * USD_TO_INR, 4)


def split_cost_inr(model: str, input_tokens: int, output_tokens: int) -> tuple[float, float]:
    """INR cost split into (input, output) — for the granular costing breakdown."""
    pin, pout, _ = _RATES.get(model, _DEFAULT)
    in_inr = round((input_tokens / 1_000_000) * pin * USD_TO_INR, 4)
    out_inr = round((output_tokens / 1_000_000) * pout * USD_TO_INR, 4)
    return in_inr, out_inr
