"""
THE FEDERATION
A Play in Six Acts
==================

PROLOGUE
--------
Commitment governance across agents that share no central authority.

Each agent ("node") runs its own Supervisor and keeps its own append-only,
hash-chained audit trail. What this module adds:

  Identity      each node has an Ed25519 key. Nodes recognize each other by
                public key, in their OWN trust lists; there is no central
                registry. A node's signature on its log head commits it to
                the whole log, because the log is a hash chain.
  Signed logs   a node publishes its log as a LogSegment: the entries plus a
                signed head. A receiver verifies the chain and the
                signature, and checks that the new log extends the one it
                saw before. A node that shows two different histories has
                signed both, so the fork is proof, not suspicion.
  Remote loops  a decision at node A may depend on a loop at node B. A
                registers a local MIRROR of that loop. Until A accepts B's
                closure, the mirror stays open: "A closure signal
                transmitted across an autonomy boundary ... does not
                constitute loop resolution" (Key Definitions, Attempted
                Closure). A accepts only after recomputing, from B's signed
                log, that B's closure really is an evidence closure, and
                after checking the evidence's attested origin. Then A
                closes the mirror itself (Local Closure), and A's own gates,
                coherence score and audit trail treat it like any loop.
  Authority     a power (recommend, authorize, execute) reaches a node only
                as a SignedGrant from someone who holds it there, delegably.
                A peer's recommendation or handoff is never a grant.
  Origins       evidence carries an Attestation signed by its PRODUCER (the
                lab, the instrument, the verifier), not by the agent passing
                it on. A primary document is pinned by a content hash; a
                formal proof can be re-checked by the receiver. Producers
                and evaluated processes declare their lineage (base model,
                training sources, upstream data) in signed statements, and
                remote evidence counts as independent only if the two
                lineages share nothing.
  Audit         audit_federation() takes every node's published log and
                checks each chain and signature, every cross-reference, and
                that no node showed different histories to different peers.

WHAT IS PROVEN AND WHAT IS ONLY ATTESTED
    Proven: who signed a log or an attestation (signatures); that a log was
    not edited, reordered or rolled back after a peer saw it (hash chain
    plus signed heads); what a document says (content hash); that a proof
    checks (if the receiver has a checker). Attested, not proven: that two
    lineages really share nothing. A lineage statement is a signed claim; a
    false one stays on the record under its signer's key. No cryptographic
    layer can prove the absence of a shared causal ancestry, which is what
    External Evidence Source ultimately asks.

THE PLAYBILL
    ACT I    IDENTITY
        Scene 1  PublicIdentity, AgentKey     a name and its key
        Scene 2  LineageStatement             a signed claim of causal ancestry
        Scene 3  TrustList                    whom this node recognizes
        Scene 4  SignedGrant, sign_grant(),   a signed grant of authority, and
                 SignedRevocation,            its signed withdrawal
                 sign_revocation()
    ACT II   SIGNED LOGS
        Scene 1  SignedHead, LogSegment       a published log
        Scene 2  verify_segment()             is it intact and signed?
    ACT III  ORIGINS
        Scene 1  Attestation                  a producer's signed word on evidence
        Scene 2  attest()                     produce one
        Scene 3  verify_attestation()         check one
    ACT IV   READING ANOTHER NODE'S LOG
        Scene 1  RemoteSignal, read_signal()  a loop as the peer's log shows it
        Scene 2  _remote_mirrors(),           Closure Chain, recomputed from
                 _remote_sound()              published logs, across nodes
    ACT V    THE NODE
        Scene 1  Node.__init__                the node's records
        Scene 2  recognize, declare_lineage, hold_attestation
        Scene 3  publish                      sign and publish the log
        Scene 4  receive, _recheck            verify a peer's log; catch forks
        Scene 5  depend                       a decision rests on a peer's loop
        Scene 6  _check_item, _verified       verify a remote loop, link by link
        Scene 7  accept_remote_closure        accept it, then close the mirror
        Scene 8  receive_grant,               authority from another node, and
                 receive_revocation           its withdrawal
        Scene 9  _withdraw                    a peer's closure no longer stands
    ACT VI   THE AUDITOR
        Scene 1  AuditReport, audit_federation()

READER'S NOTE — why signing the head signs the whole log
    Each audit entry stores the hash of the entry before it. The last
    entry's hash (the "head") therefore depends on every earlier entry. A
    signature over the head is a signature over the entire history: change
    any earlier entry and the head changes, and the signature no longer
    fits.

READER'S NOTE — Ed25519
    A digital-signature scheme. A private key signs bytes; anyone with the
    matching public key can check the signature, and no one without the
    private key can produce one. The `cryptography` package provides it.

READER'S NOTE — canonical bytes
    To sign a record, it is first turned into bytes the same way every
    time: JSON with sorted keys and no spaces (_canonical_bytes). Signer
    and verifier must produce identical bytes, or a true signature fails.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# copy                      deep copies, so no node shares a record with another.
# secrets                   the random nonce in a signed grant.
# hashlib, json             content hashes and canonical bytes.
# dataclass, field          the record types.
# Callable, Iterable,       type hints.
#   Optional
# cryptography              Ed25519 keys and signatures (requirements.txt).
# .audit                    AuditEntry, AuditTrail, GENESIS: the hash chain.
# .supervisor               Supervisor, TransitionRefused, Settings.
# .types                    the vocabulary used to mirror a remote loop.
# ===========================================================================

from __future__ import annotations

import copy
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey,
)

from .audit import GENESIS, AuditEntry, AuditTrail
from .statemachine import check_transition, exit_allowed
from .supervisor import Settings, Supervisor, TransitionRefused
from .types import (CommitmentState, EES_ELIGIBLE_KINDS, EvidenceKind, OperationalState, Power,
                    Referent, SignalType)


# ===========================================================================
# DRAMATIS PERSONAE (every module-level variable, declared here at the top)
# ===========================================================================

# MIRROR_SEPARATOR — joins a peer's name and its signal id into the id of the
#   local mirror ("bell/frr-3").
MIRROR_SEPARATOR = "/"

# NOMINAL_STATES — operational states a mirror cannot inherit as-is: a
#   nominal classification needs validating evidence the receiver has not
#   seen yet (Rule 2), so a mirror of a nominal loop starts as elevated
#   uncertainty.
NOMINAL_STATES = {OperationalState.NOMINAL.value}


# ===========================================================================
# STAGEHANDS — small helpers used throughout
# ===========================================================================

def _canonical_bytes(record: dict) -> bytes:
    """
    The bytes that get signed for a record.

    Enter:   record   a JSON-ready dict
    Exit:    UTF-8 JSON with sorted keys and no spaces
    """
    return json.dumps(record, sort_keys=True, separators=(",", ":")).encode()


def content_hash(artifact: str) -> str:
    """
    The SHA-256 of an artifact's text, as hex.

    Enter:   artifact   the text (a document, a proof, a measurement file)
    Exit:    64 hex characters
    """
    return hashlib.sha256(artifact.encode()).hexdigest()


# ###########################################################################
# ACT I — IDENTITY
# ###########################################################################

# ===========================================================================
# ACT I, SCENE 1 — A NAME AND ITS KEY
# ===========================================================================

@dataclass(frozen=True)
class PublicIdentity:
    """
    What other nodes know about an agent: its name and public key.

    Fields:
      name         the agent's name, as it appears in logs
      public_hex   its Ed25519 public key, as hex
    """
    name: str
    public_hex: str

    @property
    def fingerprint(self) -> str:
        """
        A short, stable label for the key (first 16 hex digits of its
        SHA-256), for logs and messages.

        Enter:   (none)
        Exit:    16 hex characters
        """
        return hashlib.sha256(bytes.fromhex(self.public_hex)).hexdigest()[:16]

    def verify(self, record: dict, signature_hex: str) -> bool:
        """
        Did this identity's private key sign this record?

        Enter:   record          the signed record (a dict)
                 signature_hex   the signature, as hex
        Exit:    True if the signature is valid for these exact bytes
        """
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(self.public_hex)).verify(
                bytes.fromhex(signature_hex), _canonical_bytes(record))
            return True
        except (InvalidSignature, ValueError):
            return False


class AgentKey:
    """
    An agent's private key. Only the agent holds it.
    """

    def __init__(self, name: str, private: Optional[Ed25519PrivateKey] = None):
        """
        Enter:   name      the agent's name
                 private   an existing key, or None to generate a new one
        Exit:    self.name, self._private (never shared)
        """
        self.name = name
        self._private = private or Ed25519PrivateKey.generate()

    @property
    def public(self) -> PublicIdentity:
        """
        The identity to hand to other nodes.

        Enter:   (none)
        Exit:    a PublicIdentity for this key
        """
        # PLAYERS IN THIS SCENE
        #   raw   the 32-byte public key

        raw = self._private.public_key().public_bytes_raw()
        return PublicIdentity(self.name, raw.hex())

    def sign(self, record: dict) -> str:
        """
        Sign a record.

        Enter:   record   a JSON-ready dict
        Exit:    the signature, as hex
        """
        return self._private.sign(_canonical_bytes(record)).hex()


# ===========================================================================
# ACT I, SCENE 2 — A SIGNED CLAIM OF ANCESTRY
# ===========================================================================

@dataclass(frozen=True)
class LineageStatement:
    """
    A party's signed declaration of what its outputs causally descend from:
    its base model, training sources, upstream data, instruments.

    Fields:
      subject     the party (a producer, or a process under evaluation)
      lineage     the declared ancestry, as a tuple of labels
      version     a number the subject raises with each new statement, so
                  an older statement replayed later cannot replace a newer
                  one
      signature   the subject's signature over (subject, lineage, version)

    Two parties whose lineages share a label are not causally independent
    (Layer 2, External Evidence Source). A statement is a claim, not a
    proof; signing it makes it attributable.
    """
    subject: str
    lineage: tuple[str, ...]
    version: int
    signature: str

    def record(self) -> dict:
        """
        The signed part.

        Enter:   (none)
        Exit:    {"subject", "lineage" (sorted), "version"}
        """
        return {"subject": self.subject, "lineage": sorted(self.lineage),
                "version": self.version}


def declare_lineage(key: AgentKey, lineage: Iterable[str], version: int = 1) -> LineageStatement:
    """
    Sign a lineage statement for this key's owner.

    Enter:   key       the subject's own key
             lineage   the labels it descends from
             version   1 for the first statement; higher for each update
    Exit:    a LineageStatement
    """
    # PLAYERS IN THIS SCENE
    #   labels   the lineage, deduplicated and sorted

    labels = tuple(sorted(set(lineage)))
    return LineageStatement(key.name, labels, version,
                            key.sign({"subject": key.name, "lineage": list(labels),
                                      "version": version}))


# ===========================================================================
# ACT I, SCENE 3 — WHOM THIS NODE RECOGNIZES
# ===========================================================================

class TrustList:
    """
    One node's own list of the identities and lineages it recognizes.
    Every node keeps its own; there is no shared registry to capture.
    """

    def __init__(self):
        """
        Enter:   (none)
        Exit:    empty identities and lineages
        """
        self.identities: dict[str, PublicIdentity] = {}
        self.lineages: dict[str, LineageStatement] = {}

    def recognize(self, identity: PublicIdentity) -> None:
        """
        Recognize a party by its public key. A different key under a name
        already recognized is refused, so a name cannot be taken over. A
        name containing MIRROR_SEPARATOR is refused, so two mirror ids
        ("x" + "y/s", "x/y" + "s") can never coincide.

        Enter:   identity   the party's PublicIdentity
        Exit:    None; raises TransitionRefused on a conflicting key or name
        """
        # PLAYERS IN THIS SCENE
        #   known   the identity already recognized under this name, if any

        if MIRROR_SEPARATOR in identity.name or not identity.name:
            raise TransitionRefused(f"{identity.name!r}: a name may not be empty or contain "
                                    f"{MIRROR_SEPARATOR!r}")
        known = self.identities.get(identity.name)
        if known is not None and known.public_hex != identity.public_hex:
            raise TransitionRefused(f"{identity.name} is already recognized with a different key")
        self.identities[identity.name] = identity

    def add_lineage(self, statement: LineageStatement) -> None:
        """
        Record a lineage statement, after checking its subject signed it
        and that it is newer than the one on record.

        Enter:   statement   the LineageStatement
        Exit:    None; raises TransitionRefused if the subject is not
                 recognized, the signature fails, or its version is not
                 above the recorded statement's (the same statement again
                 is a no-op)
        """
        # PLAYERS IN THIS SCENE
        #   who   the subject's recognized identity

        who = self.identities.get(statement.subject)
        if who is None or not who.verify(statement.record(), statement.signature):
            raise TransitionRefused(f"lineage statement for {statement.subject!r} "
                                    "is not signed by a recognized key")
        known = self.lineages.get(statement.subject)
        if known is not None and known != statement and statement.version <= known.version:
            raise TransitionRefused(f"lineage statement v{statement.version} for "
                                    f"{statement.subject!r} is not newer than v{known.version}")
        self.lineages[statement.subject] = statement


# ===========================================================================
# ACT I, SCENE 4 — A SIGNED GRANT OF AUTHORITY
# ===========================================================================

@dataclass(frozen=True)
class SignedGrant:
    """
    A grantor's signed grant of a power, addressed to one node.

    Fields:
      grantor     who grants it (must hold the power, delegably, at `node`)
      grantee     who receives it
      node        the node whose Supervisor it applies to (so it cannot be
                  replayed at another node)
      power       the Power's value
      scope       the decision scope ("*" for all)
      delegable   may the grantee grant it on?
      expires_at  wall-clock lapse time (seconds since the epoch), or None
      nonce       random, so two grants with the same terms are different
                  grants (Ed25519 signatures are deterministic), and a node
                  can refuse any grant it has already received
      signature   the grantor's signature over all of the above

    Interoperability carries authority only this way. A recommendation, a
    handoff or a log entry from a peer is never a grant.
    """
    grantor: str
    grantee: str
    node: str
    power: str
    scope: str
    delegable: bool
    expires_at: Optional[float]
    nonce: str
    signature: str

    def record(self) -> dict:
        """
        The signed part.

        Enter:   (none)
        Exit:    every field but the signature
        """
        return {"grantor": self.grantor, "grantee": self.grantee, "node": self.node,
                "power": self.power, "scope": self.scope, "delegable": self.delegable,
                "expires_at": self.expires_at, "nonce": self.nonce}

    @property
    def ref(self) -> str:
        """
        A stable reference to this exact grant, for revoking it: the
        SHA-256 of its signature.

        Enter:   (none)
        Exit:    64 hex characters
        """
        return content_hash(self.signature)


def sign_grant(grantor_key: AgentKey, grantee: str, node: str, power: Power, scope: str,
               delegable: bool = False, expires_at: Optional[float] = None) -> SignedGrant:
    """
    The grantor signs a grant.

    Enter:   grantor_key   the grantor's own key
             grantee, node, power, scope, delegable, expires_at
                           as in SignedGrant
    Exit:    a SignedGrant
    """
    # PLAYERS IN THIS SCENE
    #   rec   the signed fields

    rec = {"grantor": grantor_key.name, "grantee": grantee, "node": node,
           "power": Power(power).value, "scope": scope, "delegable": delegable,
           "expires_at": expires_at, "nonce": secrets.token_hex(16)}
    return SignedGrant(grantor_key.name, grantee, node, rec["power"], scope, delegable,
                       expires_at, rec["nonce"], grantor_key.sign(rec))


@dataclass(frozen=True)
class SignedRevocation:
    """
    A signed withdrawal of a grant, addressed to one node.

    Fields:
      revoker     who withdraws it (its grantor, a grantor above it, or a root)
      node        the node holding the grant
      grant_ref   the SignedGrant's ref
      reason      why
      signature   the revoker's signature over all of the above

    A revocation binds only once it arrives. Until then the node holding
    the grant cannot know of it; an expiry on the grant bounds that window.
    """
    revoker: str
    node: str
    grant_ref: str
    reason: str
    signature: str

    def record(self) -> dict:
        """
        The signed part.

        Enter:   (none)
        Exit:    every field but the signature
        """
        return {"revoker": self.revoker, "node": self.node, "grant_ref": self.grant_ref,
                "reason": self.reason}


def sign_revocation(revoker_key: AgentKey, grant: SignedGrant, reason: str) -> SignedRevocation:
    """
    Sign the withdrawal of a grant.

    Enter:   revoker_key   the revoker's own key
             grant         the SignedGrant being withdrawn
             reason        why
    Exit:    a SignedRevocation addressed to the grant's node
    """
    # PLAYERS IN THIS SCENE
    #   rec   the signed fields

    rec = {"revoker": revoker_key.name, "node": grant.node, "grant_ref": grant.ref,
           "reason": reason}
    return SignedRevocation(revoker_key.name, grant.node, grant.ref, reason,
                            revoker_key.sign(rec))


# ###########################################################################
# ACT II — SIGNED LOGS
# ###########################################################################

# ===========================================================================
# ACT II, SCENE 1 — A PUBLISHED LOG
# ===========================================================================

@dataclass(frozen=True)
class SignedHead:
    """
    A node's signature over the head of its log.

    Fields:
      agent       the publishing node
      length      how many entries the log has
      head_hash   the last entry's hash (GENESIS for an empty log)
      signature   the node's signature over (agent, length, head_hash)
    """
    agent: str
    length: int
    head_hash: str
    signature: str

    def record(self) -> dict:
        """
        The signed part.

        Enter:   (none)
        Exit:    {"agent", "length", "head_hash"}
        """
        return {"agent": self.agent, "length": self.length, "head_hash": self.head_hash}


@dataclass(frozen=True)
class LogSegment:
    """
    What a node publishes: its whole log, a signed head, and the producer
    attestations for evidence in it.

    Fields:
      head           the SignedHead
      entries        the AuditEntry records, oldest first
      attestations   Attestation records it carries, by evidence id
    """
    head: SignedHead
    entries: tuple[AuditEntry, ...]
    attestations: tuple["Attestation", ...] = ()


# ===========================================================================
# ACT II, SCENE 2 — IS IT INTACT AND SIGNED?
# ===========================================================================

def verify_segment(segment: LogSegment, trust: TrustList) -> tuple[bool, str]:
    """
    Check a published log: recognized signer, valid signature, intact chain
    ending exactly at the signed head, and entries an honest Supervisor
    could have written (parse_log).

    Enter:   segment   the LogSegment
             trust     the verifier's TrustList
    Exit:    (True, "ok") or (False, reason)
    """
    # PLAYERS IN THIS SCENE
    #   who      the publisher's recognized identity
    #   ok, why  the hash-chain check

    who = trust.identities.get(segment.head.agent)
    if who is None:
        return False, f"{segment.head.agent} is not recognized"
    if not who.verify(segment.head.record(), segment.head.signature):
        return False, f"head signature for {segment.head.agent} is invalid"
    if len(segment.entries) != segment.head.length:
        return False, "entry count does not match the signed head"
    ok, why = AuditTrail.verify(list(segment.entries), expected_head=segment.head.head_hash)
    if not ok:
        return False, f"chain: {why}"
    problems = parse_log(segment.entries).problems
    if problems:
        return False, "malformed log: " + "; ".join(problems[:3])
    return True, "ok"


# ###########################################################################
# ACT III — ORIGINS
# ###########################################################################

# ===========================================================================
# ACT III, SCENE 1 — A PRODUCER'S SIGNED WORD ON EVIDENCE
# ===========================================================================

@dataclass(frozen=True)
class Attestation:
    """
    The producer's own signed statement about an item of evidence.

    Fields:
      evidence_id    the evidence id as it appears in the relaying node's log
      producer       the producing party (must match produced_by in the log)
      relay          the node the producer gave it to: the only node whose
                     log it can be cited from, so it cannot be replayed
                     into another node's log
      kind           the evidence kind's value
      content_hash   SHA-256 of the artifact
      artifact       the artifact itself, if shipped (a document, a proof)
      signature      the producer's signature over everything but artifact

    The relaying node cannot forge it: only the producer's key signs it.
    """
    evidence_id: str
    producer: str
    relay: str
    kind: str
    content_hash: str
    artifact: Optional[str]
    signature: str

    def record(self) -> dict:
        """
        The signed part (the artifact is bound through its hash).

        Enter:   (none)
        Exit:    {"evidence_id", "producer", "relay", "kind", "content_hash"}
        """
        return {"evidence_id": self.evidence_id, "producer": self.producer,
                "relay": self.relay, "kind": self.kind, "content_hash": self.content_hash}


# ===========================================================================
# ACT III, SCENE 2 — PRODUCE ONE
# ===========================================================================

def attest(producer_key: AgentKey, relay: str, evidence_id: str, kind: EvidenceKind,
           artifact: str, ship_artifact: bool = True) -> Attestation:
    """
    The producer signs its evidence.

    Enter:   producer_key    the producer's own key
             relay           the node it is giving the evidence to
             evidence_id     the id the relaying node will log it under
             kind            its EvidenceKind
             artifact        its content
             ship_artifact   include the artifact itself (False: hash only)
    Exit:    an Attestation
    """
    # PLAYERS IN THIS SCENE
    #   rec   the signed fields

    rec = {"evidence_id": evidence_id, "producer": producer_key.name, "relay": relay,
           "kind": EvidenceKind(kind).value, "content_hash": content_hash(artifact)}
    return Attestation(evidence_id, producer_key.name, relay, rec["kind"],
                       rec["content_hash"], artifact if ship_artifact else None,
                       producer_key.sign(rec))


# ===========================================================================
# ACT III, SCENE 3 — CHECK ONE
# ===========================================================================

def verify_attestation(att: Attestation, trust: TrustList,
                       checkers: dict[str, Callable[[str], bool]]) -> tuple[bool, str]:
    """
    Is this attestation signed by a recognized producer, and does what can
    be checked check out?

    Enter:   att        the Attestation
             trust      the verifier's TrustList
             checkers   evidence kind value -> function that re-checks an
                        artifact (e.g. a proof checker for formal
                        verification)
    Exit:    (True, "ok") or (False, reason)

    Checked: the producer's signature; the artifact's hash, if the artifact
    was shipped; the artifact itself, by a checker, if one is registered
    for its kind. A formal proof with a checker is the one case where the
    evidence is verified independently of anyone's word.
    """
    # PLAYERS IN THIS SCENE
    #   who     the producer's recognized identity
    #   check   the checker for this kind, if any

    who = trust.identities.get(att.producer)
    if who is None:
        return False, f"producer {att.producer!r} is not recognized"
    if not who.verify(att.record(), att.signature):
        return False, f"attestation signature by {att.producer!r} is invalid"
    if att.artifact is not None and content_hash(att.artifact) != att.content_hash:
        return False, "artifact does not match its attested hash"
    check = checkers.get(att.kind)
    if check is not None:
        if att.artifact is None:
            return False, f"no artifact shipped for re-checkable {att.kind} evidence"
        if not check(att.artifact):
            return False, f"{att.kind} artifact failed the receiver's check"
    return True, "ok"


# ###########################################################################
# ACT IV — READING ANOTHER NODE'S LOG
# ###########################################################################

# ===========================================================================
# ACT IV, SCENE 1 — A LOOP AS THE PEER'S LOG SHOWS IT
# ===========================================================================

@dataclass
class RemoteSignal:
    """
    One signal, reconstructed from a peer's log entries alone.

    Fields:
      signal_id, signal_type, registrant, referent, evaluated_process,
      registered_at, at_registration, failure_mode, steward, successor
                        from its registration entry
      state             its latest commitment state
      operational_state its latest classification, if any
      closure           the latest TRANSITION entry into a closed state, or None
      exit              the latest EXIT entry, or None (a superseded exit
                        citing an External Evidence Source resolves an
                        upstream loop: Layer 2, Closure Chain)
    """
    signal_id: str
    signal_type: str
    registrant: str
    referent: str
    evaluated_process: str
    registered_at: int
    at_registration: frozenset
    failure_mode: Optional[str]
    steward: Optional[str]
    successor: Optional[str]
    state: str = "registered"
    operational_state: Optional[str] = None
    closure: Optional[AuditEntry] = None
    exit: Optional[AuditEntry] = None


@dataclass
class ParsedLog:
    """
    A peer's log, replayed and checked.

    Fields:
      signals    signal id -> RemoteSignal
      evidence   evidence id -> {"kind", "produced_by", "at", "depends_on"}
      mirrors    mirror id -> (owning node, the owner's signal id)
      problems   every way the log is malformed; empty for a sound log
    """
    signals: dict = field(default_factory=dict)
    evidence: dict = field(default_factory=dict)
    mirrors: dict = field(default_factory=dict)
    problems: list = field(default_factory=list)


def _state(value) -> Optional[CommitmentState]:
    """A CommitmentState from its value, or None if it is not one."""
    try:
        return CommitmentState(value)
    except ValueError:
        return None


def parse_log(entries: Iterable[AuditEntry]) -> ParsedLog:
    """
    Replay a log entry by entry, as the peer's own Supervisor would have
    written it, and reconstruct its signals, evidence and mirrors.

    Enter:   entries   a node's audit entries, oldest first
    Exit:    a ParsedLog; any entry an honest Supervisor could not have
             written is a problem, and a log with problems is refused
             (verify_segment)

    A dishonest node controls its own log entirely, so nothing in it is
    taken on trust. Checked: every registration is a signal's first entry
    and happens once; every TRANSITION starts from the state the signal is
    in and is a move the Layer 4 table allows; EXIT only from an open
    state, REENTRY only from exited; DEPENDENCY_ADDED only for evidence on
    record; MIRROR_REGISTERED names a signal
    registered in the entry just before it, so a loop cannot be relabeled
    a mirror after the fact; evidence ids are unique; required fields are
    present and of the right type.
    """
    # PLAYERS IN THIS SCENE
    #   out          the ParsedLog being built
    #   last_reg     the signal registered by the previous entry, if any
    #   e, p, sid    each entry, its payload, and the signal it names
    #   sig          that signal's reconstruction
    #   cur, to      states, as CommitmentState
    #   bad          records one problem for this entry

    out = ParsedLog()
    last_reg = None
    for e in entries:
        p = e.payload if isinstance(e.payload, dict) else {}
        sid = p.get("signal")
        sig = out.signals.get(sid) if isinstance(sid, str) else None

        def bad(why: str) -> None:
            out.problems.append(f"entry {e.sequence} ({e.event}): {why}")

        reg_before, last_reg = last_reg, None
        if e.event == "TRANSITION" and p.get("from") == "unregistered":
            fields = ("signal", "signal_type", "referent", "evaluated_process")
            if not all(isinstance(p.get(k), str) for k in fields):
                bad("registration is missing a field")
            elif sig is not None:
                bad(f"{sid} is registered twice")
            elif p.get("to") != "registered":
                bad("registration does not lead to registered")
            else:
                out.signals[sid] = RemoteSignal(
                    sid, p["signal_type"], e.actor, p["referent"], p["evaluated_process"],
                    e.at, frozenset(p.get("evidence_at_registration") or []),
                    p.get("failure_mode"), p.get("steward"), p.get("successor"))
                last_reg = sid
        elif e.event == "TRANSITION":
            cur, to = _state(p.get("from")), _state(p.get("to"))
            if sig is None:
                bad(f"transition of unregistered signal {sid!r}")
            elif cur is None or to is None:
                bad("transition without valid from/to states")
            elif cur.value != sig.state:
                bad(f"{sid} is {sig.state}, not {cur.value}")
            elif not check_transition(cur, to)[0]:
                bad(f"{cur.value} -> {to.value} is not in the Layer 4 table")
            else:
                sig.state = to.value
                sig.closure = e if to.value.startswith("closed_") else sig.closure
        elif e.event == "EXIT":
            if sig is None or not exit_allowed(_state(sig.state))[0] \
                    or p.get("from") != sig.state:
                bad(f"exit of {sid!r} from a state it is not in, or not open")
            else:
                sig.state = "exited"
                sig.exit = e
        elif e.event == "REENTRY":
            if sig is None or sig.state != "exited":
                bad(f"re-entry of {sid!r}, which has not exited")
            else:
                sig.state = "under_review"
        elif e.event == "CLASSIFIED":
            if sig is None or not isinstance(p.get("operational_state"), str):
                bad(f"classification of unregistered signal {sid!r}")
            else:
                sig.operational_state = p["operational_state"]
        elif e.event == "MIRROR_REGISTERED":
            mid = p.get("mirror")
            if not (isinstance(mid, str) and isinstance(p.get("peer"), str)
                    and isinstance(p.get("signal"), str)):
                bad("mirror declaration is missing a field")
            elif mid != reg_before:
                bad(f"{mid!r} is declared a mirror after the fact (it must be declared "
                    "in the entry right after its registration)")
            else:
                out.mirrors[mid] = (p["peer"], p["signal"])
        elif e.event == "EVIDENCE_ADDED":
            eid = p.get("evidence")
            if not (isinstance(eid, str) and isinstance(p.get("kind"), str)
                    and isinstance(p.get("produced_by"), str)
                    and isinstance(p.get("depends_on", []), list)):
                bad("evidence record is missing a field")
            elif eid in out.evidence:
                bad(f"evidence {eid!r} is added twice")
            else:
                out.evidence[eid] = {"kind": p["kind"], "produced_by": p["produced_by"],
                                     "at": e.at, "depends_on": list(p.get("depends_on", []))}
        elif e.event == "DEPENDENCY_ADDED":
            # A dependency found later (Supervisor.add_dependency): the
            # evidence now rests on one more upstream loop.
            eid, up = p.get("evidence"), p.get("upstream")
            if eid not in out.evidence or not isinstance(up, str):
                bad(f"dependency added to unknown evidence {eid!r}")
            elif up not in out.evidence[eid]["depends_on"]:
                out.evidence[eid]["depends_on"].append(up)
    return out


def read_signal(entries: Iterable[AuditEntry], signal_id: str) -> Optional[RemoteSignal]:
    """
    One signal as a log shows it (see parse_log).

    Enter:   entries     a node's audit entries, oldest first
             signal_id   the node's id for the signal
    Exit:    a RemoteSignal, or None if the log never registered it
    """
    return parse_log(entries).signals.get(signal_id)


def _remote_evidence(entries: Iterable[AuditEntry]) -> dict[str, dict]:
    """
    Every evidence record in a log, by evidence id (see parse_log).

    Enter:   entries   a node's audit entries
    Exit:    evidence id -> {"kind", "produced_by", "at", "depends_on"}
    """
    return parse_log(entries).evidence


def _remote_ees(record: dict, sig: RemoteSignal, claimant: str) -> bool:
    """
    The External Evidence Source test on a peer's evidence record, by the
    same one definition the Supervisor uses (Supervisor.is_ees).

    Enter:   record     the evidence record ({"kind", "produced_by", ...})
             sig        the RemoteSignal the claim is about
             claimant   the agent making the claim (the closing or exiting
                        agent: the actor of that log entry)
    Exit:    True if the kind is eligible and the producer is neither the
             claimant nor the signal's evaluated process

    Spec (Layer 2, EES): the producer is not "the agent making the claim it
    is offered for (the closing agent, for a closure ...)" nor "any process
    whose output the claim evaluates". The registrant is not excluded as
    such.
    """
    return (record["kind"] in {k.value for k in EES_ELIGIBLE_KINDS}
            and record["produced_by"] not in (sig.evaluated_process, claimant))


def _remote_qualifying(sig: RemoteSignal, evidence: dict[str, dict]) -> list[str]:
    """
    Recompute which cited evidence of a peer's closure is novel and EES,
    by the same rules the peer's own Supervisor uses.

    Enter:   sig        the RemoteSignal (must have a closure)
             evidence   the peer's evidence records
    Exit:    the qualifying evidence ids; the claimant is the agent who
             made the closure (the closure entry's actor)
    """
    return [eid for eid in sig.closure.payload.get("cited_evidence", [])
            if eid in evidence
            and eid not in sig.at_registration and evidence[eid]["at"] > sig.registered_at
            and _remote_ees(evidence[eid], sig, sig.closure.actor)]


def _remote_superseded(sig: RemoteSignal, evidence: dict[str, dict]) -> list[str]:
    """
    For a peer's loop exited as superseded: the cited evidence that is an
    External Evidence Source for the exiting agent's claim.

    Enter:   sig        the RemoteSignal
             evidence   the peer's evidence records
    Exit:    the qualifying ids (empty unless the loop is exited superseded)

    Mirrors Supervisor._supersession_shown.
    """
    if sig.state != "exited" or sig.exit is None \
            or sig.exit.payload.get("exit_type") != "superseded":
        return []
    return [eid for eid in sig.exit.payload.get("evidence", []) or []
            if eid in evidence and _remote_ees(evidence[eid], sig, sig.exit.actor)]


# ===========================================================================
# ACT IV, SCENE 2 — CLOSURE CHAIN, RECOMPUTED REMOTELY
# ===========================================================================

def _remote_mirrors(entries: Iterable[AuditEntry]) -> dict[str, tuple[str, str]]:
    """
    The mirrors a log declares (see parse_log).

    Enter:   entries   a node's audit entries
    Exit:    mirror id -> (owning node, the owner's signal id)
    """
    return parse_log(entries).mirrors


def _remote_sound(entries: list[AuditEntry], signal_id: str, owner: str = "",
                  resolve: Optional[Callable[[str], Optional[list[AuditEntry]]]] = None,
                  seen: frozenset = frozenset()) -> tuple[bool, list[str]]:
    """
    Is the signal closed by a chain-sound evidence closure, judged from
    published logs alone? (Structure only: no attestations or lineage. The
    node's own acceptance, Node._verified, checks those as well.)

    Enter:   entries     the log holding the signal
             signal_id   the signal
             owner       whose log it is (labels the cycle guard)
             resolve     node name -> its published entries, for following
                         a mirror to the loop it stands for; None means
                         mirrors cannot be followed and never count
             seen        (owner, signal) pairs already on the path
    Exit:    (sound?, the qualifying evidence ids that make it so)

    The same least-fixed-point rule as Supervisor._closure_sound: at least
    one qualifying item, and every cited item's upstream loops resolved
    (chain-sound, or superseded with an EES), no cycles. A mirror is sound
    only if the loop it stands for is sound in its owner's log too, so a
    node cannot vouch for a loop it does not own.
    """
    # PLAYERS IN THIS SCENE
    #   key        this (log, signal) pair, for the cycle guard
    #   sig        the signal, as the log shows it
    #   mirrors    the log's mirrors
    #   peer, inner, theirs   the owner of a mirrored loop, its id, its log
    #   evidence   the log's evidence records
    #   good       qualifying items whose upstream loops are all sound

    key = (owner, signal_id)
    if key in seen:
        return False, []
    sig = read_signal(entries, signal_id)
    if sig is not None and sig.state == "exited":
        # An upstream loop superseded with an EES is resolved (Closure Chain).
        shown = _remote_superseded(sig, _remote_evidence(entries))
        return bool(shown), shown
    if sig is None or sig.state != "closed_evidence" or sig.closure is None:
        return False, []
    mirrors = _remote_mirrors(entries)
    if signal_id in mirrors:
        peer, inner = mirrors[signal_id]
        theirs = resolve(peer) if resolve else None
        if theirs is None or not _remote_sound(theirs, inner, peer, resolve, seen | {key})[0]:
            return False, []
    evidence = _remote_evidence(entries)
    # Every cited item is load-bearing: each one's upstream loops must be
    # resolved, not just one qualifying item's.
    cited = [eid for eid in sig.closure.payload.get("cited_evidence", []) if eid in evidence]
    if not all(_remote_sound(entries, up, owner, resolve, seen | {key})[0]
               for eid in cited for up in evidence[eid]["depends_on"]):
        return False, []
    good = _remote_qualifying(sig, evidence)
    return bool(good), good


# ###########################################################################
# ACT V — THE NODE
# ###########################################################################

class Node:
    """
    One agent in a federation: its own Supervisor, its own signed log, its
    own trust list, and mirrors of the remote loops its decisions rest on.
    """

    # =======================================================================
    # ACT V, SCENE 1 — THE NODE'S RECORDS
    # =======================================================================

    def __init__(self, key: AgentKey, settings: Optional[Settings] = None,
                 checkers: Optional[dict[str, Callable[[str], bool]]] = None):
        """
        Enter:   key        this node's AgentKey
                 settings   Settings for its Supervisor
                 checkers   evidence kind value -> artifact re-checker
        Exit:    a node that recognizes only itself

        Records:
          name, key, sv            identity and the local Supervisor
          trust                    whom this node recognizes (TrustList)
          peers                    peer name -> the latest verified LogSegment
          attestations             evidence id -> Attestation this node carries
          mirrors                  mirror id -> (peer, peer signal id)
          accepted                 mirror id -> hash of the peer closure entry
                                   accepted for it
          equivocators             peers caught signing two histories, or a
                                   log no honest Supervisor writes
          grant_refs               SignedGrant ref -> the local grant id it
                                   became (for revocations); a ref already
                                   here is never accepted again
        """
        self.name = key.name
        self.key = key
        self.sv = Supervisor(settings)
        self.trust = TrustList()
        self.trust.recognize(key.public)
        self.checkers = dict(checkers or {})
        self.peers: dict[str, LogSegment] = {}
        self.attestations: dict[str, Attestation] = {}
        self.mirrors: dict[str, tuple[str, str]] = {}
        self.accepted: dict[str, str] = {}
        self.equivocators: set[str] = set()
        self.grant_refs: dict[str, str] = {}

    # =======================================================================
    # ACT V, SCENE 2 — WHOM AND WHAT THIS NODE KNOWS
    # =======================================================================

    def recognize(self, identity: PublicIdentity, by: str, principal: bool = False) -> None:
        """
        Add a party to this node's own trust list, and log it.

        Enter:   identity    the party's PublicIdentity
                 by          the local agent deciding to recognize it
                 principal   True to recognize the key of one of this
                             node's authority roots
        Exit:    None; logged as PEER_RECOGNIZED (or PRINCIPAL_RECOGNIZED).
                 A key under an authority root's name is refused unless
                 principal=True: whoever holds that key can sign grants as
                 the root, so binding it must be a deliberate act.
        """
        if identity.name in self.sv.settings.authority_roots and not principal:
            raise TransitionRefused(f"{identity.name} is an authority root here; recognize its "
                                    "key only deliberately (principal=True)")
        self.trust.recognize(identity)
        self.sv._log("PRINCIPAL_RECOGNIZED" if principal else "PEER_RECOGNIZED", by,
                     peer=identity.name, fingerprint=identity.fingerprint)
        self._recheck(by, f"{identity.name} recognized")

    def declare_lineage(self, statement: LineageStatement, by: str) -> None:
        """
        Record a party's signed lineage statement, and log it.

        Enter:   statement   the LineageStatement
                 by          the local agent recording it
        Exit:    None; logged as LINEAGE_RECORDED
        """
        self.trust.add_lineage(statement)
        self.sv._log("LINEAGE_RECORDED", by, subject=statement.subject,
                     lineage=list(statement.lineage), version=statement.version)
        self._recheck(by, f"new lineage statement for {statement.subject}")

    def hold_attestation(self, att: Attestation) -> None:
        """
        Carry a producer's attestation, to publish alongside the evidence.

        Enter:   att   the Attestation
        Exit:    None
        """
        self.attestations[att.evidence_id] = att

    # =======================================================================
    # ACT V, SCENE 3 — SIGN AND PUBLISH THE LOG
    # =======================================================================

    def publish(self) -> LogSegment:
        """
        Sign the current head of this node's log and publish it.

        Enter:   (none)
        Exit:    a LogSegment with every entry, a SignedHead and the
                 attestations this node carries. The entries are deep
                 copies: an AuditEntry is frozen, but its payload is a dict,
                 and a receiver in the same process must not be able to
                 reach into this node's own records through it.
        """
        # PLAYERS IN THIS SCENE
        #   entries   this node's audit entries
        #   rec       the head record to sign

        entries = self.sv.audit.entries()
        rec = {"agent": self.name, "length": len(entries), "head_hash": self.sv.audit.head()}
        return LogSegment(SignedHead(self.name, len(entries), rec["head_hash"],
                                     self.key.sign(rec)),
                          tuple(copy.deepcopy(entries)), tuple(self.attestations.values()))

    # =======================================================================
    # ACT V, SCENE 4 — VERIFY A PEER'S LOG; CATCH FORKS
    # =======================================================================

    def receive(self, segment: LogSegment, by: str) -> bool:
        """
        Take in a peer's published log, if it verifies and extends the one
        seen before.

        Enter:   segment   the peer's LogSegment
                 by        the local agent receiving it
        Exit:    True if accepted. Logs PEER_LOG_VERIFIED, PEER_LOG_REJECTED,
                 PEER_FORK_DETECTED or PEER_MISBEHAVED. A fork (two signed
                 histories that differ), or a validly signed log that no
                 honest Supervisor could have written, marks the peer as an
                 equivocator. Either way, every
                 accepted remote closure is checked again, and any that no
                 longer stands is withdrawn.
        """
        # PLAYERS IN THIS SCENE
        #   peer       the publisher
        #   ok, why    verification result
        #   old        the previously verified segment from this peer, if any
        #   at_old     the new log's hash at the old length

        segment = copy.deepcopy(segment)        # nothing the sender holds is shared
        peer = segment.head.agent
        ok, why = verify_segment(segment, self.trust)
        if ok and peer == self.name:
            ok, why = False, "a node does not receive its own log"
        if ok and peer in self.equivocators:
            ok, why = False, f"{peer} has equivocated; its logs are no longer accepted"
        old = self.peers.get(peer)
        if ok and old is not None:
            # Compare the two signed histories where both reach.
            n = min(segment.head.length, old.head.length)
            at_n_new = segment.entries[n - 1].entry_hash if n else GENESIS
            at_n_old = old.entries[n - 1].entry_hash if n else GENESIS
            if at_n_new == at_n_old and segment.head.length < old.head.length:
                ok, why = False, (f"log is shorter ({segment.head.length}) than one "
                                  f"already seen ({old.head.length}): rollback")
            else:
                if at_n_new != at_n_old:
                    # Both heads carry the peer's valid signature: proof.
                    self.equivocators.add(peer)
                    self.sv._log("PEER_FORK_DETECTED", by, peer=peer,
                                 earlier_head=old.head.record(),
                                 earlier_signature=old.head.signature,
                                 later_head=segment.head.record(),
                                 later_signature=segment.head.signature,
                                 position=old.head.length)
                    self._recheck(by, f"{peer} equivocated (two signed histories)")
                    return False
        if not ok and why.startswith("malformed log") and peer in self.trust.identities \
                and peer != self.name and peer not in self.equivocators:
            # A correctly signed log that no honest Supervisor could have
            # written is proof of misbehavior, like a fork: the peer is no
            # longer relied on.
            self.equivocators.add(peer)
            self.sv._log("PEER_MISBEHAVED", by, peer=peer, reason=why,
                         head=segment.head.record(), head_signature=segment.head.signature)
            self._recheck(by, f"{peer} signed a malformed log")
            return False
        if not ok:
            self.sv._log("PEER_LOG_REJECTED", by, peer=peer, reason=why)
            return False
        self.peers[peer] = segment
        self.sv._log("PEER_LOG_VERIFIED", by, peer=peer, length=segment.head.length,
                     head=segment.head.head_hash, head_signature=segment.head.signature)
        self._recheck(by, f"{peer}'s new log")
        return True

    def _recheck(self, by: str, cause: str) -> None:
        """
        Check every accepted remote closure again; withdraw any that no
        longer stands. A chain can pass through several nodes, so a new log
        from any peer may break any acceptance.

        Enter:   by      the local agent
                 cause   what prompted the check, for the log
        Exit:    None
        """
        # PLAYERS IN THIS SCENE
        #   mid, peer, sid   each accepted mirror and the loop it stands for
        #   ok, reasons      the fresh verification (any error counts as a
        #                    failure: the check fails closed)
        #   rs               the loop in the peer's current log

        for mid in list(self.accepted):
            peer, sid = self.mirrors[mid]
            try:
                ok, reasons, _ = self._verified(peer, sid, expect=self._expected(mid))
                rs = read_signal(self.peers[peer].entries, sid) if peer in self.peers else None
                ok = ok and rs is not None and rs.closure.entry_hash == self.accepted[mid]
            except Exception as exc:       # fail closed: anything odd withdraws
                ok, reasons = False, [f"could not be checked ({type(exc).__name__})"]
            if ok:
                continue
            self._withdraw(mid, by, f"{cause}: the accepted closure of {peer}'s {sid} "
                                    "no longer stands (" + ("; ".join(reasons) or
                                                            "it was closed again") + ")")

    # =======================================================================
    # ACT V, SCENE 5 — A DECISION RESTS ON A PEER'S LOOP
    # =======================================================================

    def depend(self, decision_id: str, peer: str, signal_id: str, by: str) -> str:
        """
        Make a local decision depend on a loop at a peer, through a mirror.

        Enter:   decision_id   a local decision
                 peer          the peer that owns the loop
                 signal_id     the peer's id for it
                 by            the local agent
        Exit:    the mirror's id ("peer/signal"). The mirror is registered
                 (MIRROR_REGISTERED records what it stands for), classified
                 (a nominal remote classification becomes elevated
                 uncertainty: Rule 2 needs evidence this node has not
                 verified) and put under review: an open loop until this
                 node accepts the peer's closure.
                 Raises TransitionRefused if no verified log from the peer
                 registers the signal.
        """
        # PLAYERS IN THIS SCENE
        #   seg     the peer's verified log
        #   rs      the remote signal
        #   mid     the mirror's id
        #   state   the operational state the mirror starts in

        seg = self.peers.get(peer)
        rs = read_signal(seg.entries, signal_id) if seg else None
        if rs is None:
            raise TransitionRefused(f"no verified log from {peer} registers {signal_id!r}")
        mid = f"{peer}{MIRROR_SEPARATOR}{signal_id}"
        if mid in self.mirrors and self.mirrors[mid] != (peer, signal_id):
            raise TransitionRefused(f"{mid} already mirrors {self.mirrors[mid]}")
        if mid not in self.mirrors:
            self.sv.register_signal(mid, SignalType(rs.signal_type),
                                    f"mirror of {peer}'s {signal_id}", peer,
                                    Referent(rs.referent), rs.evaluated_process,
                                    steward=rs.steward, successor=rs.successor,
                                    failure_mode=rs.failure_mode)
            self.sv._log("MIRROR_REGISTERED", by, mirror=mid, peer=peer, signal=signal_id,
                         peer_length=seg.head.length, peer_head=seg.head.head_hash)
            state = (rs.operational_state if rs.operational_state
                     and rs.operational_state not in NOMINAL_STATES
                     else OperationalState.ELEVATED_UNCERTAINTY.value)
            self.sv.classify(mid, OperationalState(state), by)
            self.sv.open_review(mid, by)
            self.mirrors[mid] = (peer, signal_id)
        self.sv.link_signal(decision_id, mid, by)
        return mid

    # =======================================================================
    # ACT V, SCENE 6 — VERIFY A REMOTE LOOP, LINK BY LINK
    # =======================================================================

    def _check_item(self, peer: str, seg: LogSegment, rs: RemoteSignal, eid: str,
                    ev: dict) -> tuple[Optional[Attestation], str]:
        """
        Does one qualifying item of a peer's closure carry a verified origin?

        Enter:   peer, seg   the peer and its verified log
                 rs          the closed remote signal
                 eid, ev     the item's id and its log record
        Exit:    (the Attestation, "ok") or (None, reason)

        Checks: the producer's attestation is in the peer's log segment,
        was given to this peer (relay), matches the log's producer and
        kind, and verifies (signature, hash, checker); the producer's and
        the evaluated process's lineage statements are on record here and
        share nothing.
        """
        # PLAYERS IN THIS SCENE
        #   att            the attestation for this item, if published
        #   ok, why        the attestation check
        #   mine, theirs   the two lineage statements
        #   shared         labels they have in common

        att = next((a for a in seg.attestations if a.evidence_id == eid), None)
        if att is None:
            return None, f"{eid}: no attestation from its producer"
        if att.producer == peer:
            return None, f"{eid}: {peer} attests its own evidence; a relaying node is not an " \
                         "independent producer"
        if att.relay != peer:
            return None, f"{eid}: attestation was given to {att.relay}, not {peer}"
        if att.producer != ev["produced_by"] or att.kind != ev["kind"]:
            return None, f"{eid}: attestation does not match the log (producer or kind)"
        ok, why = verify_attestation(att, self.trust, self.checkers)
        if not ok:
            return None, f"{eid}: {why}"
        mine = self.trust.lineages.get(att.producer)
        theirs = self.trust.lineages.get(rs.evaluated_process)
        if mine is None or theirs is None:
            return None, (f"{eid}: independence cannot be checked: no lineage statement "
                          f"for {att.producer if mine is None else rs.evaluated_process}")
        shared = sorted(set(mine.lineage) & set(theirs.lineage))
        if shared:
            return None, f"{eid}: {att.producer} shares lineage {shared} with {rs.evaluated_process}"
        return att, "ok"

    def _expected(self, mid: str) -> tuple[str, str, str]:
        """
        What a mirror was registered as: the remote loop must still match.

        Enter:   mid   a mirror id
        Exit:    (signal type, referent, evaluated process), as values
        """
        m = self.sv.signals[mid]
        return (m.signal_type.value, m.registrant_referent.value, m.evaluated_process)

    def _verified(self, peer: str, signal_id: str, seen: frozenset = frozenset(),
                  expect: Optional[tuple[str, str, str]] = None, upstream: bool = False
                  ) -> tuple[bool, list[str], Optional[tuple]]:
        """
        Does a peer's log show this loop closed by a chain-sound evidence
        closure whose every link has a verified origin?

        Enter:   peer, signal_id   the remote loop
                 seen              (peer, signal) pairs on the path (cycles)
                 expect            (signal type, referent, evaluated process)
                                   the loop must have: what the mirror was
                                   registered as, so the judgment is about
                                   the loop that was mirrored
                 upstream          True when checking a loop some evidence
                                   depends on: then a loop exited as
                                   superseded with an External Evidence
                                   Source (with a verified origin) also
                                   counts as resolved (Layer 2, Closure
                                   Chain)
        Exit:    (ok, reasons it failed, chosen) where chosen is
                 (evidence id, log record, Attestation, RemoteSignal, owner)
                 for the item that carries the closure, or None when ok is
                 False. For a mirror, the item comes from the owner's log.

        Each link is checked the same way: closed by evidence in its
        owner's verified log; every loop that ANY cited item depends on
        verified in turn ("every cited item is load-bearing"); and at least
        one qualifying item with a verified origin and independent lineage.
        A peer's mirror of a third node's loop is followed to that node's
        own log, so the peer's word never stands in for the
        owner's. A mirror of one of this node's own loops is checked
        against this node's own Supervisor.
        """
        # PLAYERS IN THIS SCENE
        #   key        (peer, signal) for the cycle guard
        #   seg, rs    the peer's verified log and the loop in it
        #   mirrors    the peer's declared mirrors
        #   owner, inner   for a mirror: whose loop it is, and its id there
        #   evidence   the peer's evidence records
        #   reasons    why each cited item's chain, or each candidate, failed
        #   eid, ev    each cited (then each qualifying) item and its record
        #   bad_up     upstream loops of a cited item that do not verify, with why
        #   att, why   the origin check for an item

        key = (peer, signal_id)
        if key in seen:
            return False, [f"{peer}'s {signal_id} is on a dependency cycle"], None
        if peer in self.equivocators:
            return False, [f"{peer} has equivocated"], None
        seg = self.peers.get(peer)
        if seg is None:
            return False, [f"no verified log from {peer}"], None
        rs = read_signal(seg.entries, signal_id)
        if upstream and rs is not None and rs.state == "exited":
            # --- An upstream loop superseded with an EES -------------------
            evidence = _remote_evidence(seg.entries)
            reasons = []
            for eid in _remote_superseded(rs, evidence):
                att, why = self._check_item(peer, seg, rs, eid, evidence[eid])
                if att is not None:
                    return True, [], None
                reasons.append(why)
            return False, reasons or [f"{peer}'s {signal_id} exited without a supersession "
                                      "shown by an External Evidence Source"], None
        if rs is None or rs.state != "closed_evidence" or rs.closure is None:
            return False, [f"{peer}'s log does not show {signal_id} closed by evidence"], None
        if expect is not None and (rs.signal_type, rs.referent, rs.evaluated_process) != expect:
            return False, [f"{peer}'s {signal_id} is not the loop that was mirrored "
                           f"(now {(rs.signal_type, rs.referent, rs.evaluated_process)}, "
                           f"mirrored as {expect})"], None
        evidence = _remote_evidence(seg.entries)
        qualifying = _remote_qualifying(rs, evidence)
        if not qualifying:
            return False, [f"{peer}'s closure of {signal_id} cites no novel, "
                           "independent evidence"], None
        mirrors = _remote_mirrors(seg.entries)
        if signal_id in mirrors:
            owner, inner = mirrors[signal_id]
            if owner == self.name:
                local = self.sv.signals.get(inner)
                ok = local is not None and self.sv.chain_sound(inner)
                return ok, ([] if ok else [f"{peer}'s {signal_id} mirrors this node's "
                                           f"{inner}, which is not chain-sound here"]), None
            ok, reasons, chosen = self._verified(
                owner, inner, seen | {key},
                expect=(rs.signal_type, rs.referent, rs.evaluated_process))
            return ok, [f"via {peer}: {r}" for r in reasons], chosen
        # --- Every cited item is load-bearing: all their upstream loops ---
        reasons: list[str] = []
        for eid in rs.closure.payload.get("cited_evidence", []):
            if eid not in evidence:
                continue
            bad_up = {up: self._verified(peer, up, seen | {key}, upstream=True)
                      for up in evidence[eid]["depends_on"]}
            bad_up = {up: r for up, (ok, r, _) in bad_up.items() if not ok}
            if bad_up:
                reasons.append(f"{eid}: upstream loop(s) at {peer} do not verify: " +
                               "; ".join(f"{up} ({', '.join(r)})" for up, r in bad_up.items()))
        if reasons:
            return False, reasons, None
        # --- One qualifying item with a verified origin carries it ---------
        for eid in qualifying:
            ev = evidence[eid]
            att, why = self._check_item(peer, seg, rs, eid, ev)
            if att is None:
                reasons.append(why)
                continue
            return True, [], (eid, ev, att, rs, peer)
        return False, reasons, None

    # =======================================================================
    # ACT V, SCENE 7 — ACCEPT A REMOTE CLOSURE, THEN CLOSE THE MIRROR
    # =======================================================================

    def accept_remote_closure(self, peer: str, signal_id: str, by: str) -> tuple[bool, str]:
        """
        Accept a peer's closure of a loop, only if every link verifies.

        Enter:   peer, signal_id   the remote loop (already mirrored)
                 by                the local agent accepting
        Exit:    (True, "accepted") or (False, reason). On success the
                 mirror is closed locally by an evidence closure citing the
                 imported, attested evidence, and REMOTE_CLOSURE_ACCEPTED
                 records the peer's closure entry and log head. On failure
                 REMOTE_CLOSURE_REJECTED records why, and the mirror stays
                 open (an attempted closure). See _verified for the checks.
        """
        # PLAYERS IN THIS SCENE
        #   mid            the mirror's id
        #   ok, reasons, chosen   the verification
        #   eid, att, owner       the carrying item, its attestation, and
        #                         whose log it is in
        #   seg, rs        the peer's verified log and the loop in it
        #   local_id       the imported evidence's local id

        mid = f"{peer}{MIRROR_SEPARATOR}{signal_id}"
        if mid not in self.mirrors:
            raise TransitionRefused(f"{mid} is not a mirrored loop here; call depend() first")
        ok, reasons, chosen = self._verified(peer, signal_id, expect=self._expected(mid))
        if ok and chosen is None:
            ok, reasons = False, [f"{peer}'s {signal_id} mirrors this node's own loop; "
                                  "there is nothing to import"]
        if not ok:
            self.sv._log("REMOTE_CLOSURE_REJECTED", by, peer=peer, signal=signal_id,
                         mirror=mid, reasons=reasons)
            return False, "; ".join(reasons)
        # --- Close the mirror locally, citing the imported evidence --------
        eid, _, att, _, owner = chosen
        seg = self.peers[peer]
        rs = read_signal(seg.entries, signal_id)
        local_id = f"{owner}{MIRROR_SEPARATOR}{eid}"
        if local_id not in self.sv.evidence:
            self.sv.add_evidence(local_id, f"{att.kind} attested by {att.producer} "
                                 f"({att.content_hash[:16]})",
                                 f"{owner} evidence {eid}", EvidenceKind(att.kind),
                                 att.producer, by, [mid])
        elif local_id not in self.sv.signals[mid].evidence_ids:
            self.sv.signals[mid].evidence_ids.append(local_id)
        self.sv.attempt_closure(mid, by, Referent(rs.closure.payload.get("closer_referent")
                                                  or rs.referent),
                                [local_id], f"accepted {peer}'s evidence closure of {signal_id}")
        if self.sv.signals[mid].state.value != "closed_evidence":
            # A local rule kept it from being an evidence closure. A
            # rejected acceptance must leave the mirror open, so a closure
            # of any other type is reopened at once.
            if self.sv.signals[mid].state.value.startswith("closed_"):
                self.sv.reopen(mid, by, "remote closure rejected: not an evidence closure here")
            self.sv._log("REMOTE_CLOSURE_REJECTED", by, peer=peer, signal=signal_id,
                         mirror=mid, reasons=["the local closure was not an evidence closure"])
            return False, "the local closure was not an evidence closure"
        self.accepted[mid] = rs.closure.entry_hash
        self.sv._log("REMOTE_CLOSURE_ACCEPTED", by, peer=peer, signal=signal_id, mirror=mid,
                     closure_seq=rs.closure.sequence, closure_hash=rs.closure.entry_hash,
                     peer_length=seg.head.length, peer_head=seg.head.head_hash,
                     peer_head_signature=seg.head.signature,
                     evidence=eid, evidence_owner=owner, producer=att.producer)
        return True, "accepted"

    # =======================================================================
    # ACT V, SCENE 8 — AUTHORITY FROM ANOTHER NODE
    # =======================================================================

    def receive_grant(self, g: SignedGrant, by: str) -> None:
        """
        Take in a signed grant from another party.

        Enter:   g    the SignedGrant
                 by   the local agent recording it
        Exit:    None. The grant is recorded in the local Supervisor
                 (AUTHORITY_GRANTED, by the grantor) only if: it is
                 addressed to this node; its grantor is recognized here and
                 signed it; and the grantor holds that power, delegably,
                 over that scope here (Supervisor.grant). Otherwise
                 GRANT_REJECTED or GRANT_REFUSED is logged and
                 TransitionRefused raised.

        A signature proves who granted; it cannot create a power the
        grantor lacks. Delegation passes on only what was held.
        """
        # PLAYERS IN THIS SCENE
        #   who   the grantor's recognized identity
        #   why   the reason for a rejection

        who = self.trust.identities.get(g.grantor)
        why = None
        if g.node != self.name:
            why = f"grant is addressed to {g.node}, not {self.name}"
        elif g.ref in self.grant_refs:
            why = ("this exact grant was already received" +
                   (" and has been revoked" if self.grant_refs[g.ref] in self.sv.revoked else "")
                   + "; a replay is never a new grant")
        elif who is None:
            why = f"grantor {g.grantor!r} is not recognized"
        elif not who.verify(g.record(), g.signature):
            why = f"grant signature by {g.grantor!r} is invalid"
        if why:
            self.sv._log("GRANT_REJECTED", by, grantor=g.grantor, grantee=g.grantee,
                         power=g.power, scope=g.scope, reason=why)
            raise TransitionRefused(why)
        local = self.sv.grant(g.grantee, Power(g.power), g.scope, by=g.grantor,
                              delegable=g.delegable, expires_at=g.expires_at)
        self.grant_refs[g.ref] = local.grant_id

    def receive_revocation(self, r: SignedRevocation, by: str) -> list[str]:
        """
        Take in a signed revocation.

        Enter:   r    the SignedRevocation
                 by   the local agent recording it
        Exit:    the local grant ids it voids. Logs REVOCATION_REJECTED and
                 raises TransitionRefused if it is addressed elsewhere,
                 names a grant this node never received, or is not signed
                 by a recognized revoker. Whether the revoker may revoke
                 that grant is Supervisor.revoke's test.
        """
        # PLAYERS IN THIS SCENE
        #   who   the revoker's recognized identity
        #   why   the reason for a rejection

        who = self.trust.identities.get(r.revoker)
        why = None
        if r.node != self.name:
            why = f"revocation is addressed to {r.node}, not {self.name}"
        elif r.grant_ref not in self.grant_refs:
            why = "revocation names a grant this node never received"
        elif who is None:
            why = f"revoker {r.revoker!r} is not recognized"
        elif not who.verify(r.record(), r.signature):
            why = f"revocation signature by {r.revoker!r} is invalid"
        if why:
            self.sv._log("REVOCATION_REJECTED", by, revoker=r.revoker, reason=why)
            raise TransitionRefused(why)
        return self.sv.revoke(self.grant_refs[r.grant_ref], by=r.revoker, reason=r.reason)

    # =======================================================================
    # ACT V, SCENE 9 — A PEER'S CLOSURE NO LONGER STANDS
    # =======================================================================

    def _withdraw(self, mid: str, by: str, reason: str) -> None:
        """
        Reopen a mirror whose accepted peer closure no longer stands.

        Enter:   mid      the mirror
                 by       the local agent
                 reason   why
        Exit:    None; the mirror is back under review (or escalated, if a
                 review names it) and REMOTE_CLOSURE_WITHDRAWN is logged
        """
        self.accepted.pop(mid, None)
        if self.sv.signals[mid].state.value.startswith("closed_"):
            self.sv.reopen(mid, by, reason)
        self.sv._log("REMOTE_CLOSURE_WITHDRAWN", by, mirror=mid, reason=reason)


# ###########################################################################
# ACT VI — THE AUDITOR
# ###########################################################################

@dataclass
class AuditReport:
    """
    The outcome of audit_federation().

    Fields:
      ok         True if no problem was found
      problems   each problem found, as text
      checked    how many cross-references were checked
    """
    ok: bool
    problems: list[str] = field(default_factory=list)
    checked: int = 0


def _resolver(logs: dict[str, LogSegment], lengths: dict[str, int]
              ) -> Callable[[str], Optional[list[AuditEntry]]]:
    """
    A resolve function for _remote_sound over published logs, each cut at
    the length one node had verified.

    Enter:   logs      node name -> its published segment
             lengths   node name -> the length to cut at
    Exit:    node name -> its entries up to that length (None if unknown)
    """
    def resolve(node: str) -> Optional[list[AuditEntry]]:
        if node not in logs or node not in lengths:
            return None
        return list(logs[node].entries[:lengths[node]])
    return resolve


def audit_federation(segments: Iterable[LogSegment], trust: TrustList) -> AuditReport:
    """
    Check a federation from the outside, given the nodes' published logs.

    Enter:   segments   published LogSegments (one or more per node)
             trust      the auditor's own TrustList
    Exit:    an AuditReport

    Checks:
      - every log verifies (recognized signer, valid signature, intact
        chain ending at the signed head, well-formed entries);
      - two segments from one node agree wherever both reach; if not, the
        node signed two histories (equivocation);
      - every PEER_LOG_VERIFIED and REMOTE_CLOSURE_ACCEPTED entry carries
        the peer's signature on the head it cites. No valid signature: the
        CITING node is at fault (it recorded a head the peer never signed).
        A valid signature on a head that is not on the peer's published
        log: the PEER signed a different history for that node
        (equivocation, with proof);
      - every accepted remote closure points at an entry that exists in the
        peer's log, has the cited hash, closes the cited signal by
        evidence, and was chain-sound in the log as it stood at the cited
        head. A mirror in that chain is followed to its owner's published
        log, cut at the length the accepting node had verified (or, for
        the accepting node's own loops, at the acceptance), so a later
        reopen there is not mistaken for a bad acceptance;
      - a malformed citation is reported, never raised.

    The auditor checks structure, not origins: it does not re-verify
    attestations or lineage, which each accepting node did.
    """
    # PLAYERS IN THIS SCENE
    #   report     the AuditReport being built
    #   logs       node name -> its longest verified segment
    #   seg, ok, why   each segment and its verification
    #   e, p       each entry and its payload
    #   peer_seg   the cited peer's published log
    #   n, head, sig   the cited length, head and head signature
    #   prefix     the peer's entries up to the cited length
    #   seen_len   per node: peer -> the length it had verified so far

    report = AuditReport(True)
    logs: dict[str, LogSegment] = {}

    # --- Every log, and every pair of logs from one node -------------------
    for seg in segments:
        ok, why = verify_segment(seg, trust)
        if not ok:
            report.problems.append(f"{seg.head.agent}: {why}")
            continue
        other = logs.get(seg.head.agent)
        if other is not None:
            n = min(len(seg.entries), len(other.entries))
            if n and seg.entries[n - 1].entry_hash != other.entries[n - 1].entry_hash:
                report.problems.append(f"{seg.head.agent} published two different signed "
                                       "histories (equivocation)")
                continue
            if len(other.entries) >= len(seg.entries):
                continue
        logs[seg.head.agent] = seg

    # --- Every citation of another node's log -----------------------------
    for name, seg in logs.items():
        seen_len: dict[str, int] = {}
        for e in seg.entries:
            if e.event not in ("PEER_LOG_VERIFIED", "REMOTE_CLOSURE_ACCEPTED"):
                continue
            report.checked += 1
            try:
                problem = _audit_citation(name, e, logs, trust, seen_len)
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                problem = f"malformed citation ({type(exc).__name__})"
            if problem:
                report.problems.append(f"{name} #{e.sequence}: {problem}")
    report.ok = not report.problems
    return report


def _audit_citation(name: str, e: AuditEntry, logs: dict[str, LogSegment], trust: TrustList,
                    seen_len: dict[str, int]) -> Optional[str]:
    """
    Check one PEER_LOG_VERIFIED or REMOTE_CLOSURE_ACCEPTED entry.

    Enter:   name       the citing node
             e          the entry
             logs       node name -> its published segment
             trust      the auditor's TrustList
             seen_len   peer -> length the citing node had verified so far
                        (updated here for PEER_LOG_VERIFIED)
    Exit:    the problem, as text, or None
    """
    # PLAYERS IN THIS SCENE
    #   p                the payload
    #   verified         True for PEER_LOG_VERIFIED
    #   peer, n, head, sig   what it cites
    #   who              the peer's identity, as the auditor knows it
    #   peer_seg, at_n   the peer's published log and its hash at n
    #   seq, prefix      the cited closure entry, and the log up to n

    p = e.payload
    verified = e.event == "PEER_LOG_VERIFIED"
    peer = p["peer"]
    n = int(p["length"] if verified else p["peer_length"])
    head = p["head"] if verified else p["peer_head"]
    sig = p.get("head_signature" if verified else "peer_head_signature")
    if verified:
        seen_len[peer] = n
    who = trust.identities.get(peer)
    if who is None or not isinstance(sig, str) or not who.verify(
            {"agent": peer, "length": n, "head_hash": head}, sig):
        return f"cites a head of {peer} that {peer} never signed"
    peer_seg = logs.get(peer)
    if peer_seg is None:
        return f"no verified log from {peer}"
    if n > len(peer_seg.entries) or n < 0:
        return f"{peer} signed a history of length {n} for {name} that it has not published"
    at_n = peer_seg.entries[n - 1].entry_hash if n else GENESIS
    if at_n != head:
        return f"{peer} signed a different history for {name} (equivocation; both heads signed)"
    if verified:
        return None
    seq = p["closure_seq"]
    prefix = list(peer_seg.entries[:n])
    if not isinstance(seq, int) or not 0 <= seq < n or prefix[seq].entry_hash != p["closure_hash"]:
        return f"cited closure entry not in {peer}'s log"
    lengths = dict(seen_len, **{name: e.sequence})
    if not _remote_sound(prefix, p["signal"], peer, _resolver(logs, lengths))[0]:
        return f"{peer}'s log did not show {p['signal']} chain-sound when accepted"
    return None

# EXEUNT — end of file.
