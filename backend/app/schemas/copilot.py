from pydantic import BaseModel, Field


class CopilotTurn(BaseModel):
    """One prior turn of the conversation, sent back by the client so a
    follow-up like "yes" or "what about that" can be resolved against what
    the assistant just said -- see services/copilot.py:resolve_followup and
    _llm_answer's use of history. Never trusted as anything but text to
    ground the next answer in; it carries no authority of its own."""
    role: str = Field(..., pattern="^(user|assistant)$")
    text: str = Field(..., min_length=1, max_length=500)


class CopilotQuestion(BaseModel):
    question: str = Field(..., min_length=1, max_length=500)
    # Bounded to the last few turns -- enough for "yes"/"what about that" to
    # resolve, not an unbounded transcript.
    history: list[CopilotTurn] = Field(default_factory=list, max_length=10)


class CopilotAnswer(BaseModel):
    answer: str
    handled: bool
    # "llm" when the open-ended language model answered; absent when a
    # deterministic intent handler did (see services/copilot.py).
    source: str | None = None
