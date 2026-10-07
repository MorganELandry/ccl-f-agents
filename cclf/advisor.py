"""
The advisor: probabilistic automation in the role CCL-F v0.2 gives it.

AI Applications names "AI as Coordination Signal Classifier" as the
immediate application: identify which of the six signal types a report is.
This advisor does that, and proposes an operational state. It never
registers, closes, classifies or authorizes anything itself: the supervisor
applies the same rules to its proposals as to anyone's, and nothing it
writes counts as evidence (EES excludes model output).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from .types import OperationalState, SignalType


SYSTEM_PROMPT = (
    "You classify reports for a safety coordination monitor (CCL-F).\n"
    "Signal types: constraint, uncertainty, anomaly, dissent, classification, framing.\n"
    "Operational states: nominal, elevated_uncertainty, off_envelope, experimental, "
    "containment.\n"
    "Only call a condition nominal if the report cites validated test data covering it.\n"
    'Respond ONLY with JSON: {"signal_type": str, "operational_state": str, '
    '"rationale": str}'
)

# Used when the model is unavailable or its reply is unusable: the most
# conservative reading, never nominal.
FALLBACK_TYPE = SignalType.UNCERTAINTY
FALLBACK_STATE = OperationalState.ELEVATED_UNCERTAINTY

Ask = Callable[[str, str], str]   # (system, user) -> reply text


@dataclass(frozen=True)
class Proposal:
    signal_type: SignalType
    operational_state: OperationalState
    rationale: str
    from_model: bool


def _langchain_ask(backend: Optional[str]) -> Ask:
    from langchain_core.messages import HumanMessage, SystemMessage
    from .backends import get_llm
    llm = get_llm(backend)

    def ask(system: str, user: str) -> str:
        return llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
    return ask


class Advisor:
    """Wraps a model call; any failure degrades to the conservative fallback."""

    def __init__(self, ask: Optional[Ask] = None, backend: Optional[str] = None):
        self._ask = ask
        self._backend = backend

    def _model(self) -> Optional[Ask]:
        if self._ask is None:
            try:
                self._ask = _langchain_ask(self._backend)
            except Exception:
                return None
        return self._ask

    def propose(self, report: str) -> Proposal:
        model = self._model()
        if model is None:
            return Proposal(FALLBACK_TYPE, FALLBACK_STATE, "model unavailable", False)
        try:
            text = model(SYSTEM_PROMPT, report)
            start, end = text.find("{"), text.rfind("}")
            data = json.loads(text[start:end + 1])
            return Proposal(SignalType(data["signal_type"]),
                            OperationalState(data["operational_state"]),
                            str(data.get("rationale", "")), True)
        except Exception as exc:
            return Proposal(FALLBACK_TYPE, FALLBACK_STATE,
                            f"unusable model reply ({type(exc).__name__})", False)
