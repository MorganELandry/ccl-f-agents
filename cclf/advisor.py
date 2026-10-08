"""
THE ADVISOR
A Play in Three Scenes
======================

PROLOGUE
--------
The advisor: probabilistic automation in the role CCL-F v0.2 gives it.

AI Applications names "AI as Coordination Signal Classifier" as the
immediate application: identify which of the six signal types a report is.
This advisor does that, and proposes an operational state. It never
registers, closes, classifies or authorizes anything itself: the supervisor
applies the same rules to its proposals as to anyone's, and nothing it
writes counts as evidence (EES excludes model output).

Where this fits: graph.py's "interpret" node hands each raw report to
Advisor.propose() and passes the resulting Proposal on. When that proposal
is applied, Supervisor.classify() is told it came from a model
(proposed_by_model), and Rule 2 still applies: a NOMINAL proposal without
EES-qualifying evidence is recorded as elevated uncertainty instead.

THE PLAYBILL (what happens in this file)
    Scene 1  Proposal          the advisor's answer (frozen record)
    Scene 2  _langchain_ask()  build a real model call from a backend
    Scene 3  Advisor           wrap the model call; fall back safely
               _model()          get (and cache) the model call
               propose()         classify one report

READER'S NOTE — Callable type aliases
    `Ask = Callable[[str, str], str]` gives a name to a *shape of function*:
    one that takes two str arguments (system prompt, user text) and returns
    a str (the reply). Any function with that shape will do, which is why
    tests can pass a tiny fake `ask` instead of a real model. Ask is only a
    type hint; Python does not check it at runtime.

READER'S NOTE — lazy imports
    _langchain_ask() imports LangChain and the backends package inside the
    function rather than at the top of the file. So `import cclf` works even
    when LangChain is not installed; the import only happens (and can only
    fail) the first time a real model is needed. See also backends/__init__.

READER'S NOTE — the conservative fallback
    If no model is available, or its reply cannot be understood, propose()
    does not crash and does not guess optimistically. It returns
    FALLBACK_TYPE (uncertainty) and FALLBACK_STATE (elevated uncertainty),
    with from_model=False. Rule 2 says unvalidated conditions cannot be
    classified as nominal, so the safe default when the advisor knows
    nothing is "there is an open uncertainty", never "all is well".

READER'S NOTE — closures (the inner function `ask`)
    In _langchain_ask(), the inner function `ask` uses `llm`, a variable of
    the outer function. Python keeps `llm` alive for as long as `ask`
    exists, so the returned `ask` still has its model after
    _langchain_ask() has returned. This is called a closure.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# json                         parses the model's JSON reply.
# dataclass                    builds the frozen Proposal record.
# Callable, Optional           type hints (see READER'S NOTE on Callable).
# OperationalState, SignalType the vocabularies a proposal must use.
# (LangChain and .backends are imported lazily inside _langchain_ask.)
# ===========================================================================

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from .types import OperationalState, SignalType


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# SYSTEM_PROMPT — the instructions sent to the model with every report. It
#   lists the six signal types and five operational states by their enum
#   values, repeats Rule 2's demand in plain words (nominal only with
#   validated test data), and asks for a JSON-only reply with three keys.
#   Adjacent string literals inside parentheses are joined into one str.
SYSTEM_PROMPT = (
    "You classify reports for a safety coordination monitor (CCL-F).\n"
    "Signal types: constraint, uncertainty, anomaly, dissent, classification, framing.\n"
    "Operational states: nominal, elevated_uncertainty, off_envelope, experimental, "
    "containment.\n"
    "Only call a condition nominal if the report cites validated test data covering it.\n"
    'Respond ONLY with JSON: {"signal_type": str, "operational_state": str, '
    '"rationale": str}'
)

# FALLBACK_TYPE, FALLBACK_STATE — the conservative answer (see READER'S NOTE).
# Used when the model is unavailable or its reply is unusable: the most
# conservative reading, never nominal.
FALLBACK_TYPE = SignalType.UNCERTAINTY
FALLBACK_STATE = OperationalState.ELEVATED_UNCERTAINTY

# Ask — a type alias, not data: the shape of a model-call function
#   (READER'S NOTE on Callable). Advisor accepts any function of this shape.
Ask = Callable[[str, str], str]   # (system, user) -> reply text


# ===========================================================================
# SCENE 1 — THE RECOMMENDATION
# Proposal: what the advisor suggests for one report
# ===========================================================================

@dataclass(frozen=True)
class Proposal:
    """
    The advisor's suggestion for one report. Only a suggestion: the
    supervisor decides what is actually recorded.

    Fields:
      signal_type        proposed SignalType
      operational_state  proposed OperationalState
      rationale          the model's reason, or why the fallback was used
      from_model         True if a model produced it; False for the fallback

    Frozen so a proposal cannot be quietly altered after it is made.
    """
    signal_type: SignalType
    operational_state: OperationalState
    rationale: str
    from_model: bool


# ===========================================================================
# SCENE 2 — HIRING THE MODEL
# _langchain_ask(): turn a configured LangChain model into an Ask function
# ===========================================================================

def _langchain_ask(backend: Optional[str]) -> Ask:
    """
    Build an Ask function backed by a real LangChain chat model.

    Enter:   backend   a backend name ("openai", "anthropic", ...) or None
                       for the configured default (see backends/__init__.py)
    Exit:    an Ask: ask(system, user) -> the model's reply text
             raises ImportError / ValueError / other errors if the model
             cannot be built; Advisor._model() catches these

    The imports are lazy (READER'S NOTE above). `ask` is a closure over
    `llm` (READER'S NOTE above).
    """
    # PLAYERS IN THIS SCENE
    #   HumanMessage, SystemMessage   LangChain message classes (lazy import)
    #   get_llm                       backend registry function (lazy import)
    #   llm                           the chat model
    #   ask                           the inner function returned

    # --- Lazy imports: only needed when a real model is used ----------------
    from langchain_core.messages import HumanMessage, SystemMessage
    from .backends import get_llm
    llm = get_llm(backend)

    # --- The function we hand back ------------------------------------------
    def ask(system: str, user: str) -> str:
        """
        Send one system prompt and one report to the model.

        Enter:   system   the instructions (SYSTEM_PROMPT when called by propose)
                 user     the report text
        Exit:    the reply's text (the message's .content)
        """
        # Send the system prompt and the report; return the reply's text.
        return llm.invoke([SystemMessage(content=system), HumanMessage(content=user)]).content
    return ask


# ===========================================================================
# SCENE 3 — THE ADVISOR
# Advisor: ask the model, and fall back conservatively on any failure
# ===========================================================================

class Advisor:
    """
    Wraps a model call; any failure degrades to the conservative fallback.

    Pass `ask` to use a specific function (tests pass a fake one). Leave it
    out and a LangChain model for `backend` is built on first use.
    """

    # -----------------------------------------------------------------------
    # SCENE 3a — TAKING ON THE ROLE
    # -----------------------------------------------------------------------
    def __init__(self, ask: Optional[Ask] = None, backend: Optional[str] = None):
        """
        Remember how to reach a model; build nothing yet.

        Enter:   ask       an Ask function to use, or None to build one later
                 backend   backend name passed to _langchain_ask if needed
        Exit:    stores both; nothing is built or called yet
        """
        self._ask = ask
        self._backend = backend

    # -----------------------------------------------------------------------
    # SCENE 3b — FINDING THE MODEL
    # -----------------------------------------------------------------------
    def _model(self) -> Optional[Ask]:
        """
        Return the Ask function, building it on first use.

        Enter:   (none)
        Exit:    the Ask function, or None if it could not be built

        A successfully built model is cached in self._ask. A failure is not
        cached, so the next call tries again. `except Exception` catches any
        error (missing package, missing key, unknown backend) because the
        advisor must never stop the system; it just falls back.
        """
        if self._ask is None:
            try:
                self._ask = _langchain_ask(self._backend)
            except Exception:
                return None
        return self._ask

    # -----------------------------------------------------------------------
    # SCENE 3c — THE RECOMMENDATION
    # -----------------------------------------------------------------------
    def propose(self, report: str) -> Proposal:
        """
        Propose a signal type and operational state for one report.

        Enter:   report   the raw report text
        Exit:    a Proposal; from_model=True if the model's reply was usable,
                 otherwise the conservative fallback with from_model=False
                 and a rationale saying why. Never raises for model problems.
        """
        # PLAYERS IN THIS SCENE
        #   model        the Ask function, or None
        #   text         the model's raw reply
        #   start, end   positions of the first "{" and last "}" in text
        #   data         the parsed JSON dict
        #   exc          the error, if anything went wrong

        # --- No model at all: fall back -------------------------------------
        model = self._model()
        if model is None:
            return Proposal(FALLBACK_TYPE, FALLBACK_STATE, "model unavailable", False)
        try:
            # --- Ask the model ----------------------------------------------
            text = model(SYSTEM_PROMPT, report)
            # --- Cut out the JSON object ------------------------------------
            # Models sometimes wrap JSON in extra words or code fences, so
            # take everything from the first "{" to the last "}".
            start, end = text.find("{"), text.rfind("}")
            data = json.loads(text[start:end + 1])
            # --- Convert strings to enum members ----------------------------
            # SignalType("anomaly") looks the member up by value and raises
            # ValueError for anything not in the vocabulary.
            return Proposal(SignalType(data["signal_type"]),
                            OperationalState(data["operational_state"]),
                            str(data.get("rationale", "")), True)
        except Exception as exc:
            # --- Anything unusable: fall back, saying what went wrong -------
            # type(exc).__name__ is the error's class name, e.g. "KeyError".
            return Proposal(FALLBACK_TYPE, FALLBACK_STATE,
                            f"unusable model reply ({type(exc).__name__})", False)

# EXEUNT — end of file.
