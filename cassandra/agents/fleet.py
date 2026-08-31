"""The agent fleet, built on Google ADK with Gemini 3.5 Flash.

A deliberate constraint runs through this module: none of these agents holds a
tool. Not one can read a file, mutate a workbook, call an API, or reach the
network. Each receives evidence that deterministic code has already assembled,
and returns a typed judgement. Every capability in the system lives in plain
Python that the orchestrator controls.

This is the strongest form of least privilege available. Tool scoping usually
means giving each agent a narrow set of functions and trusting the model not to
misuse them. Here there is nothing to misuse. A prompt injected into a cell
label can at worst produce a wrong judgement, which the Verifier then rejects by
recalculation, because the Verifier does not ask the model anything at all.
"""

from __future__ import annotations

import asyncio
import os

from google.adk.agents import LlmAgent
from google.adk.runners import InMemoryRunner
from google.genai import types

from .schemas import Adjudication, ProposedPatch, SemanticReport

MODEL = os.environ.get("CASSANDRA_MODEL", "gemini-3.5-flash")

_SHARED_CONTEXT = """
You are part of Cassandra, a system that audits the spreadsheets companies run
their finances on. You are looking at a real financial model whose numbers are
shown to executives and investors.

Two standing rules:

Be conservative. A false alarm costs an analyst an hour and teaches them to
ignore you, which is worse than missing a defect. Cells legitimately differ from
their neighbours all the time: the first cell of a series seeds it from an
assumption, subtotal rows aggregate differently from the rows above them, and
sign conventions vary between models.

Reason about intent, not syntax. The question is never whether a formula is
unusual. It is whether the number this cell produces is the number a reader of
this model would expect it to produce.
""".strip()


ADJUDICATOR_INSTRUCTION = f"""{_SHARED_CONTEXT}

You are the Adjudicator. A deterministic detector has located a suspicious cell
and assembled evidence about it. Rule on whether it is genuinely a defect.

The detector found a structural anomaly. It cannot tell whether that anomaly is
a mistake or a modelling decision. That is your entire job.

Weigh the detector's own confidence, but do not defer to it. Note in particular
that a cell at the start or end of a region is often legitimately different.

Severity means consequence, not certainty:
  critical  the headline figures a reader quotes are wrong
  material  a number people act on is wrong
  minor     wrong but consequential to little
  cosmetic  not wrong, merely untidy

Write the explanation for a finance lead, not an engineer. Say what the number
does, not what the formula says.
"""


PATCHER_INSTRUCTION = f"""{_SHARED_CONTEXT}

You are the Patcher. A defect has been confirmed. Write the formula that repairs
it.

Constraints:

Change only what is wrong. If a range stops one row short, extend it by one row;
do not restructure the formula. The smallest correct edit is always the right
one, because it is the one a reviewer can check at a glance.

Match the conventions of the surrounding cells. The peer formulas shown to you
are the model's house style. Use absolute and relative references the way they
do.

Predict the resulting value only if you are confident. Your prediction is
checked by recalculating the entire workbook, and a wrong prediction rejects
your patch. Null is a legitimate answer and costs you nothing.

Some defects are latent: the cell computes the correct value today and is wrong
only in the future. A hardcoded constant that happens to equal the assumption it
replaced is the standard case. Set is_latent when your repair does not move the
value today, and name the driver cell it should track, because that repair is
proven by a different method.
"""


SEMANTIC_INSTRUCTION = f"""{_SHARED_CONTEXT}

You are the Semantic Auditor. You are the only part of Cassandra that can catch
a formula which is perfectly well formed and computes the wrong quantity.

You are given labelled cells with their formulas. For each, decide whether the
formula computes what the label claims.

The defects you exist to find look like this: a cell labelled Net Margin that
divides gross profit by revenue, a row labelled Q4 that reads the Q3 column, a
figure labelled Annual that has not been multiplied by four, a cell labelled
Total that omits a component.

Do not flag a cell merely because its label is terse or its formula indirect.
Flag it when a reader trusting the label would be misled about the number.

Return a verdict for every cell you are given.
"""


def build_adjudicator() -> LlmAgent:
    return LlmAgent(
        name="adjudicator",
        model=MODEL,
        description="Rules on whether a detected anomaly is genuinely a defect.",
        instruction=ADJUDICATOR_INSTRUCTION,
        output_schema=Adjudication,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )


def build_patcher() -> LlmAgent:
    return LlmAgent(
        name="patcher",
        model=MODEL,
        description="Writes the repair formula for a confirmed defect.",
        instruction=PATCHER_INSTRUCTION,
        output_schema=ProposedPatch,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )


def build_semantic_auditor() -> LlmAgent:
    return LlmAgent(
        name="semantic_auditor",
        model=MODEL,
        description="Checks that a formula computes what its label claims.",
        instruction=SEMANTIC_INSTRUCTION,
        output_schema=SemanticReport,
        generate_content_config=types.GenerateContentConfig(temperature=0.0),
    )


async def _ask(agent: LlmAgent, prompt: str, user_id: str = "cassandra") -> str:
    """Run one agent over one prompt and return its raw structured response."""
    runner = InMemoryRunner(agent=agent, app_name="cassandra")
    session = await runner.session_service.create_session(
        app_name="cassandra", user_id=user_id
    )
    message = types.Content(role="user", parts=[types.Part(text=prompt)])

    final = ""
    async for event in runner.run_async(
        user_id=user_id, session_id=session.id, new_message=message
    ):
        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final = part.text
    return final


def ask(agent: LlmAgent, prompt: str) -> str:
    """Synchronous wrapper, so the orchestrator stays readable."""
    return asyncio.run(_ask(agent, prompt))
