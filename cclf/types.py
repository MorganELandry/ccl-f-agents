"""
THE CAST LIST
A Play in Five Scenes
=====================

PROLOGUE
--------
Every other file in the cclf package talks about the same handful of things:
the commitment state an organization is in, the evidence it has been shown,
the agent's best guess about what is really going on, and the audit log
that records every decision. This file defines those things, once, so the
rest of the program shares one vocabulary (the canonical CCL-F v0.2 names).

Nothing in here calls a language model or the network. These are plain data
containers plus a few small helper methods. The commitment states map
directly to the LangGraph nodes in nodes.py; the rules about which moves
between states are legal live in guards.py, and graph.py wires the
nodes together.

Reference: CCL-F Framework v0.1 (Zenodo, CC BY-NC-ND 4.0)

THE PLAYBILL (what happens in this file)
    Scene 1  CommitmentState   the four states an organization can be in
    Scene 2  Evidence          one piece of evidence, plus its quality scores
    Scene 3  ACSEstimate       the agent's probability guess over the states
    Scene 4  AuditEntry        one tamper-evident line in the audit log
    Scene 5  CCLFAgentState    everything the graph carries from node to node

READER'S NOTE — dataclasses
    `@dataclass` placed above a class tells Python to write the boring
    methods for you. From the list of annotated fields (`content: str`) it
    generates __init__ (so you can write Evidence(evidence_id=..., ...)),
    __repr__ (a readable print-out) and __eq__ (two objects with equal
    fields compare equal). Fields with a default must come after fields
    without one, just like function arguments.

READER'S NOTE — field(default_factory=...)
    A plain default such as `confidence: float = 0.0` is evaluated once,
    when the class is defined, and shared by every instance. That is fine
    for numbers and strings, which cannot be changed in place. It is wrong
    for a list: every object would share the *same* list, and appending to
    one would append to all. (Python's dataclass refuses a bare `= []` for
    exactly this reason.) `field(default_factory=list)` instead says "call
    list() each time a new object is built", so every object gets its own
    fresh list. The same trick is used with `time.time`, so each object
    gets the time *it* was created, not the time the module was loaded,
    and with `ACSEstimate`, so each state gets its own estimate object.

READER'S NOTE — Enums
    An Enum is a fixed, named set of values. CommitmentState.OPEN can only
    ever be one of four members, so a typo becomes an error instead of a
    silent bug. Here the class also inherits from `str`, which makes every
    member *also* a real string: CommitmentState.OPEN == "OPEN" is True,
    and json.dumps() writes it out as "OPEN". That is what lets the audit
    hash (Scene 4) and the LangGraph checkpointer handle states easily.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# `from __future__ import annotations` stores type hints as text instead of
#   evaluating them, so a hint may name a class defined later in the file.
# Enum                 base class for the fixed set of commitment states.
# Any, Optional        type-hint helpers: Optional[X] means "X or None".
# dataclass, field     see the READER'S NOTES above.
# hashlib, json        used together to fingerprint an audit entry (Scene 4).
# time                 time.time() gives "seconds since 1970" for timestamps.
# ===========================================================================

from __future__ import annotations
from enum import Enum
from typing import Any, Optional
from dataclasses import dataclass, field
import hashlib
import json
import time


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ---------------------------------------------------------------------------
# This file has no module-level variables. Its whole cast is the five
# classes below; nothing outside a class is stored at the top level.
# ===========================================================================


# ===========================================================================
# SCENE 1 — THE FOUR STATES
# CommitmentState: where, on the road to committing, is the organization?
# ===========================================================================

class CommitmentState(str, Enum):
    """
    The four states of the CCL-F commitment state machine.

    OPEN         → signals are visible; no trajectory committed
    TRAJECTORY   → a direction is locked; alternatives are deprioritized
    AUTHORITY    → the decision authority has formally closed
    EXECUTION    → resources are deployed; reversal is operationally costly

    Blocked transitions (structurally enforced in guards.py, not just policy):
      EXECUTION  → TRAJECTORY   (cannot unspend)
      AUTHORITY  → OPEN         (authority closure is durable)
      TRAJECTORY → OPEN         (trajectory lock does not self-reverse)
      any        → skip a state  (no non-monotonic jumps)

    Because the class inherits from both `str` and `Enum`, each member is
    also its own string value (see the READER'S NOTE on Enums above).
    """
    # Each line is one member: NAME = value. The value is the same text as
    # the name, so the state reads the same in code, logs and JSON.
    OPEN        = "OPEN"
    TRAJECTORY  = "TRAJECTORY"
    AUTHORITY   = "AUTHORITY"
    EXECUTION   = "EXECUTION"


# ===========================================================================
# SCENE 2 — THE EVIDENCE
# Evidence: one item shown to the agent, and is it good enough to count?
# ===========================================================================

@dataclass
class Evidence:
    """
    A single piece of evidence presented to the agent.

    Fields:
        evidence_id          a short identifier chosen by the caller
        content              the text of the evidence itself
        source               where it came from (a report, a person, ...)
        timestamp            when this object was created (seconds since 1970);
                             filled in automatically by default_factory
        novelty_score        0.0–1.0, how new this is; None = not yet scored
        independence_score   0.0–1.0, how independent of earlier evidence;
                             None = not yet scored

    The two scores start as None and are filled in by the evidence_intake
    LLM node in nodes.py.
    """
    evidence_id: str
    content: str
    source: str
    timestamp: float = field(default_factory=time.time)
    # Novelty / independence scores set by the LLM node
    novelty_score: Optional[float] = None       # 0.0–1.0; None = not yet evaluated
    independence_score: Optional[float] = None  # 0.0–1.0; None = not yet evaluated

    # -----------------------------------------------------------------------
    # SCENE 2, PART 1 — THE ADMISSION TEST
    # is_admissible(): does this evidence count toward a decision?
    # -----------------------------------------------------------------------
    def is_admissible(self) -> bool:
        """
        Evidence must clear both novelty AND independence guards.

        Enter:   (none besides self)
        Exit:    True only if both scores have been set and both are >= 0.5;
                 False if either score is missing or below 0.5
        """
        # --- Not yet scored ---------------------------------------------
        # Unscored evidence is never admissible: we do not guess.
        if self.novelty_score is None or self.independence_score is None:
            return False
        # --- Both thresholds must pass ------------------------------------
        return self.novelty_score >= 0.5 and self.independence_score >= 0.5


# ===========================================================================
# SCENE 3 — THE HIDDEN STATE
# ACSEstimate: what does the agent believe the true commitment state is?
# ===========================================================================

@dataclass
class ACSEstimate:
    """
    Probability distribution over CommitmentStates inferred from behavioral signals.
    The agent cannot observe ACS directly; it maintains this distribution.

    ACS stands for Authority Commitment Signal. An organization may have
    *really* committed before it says so in public, so the agent keeps a
    belief over all four states instead of a single answer.

    Fields:
        p_open, p_trajectory, p_authority, p_execution
                     probability of each state (a fresh estimate is
                     100% OPEN, 0% everything else)
        confidence   0.0–1.0, how sure the inference node is of this estimate
        reasoning    the inference node's explanation, in words

    The acs_inference node in nodes.py replaces these numbers each cycle.
    """
    p_open: float       = 1.0
    p_trajectory: float = 0.0
    p_authority: float  = 0.0
    p_execution: float  = 0.0
    confidence: float   = 0.0
    reasoning: str      = ""

    # -----------------------------------------------------------------------
    # SCENE 3, PART 1 — THE BEST GUESS
    # most_likely(): which single state has the highest probability?
    # -----------------------------------------------------------------------
    def most_likely(self) -> CommitmentState:
        """
        Return the state with the highest probability.

        Enter:   (none besides self)
        Exit:    the CommitmentState whose p_* field is largest
        """
        # PLAYERS IN THIS SCENE
        #   probs   a dict from each CommitmentState to its probability

        # --- Pair each state with its number ----------------------------
        probs = {
            CommitmentState.OPEN:       self.p_open,
            CommitmentState.TRAJECTORY: self.p_trajectory,
            CommitmentState.AUTHORITY:  self.p_authority,
            CommitmentState.EXECUTION:  self.p_execution,
        }
        # --- Pick the winner -----------------------------------------------
        # max() over a dict walks its keys. `key=probs.get` tells max() to
        # compare each key by its value (probs.get(state)) instead of by the
        # key itself. On a tie, max() keeps the first key it saw, so the
        # earlier state in the list above wins.
        return max(probs, key=probs.get)


# ===========================================================================
# SCENE 4 — THE LEDGER LINE
# AuditEntry: one record in the log that nobody can quietly edit later
# ===========================================================================

@dataclass
class AuditEntry:
    """
    One entry in the append-only audit log.
    Each entry hashes its own content + the previous entry's hash,
    producing a tamper-evident chain.

    Fields:
        sequence     position of this entry in the log (0, 1, 2, ...)
        event_type   a short label such as "HUMAN_REVIEW" or "TRANSITION_APPLIED"
        from_state   the state before a transition, or None if not a transition
        to_state     the state after a transition, or None if not a transition
        payload      a dict of event details
        timestamp    when the entry was created (filled in automatically)
        prev_hash    entry_hash of the entry before this one ("GENESIS" for the
                     first entry, as supplied by CCLFAgentState.append_audit)
        entry_hash   this entry's own fingerprint (see below)

    How the hash chain works
    ------------------------
    A hash (here SHA-256) turns any input into a fixed 64-character
    fingerprint. Change a single character of the input and the fingerprint
    changes completely. Each entry's fingerprint covers its own fields *and*
    prev_hash, the fingerprint of the entry before it. So if someone edits
    entry 3, its fingerprint no longer matches what entry 4 recorded as
    prev_hash, and the chain visibly breaks from that point on. That is what
    "tamper-evident" means: tampering is not prevented, but it is detectable.

    Why a restored entry recomputes its hash and rejects a mismatch
    ---------------------------------------------------------------
    A brand-new entry is built with entry_hash left at "", and __post_init__
    simply fills it in. But an entry can also be *rebuilt* from saved data,
    for example when the LangGraph checkpointer loads a paused run back
    into memory: then every field, entry_hash included, is passed back in.
    If __post_init__ trusted that stored entry_hash, someone could edit the
    payload in storage and the entry would come back looking genuine. So
    the hash is always recomputed from the fields, and if a stored hash was
    supplied and it differs, the entry refuses to exist (ValueError).
    """
    sequence:    int
    event_type:  str
    from_state:  Optional[CommitmentState]
    to_state:    Optional[CommitmentState]
    payload:     dict[str, Any]
    timestamp:   float = field(default_factory=time.time)
    prev_hash:   str   = ""
    # Computed from the fields above. Accepted as an argument only so an
    # entry can be rebuilt from a checkpoint; a supplied value that does not
    # match the recomputed hash is rejected as tampering.
    entry_hash:  str   = ""

    # -----------------------------------------------------------------------
    # SCENE 4, PART 1 — THE SEAL
    # __post_init__(): stamp a new entry, or verify a rebuilt one
    # -----------------------------------------------------------------------
    def __post_init__(self):
        """
        Set entry_hash, checking any value that was passed in.

        Enter:   (none besides self; runs automatically right after the
                 dataclass-generated __init__ has stored every field)
        Exit:    self.entry_hash holds the freshly computed hash
                 raises ValueError if a non-empty entry_hash was supplied and
                 it does not match the entry's contents

        __post_init__ is a dataclass hook: if a class defines it, the
        generated __init__ calls it last, giving us a place for extra setup.
        """
        # PLAYERS IN THIS SCENE
        #   expected   the hash these fields *should* have

        expected = self._compute_hash()

        # --- Verify a restored entry -------------------------------------
        # An empty entry_hash means "new entry, nothing to check". A
        # non-empty one came from saved data and must match exactly.
        if self.entry_hash and self.entry_hash != expected:
            raise ValueError(
                f"Audit entry {self.sequence} failed integrity check: "
                "stored hash does not match its contents"
            )

        # --- Seal the entry ----------------------------------------------
        self.entry_hash = expected

    # -----------------------------------------------------------------------
    # SCENE 4, PART 2 — THE FINGERPRINT
    # _compute_hash(): what is the SHA-256 fingerprint of this entry?
    # -----------------------------------------------------------------------
    def _compute_hash(self) -> str:
        """
        Compute this entry's SHA-256 hash from its fields.

        Enter:   (none besides self)
        Exit:    a 64-character hexadecimal string

        Every field except entry_hash itself goes into the fingerprint
        (a hash cannot include itself).
        """
        # PLAYERS IN THIS SCENE
        #   blob   the entry's fields written out as one JSON string

        # --- Write the fields out in a fixed form --------------------------
        # A hash needs the exact same bytes every time for the same content.
        # sort_keys=True writes the dict keys in alphabetical order, so the
        # text never depends on the order the dict happened to be built in.
        # The states are str-Enums, so json writes them as plain "OPEN" etc.
        blob = json.dumps({
            "seq":        self.sequence,
            "event":      self.event_type,
            "from":       self.from_state,
            "to":         self.to_state,
            "payload":    self.payload,
            "ts":         self.timestamp,
            "prev_hash":  self.prev_hash,
        }, sort_keys=True)

        # --- Hash it ------------------------------------------------------
        # .encode() turns text into bytes (hashlib only accepts bytes);
        # .hexdigest() returns the result as readable hex characters.
        return hashlib.sha256(blob.encode()).hexdigest()


# ===========================================================================
# SCENE 5 — THE TRAVELLING TRUNK
# CCLFAgentState: everything the graph carries from one node to the next
# ===========================================================================

@dataclass
class CCLFAgentState:
    """
    The complete mutable state passed between LangGraph nodes.
    LangGraph requires state to be serialisable; all fields use basic types
    or dataclasses that can be converted to dicts.

    Each node in nodes.py receives this object, reads and changes some of
    its fields, and returns it. graph.py hands it to StateGraph so LangGraph
    knows which fields exist. The fields are described one by one below.
    Lists and the ACSEstimate use default_factory so that every new state
    gets its own copies (see the READER'S NOTE at the top of the file).
    """
    # Current formal commitment state
    commitment_state: CommitmentState = CommitmentState.OPEN

    # Evidence buffer (presented this session)
    evidence_buffer: list[Evidence] = field(default_factory=list)

    # ACS hidden-state estimate (updated by inference node)
    acs_estimate: ACSEstimate = field(default_factory=ACSEstimate)

    # Proposed transition (set by evaluation node, consumed by guard node)
    proposed_transition: Optional[CommitmentState] = None

    # Human-in-the-loop verdict (set by the human_review node, or written in
    # by an outside approval system while the graph is paused before it).
    # None means "no decision recorded yet"; True / False is the verdict.
    # apply_transition clears all three once the decision has been used, so
    # a decision can never carry over into the next review by accident.
    human_approval: Optional[bool] = None
    human_rationale: str = ""
    # Who decided: a reviewer ID from the outside system, the local user
    # name for an interactive decision, or "auto" in unattended mode.
    # CCL-F v0.2 requires every override to record the deciding agent's
    # identity (Layer 4, Execution Gates), so it goes into the audit log.
    human_reviewer: str = ""

    # Audit log — a list of AuditEntry objects, each chained to the one before
    audit_log: list[AuditEntry] = field(default_factory=list)

    # ACO flag — Adversarial Commitment Opacity detected
    aco_detected: bool = False
    aco_reasoning: str = ""

    # Free-form messages from nodes (for visibility / debugging)
    messages: list[str] = field(default_factory=list)

    # Termination signal
    should_terminate: bool = False

    # -----------------------------------------------------------------------
    # SCENE 5, PART 1 — THE TRANSLATOR
    # from_stream(): turn whatever LangGraph handed back into a state object
    # -----------------------------------------------------------------------
    @classmethod
    def from_stream(cls, chunk: Any) -> "CCLFAgentState":
        """
        Normalise a graph.stream(stream_mode="values") chunk to a state object.
        Recent LangGraph versions yield a plain dict of fields for dataclass
        state; older versions yielded the dataclass itself.

        Enter:   chunk   either a CCLFAgentState already, or a dict whose keys
                         are this class's field names (from graph.stream(),
                         graph.invoke() or graph.get_state(...).values)
        Exit:    a CCLFAgentState

        `@classmethod` means the method receives the class itself as `cls`
        instead of an instance as `self`. That lets it build a new object
        with `cls(...)` and is the usual Python way to write an alternative
        constructor. Callers write CCLFAgentState.from_stream(chunk).
        """
        # --- Already the right type: hand it straight back ----------------
        if isinstance(chunk, cls):
            return chunk

        # --- A dict of fields: unpack it into the constructor -------------
        # `cls(**chunk)` turns {"commitment_state": ..., "messages": ...} into
        # cls(commitment_state=..., messages=...). This is a shallow rebuild:
        # the values inside the dict (Evidence, AuditEntry, ...) are used as
        # they are, not converted again.
        return cls(**chunk)

    # -----------------------------------------------------------------------
    # SCENE 5, PART 2 — THE LAST LINK
    # last_audit_hash(): what should the next audit entry chain onto?
    # -----------------------------------------------------------------------
    def last_audit_hash(self) -> str:
        """
        Return the hash the next audit entry should record as prev_hash.

        Enter:   (none besides self)
        Exit:    the entry_hash of the newest audit entry, or the marker
                 string "GENESIS" if the log is still empty
        """
        # --- Empty log: the chain starts here ----------------------------
        # An empty list is "falsy", so `not self.audit_log` is True for [].
        if not self.audit_log:
            return "GENESIS"
        # --- Otherwise: the newest entry ([-1] means "last item") ----------
        return self.audit_log[-1].entry_hash

    # -----------------------------------------------------------------------
    # SCENE 5, PART 3 — THE SCRIBE
    # append_audit(): write one new, correctly chained entry to the log
    # -----------------------------------------------------------------------
    def append_audit(self, event_type: str, payload: dict,
                     from_state: Optional[CommitmentState] = None,
                     to_state: Optional[CommitmentState] = None) -> None:
        """
        Add a new AuditEntry to the end of the audit log.

        Enter:   event_type   short label for what happened
                 payload      dict of details to record
                 from_state   state before a transition (optional)
                 to_state     state after a transition (optional)
        Exit:    None; self.audit_log grows by one entry

        This is the one place entries are created during a run, so the
        sequence number and prev_hash are always filled in consistently.
        """
        # PLAYERS IN THIS SCENE
        #   entry   the new AuditEntry, already hashed by its __post_init__

        # --- Build the entry, chained to the previous one -----------------
        # sequence = current length, so the first entry is 0, the next 1...
        # entry_hash is left out on purpose: __post_init__ computes it.
        entry = AuditEntry(
            sequence=len(self.audit_log),
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            payload=payload,
            prev_hash=self.last_audit_hash(),
        )

        # --- Append-only: entries are added, never replaced ---------------
        self.audit_log.append(entry)

# EXEUNT — end of file.
