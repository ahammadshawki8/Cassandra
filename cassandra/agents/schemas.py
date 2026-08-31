"""Structured outputs for the agent fleet.

Every agent returns a typed object rather than prose. This is not decoration.
An agent that answers in free text forces the orchestrator to parse intent out
of English, which fails silently and unpredictably. A schema turns a wrong
answer into a validation error the loop can actually handle.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Adjudication(BaseModel):
    """The Adjudicator's ruling on one candidate defect."""

    is_defect: bool = Field(
        description=(
            "True only if this is genuinely wrong. A cell that differs from its "
            "neighbours for a legitimate modelling reason is not a defect."
        )
    )
    severity: str = Field(
        description="One of: critical, material, minor, cosmetic."
    )
    confidence: float = Field(
        description="Confidence between 0 and 1 that this is a real defect.",
        ge=0.0,
        le=1.0,
    )
    explanation: str = Field(
        description=(
            "Two sentences at most, in the language a finance lead would use. "
            "Say what is wrong and what it does to the numbers, not what the "
            "formula syntax looks like."
        )
    )
    dismissal_reason: str = Field(
        default="",
        description="If is_defect is false, why this is legitimate. Otherwise empty.",
    )


class ProposedPatch(BaseModel):
    """The Patcher's proposed repair for one confirmed defect."""

    formula: str = Field(
        description=(
            "The complete replacement formula including the leading equals sign. "
            "Change only what is wrong; preserve the surrounding structure."
        )
    )
    is_latent: bool = Field(
        description=(
            "True if this repair leaves the value unchanged as the workbook "
            "stands today, and only differs once a driver changes. A hardcoded "
            "constant equal to the assumption it replaced is the usual case."
        )
    )
    driver_cell: str = Field(
        default="",
        description=(
            "For a latent repair, the cell in Sheet!A1 form that this formula "
            "should now track. Empty otherwise."
        )
    )
    predicted_value: float | None = Field(
        default=None,
        description=(
            "The value the target cell will hold after this patch. Null if it "
            "cannot be determined confidently. A wrong number here will be "
            "caught by recalculation and the patch will be rejected, so guessing "
            "is worse than answering null."
        )
    )
    rationale: str = Field(
        description="One sentence on why this formula is the correct repair."
    )


class SemanticVerdict(BaseModel):
    """The Semantic Auditor's reading of one labelled cell."""

    cell: str = Field(description="The cell examined, in Sheet!A1 form.")
    agrees_with_label: bool = Field(
        description="True if the formula computes what its label claims."
    )
    confidence: float = Field(ge=0.0, le=1.0)
    what_it_actually_computes: str = Field(
        description="A short phrase naming what the formula really produces."
    )
    explanation: str = Field(
        description="One sentence. Empty if the formula and label agree."
    )


class SemanticReport(BaseModel):
    """A batch of semantic verdicts, so one model call covers many cells."""

    verdicts: list[SemanticVerdict] = Field(default_factory=list)
