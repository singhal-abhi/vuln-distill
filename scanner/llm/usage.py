"""Tokens and dollars spent, per model call and summed per run."""

from dataclasses import dataclass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost: float | None = 0.0   # US dollars; None once any call in the sum had no known price

    def add(self, other: "Usage") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cost = None if self.cost is None or other.cost is None else self.cost + other.cost

    def __str__(self) -> str:
        cost = "cost unknown" if self.cost is None else f"${self.cost:.4f}"
        return f"{self.input_tokens:,} in / {self.output_tokens:,} out tokens, {cost}"


def call_usage(price: dict | None, input_tokens: int, output_tokens: int, reported_cost: float | None = None) -> Usage:
    """One call's usage. Cost is what the provider reported (OpenRouter does), else from the model's price in
    config (USD per million input / output tokens), else unknown."""
    cost = reported_cost
    if cost is None and price:
        cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    return Usage(input_tokens, output_tokens, cost)


def total(usages: list[Usage]) -> Usage:
    summed = Usage()
    for usage in usages:
        summed.add(usage)
    return summed
