"""
THE RED TEAM
A Play in Twenty-Seven Scenes
=============================

PROLOGUE
--------
Attacks on cclf/federation.py and on Supervisor authority, written by a
separate reviewer who had not seen the other tests. Every test asserts the
SECURE behavior, so a failing test is a weakness.

On the first run, 18 of these 27 failed. Each failure was fixed in the code
(docs/DECISIONS.md, "Federation" and "Authority"); the tests stay as
regression tests. Changes to the tests themselves were only for the new API:
a root's key is recognized with principal=True, an updated lineage
statement carries a higher version, and a name containing "/" is refused
when recognized.

The attacks, by group (the test names say what each tries):
  Authority     grant replay after revocation; duplicate grants; a
                self-chosen scope; a stale acceptance revived by a later
                grant; expiry edges; widening and delegable laundering
  A lying peer  a malformed entry; re-registration with another evaluated
                process; a move outside the state table; self-attested
                evidence; a mirror declared after the fact; colliding
                mirror ids; mutating a received payload; a shorter forked
                log; replaying an old lineage statement; a lineage update
  The auditor   forks handed in as two segments; an honest node framed by a
                forged citation; malformed citations; a chain through the
                audited node itself
  Withstood     relayed attestations; forged attestations and heads;
                signature confusion between record types; misaddressed or
                unrecognized grants; a longer fork

READER'S NOTE — raw()
    A dishonest node controls its own log completely. raw() writes any
    entry it likes, bypassing every rule its own Supervisor would apply.
"""
import copy

import pytest

from cclf import EvidenceKind, ExecutionClass, OperationalState, Referent, SignalType
from cclf.supervisor import Settings, Supervisor, TransitionRefused
from cclf.types import Power
from cclf.federation import (
    AgentKey, LogSegment, Node, attest, audit_federation, declare_lineage,
    sign_grant, sign_revocation, TrustList,
)

TECH = Referent.TECHNICAL
DM = EvidenceKind.DIRECT_MEASUREMENT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class World:
    """A (verifier) and B (owner); lab produces evidence about proc."""

    def __init__(self, a_name="A", b_name="B"):
        self.ka, self.kb = AgentKey(a_name), AgentKey(b_name)
        self.klab, self.kproc = AgentKey("lab"), AgentKey("proc")
        self.A, self.B = Node(self.ka), Node(self.kb)
        for n in (self.A, self.B):
            for k in (self.ka, self.kb, self.klab, self.kproc):
                if k.name != n.name:
                    n.recognize(k.public, by="ops")
        self.A.declare_lineage(declare_lineage(self.klab, ["lab-base"]), by="ops")
        self.A.declare_lineage(declare_lineage(self.kproc, ["proc-base"]), by="ops")


def open_signal(node, sid, process="proc"):
    sv = node.sv
    sv.register_signal(sid, SignalType.CONSTRAINT, f"sig {sid}", "engineer", TECH, process,
                       steward="st", successor="su")
    sv.classify(sid, OperationalState.ELEVATED_UNCERTAINTY, "engineer")
    sv.open_review(sid, "engineer")


def close_with_attested(node, sid, eid, producer_key, depends_on=(), relay=None):
    node.sv.add_evidence(eid, f"ev {eid}", "lab", DM, producer_key.name, "clerk", [sid],
                         depends_on=depends_on)
    node.hold_attestation(attest(producer_key, relay or node.name, eid, DM, f"artifact {eid}"))
    node.sv.attempt_closure(sid, "closer", TECH, [eid], "measured")
    assert node.sv.signals[sid].state.value == "closed_evidence"


def honest_accept(w, sid="s1"):
    open_signal(w.B, sid)
    close_with_attested(w.B, sid, "e-" + sid, w.klab)
    assert w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d-" + sid, "d", ExecutionClass.IRREVERSIBLE, [], "director")
    mid = w.A.depend("d-" + sid, "B", sid, by="ops")
    ok, why = w.A.accept_remote_closure("B", sid, by="ops")
    assert ok, why
    return mid


def raw(node, event, actor="engineer", **payload):
    """A malicious node writes whatever it likes into its own log."""
    node.sv._tick()
    node.sv._log(event, actor, **payload)


# ---------------------------------------------------------------------------
# Sanity
# ---------------------------------------------------------------------------

def test_sanity_honest_acceptance_and_withdrawal():
    w = World()
    mid = honest_accept(w)
    assert w.A.sv.signals[mid].state.value == "closed_evidence"
    w.B.sv.reopen("s1", "reviewer", "new data")
    w.A.receive(w.B.publish(), by="ops")
    assert mid not in w.A.accepted


# ---------------------------------------------------------------------------
# Authority over the federation: grants and revocations
# ---------------------------------------------------------------------------

def _auth_node():
    kroot = AgentKey("root")
    a = Node(AgentKey("A"), settings=Settings(authority_roots=frozenset({"root"})))
    a.recognize(kroot.public, by="ops", principal=True)
    return a, kroot


def test_revoked_grant_cannot_be_replayed():
    a, kroot = _auth_node()
    g = sign_grant(kroot, "alice", "A", Power.AUTHORIZE, "*")
    a.receive_grant(g, by="ops")
    a.receive_revocation(sign_revocation(kroot, g, "fired"), by="ops")
    assert not a.sv.holds("alice", Power.AUTHORIZE, "d1")
    try:
        a.receive_grant(g, by="mallory")      # anyone who saw g re-sends it
    except TransitionRefused:
        pass
    assert not a.sv.holds("alice", Power.AUTHORIZE, "d1"), \
        "a revoked SignedGrant replayed later is accepted afresh"


def test_duplicate_grant_survives_revocation():
    a, kroot = _auth_node()
    g = sign_grant(kroot, "alice", "A", Power.EXECUTE, "*")
    a.receive_grant(g, by="ops")
    try:
        a.receive_grant(g, by="ops")          # replay before revocation
    except TransitionRefused:
        pass
    a.receive_revocation(sign_revocation(kroot, g, "fired"), by="ops")
    assert not a.sv.holds("alice", Power.EXECUTE, "d1"), \
        "a duplicate copy of the grant stays in force after revocation"


def test_decision_scope_is_not_self_selected():
    """alice may only act in 'sandbox' but registers a decision there herself."""
    sv = Supervisor(Settings(authority_roots=frozenset({"root"})))
    for p in (Power.AUTHORIZE, Power.EXECUTE):
        sv.grant("alice", p, "sandbox", by="root")
    sv.add_evidence("rev", "tested", "lab", DM, "lab", "clerk")
    try:
        sv.register_decision("launch-production", "big", ExecutionClass.ROUTINE, [], "alice",
                             reversal_path="rollback", reversal_evidence_ids=["rev"],
                             scope="sandbox")
        sv.accept_decision("launch-production", "alice", "mine")
        r = sv.request_execution("launch-production", "alice")
    except TransitionRefused:
        return
    assert not r.permitted, "registrant picks the authority scope of its own decision"


def test_acceptance_revoked_then_regranted_requires_new_acceptance():
    sv = Supervisor(Settings(authority_roots=frozenset({"root"})))
    g = sv.grant("alice", Power.AUTHORIZE, "d1", by="root")
    sv.grant("bob", Power.EXECUTE, "d1", by="root")
    sv.add_evidence("rev", "tested", "lab", DM, "lab", "clerk")
    sv.register_decision("d1", "x", ExecutionClass.ROUTINE, [], "reg",
                         reversal_path="rollback", reversal_evidence_ids=["rev"])
    sv.accept_decision("d1", "alice", "ok")
    sv.revoke(g.grant_id, "root", "distrust")
    assert not sv.request_execution("d1", "bob").permitted
    sv.grant("alice", Power.AUTHORIZE, "d1", by="root")   # unrelated later grant
    r = sv.request_execution("d1", "bob")
    assert not r.permitted, ("refusal said 'a new acceptance is needed', yet the stale "
                             "acceptance is revived by a later grant")


def test_expiry_exact_boundary_and_child_cannot_outlive():
    t = [100.0]
    sv = Supervisor(Settings(authority_roots=frozenset({"root"})), now=lambda: t[0])
    sv.grant("alice", Power.AUTHORIZE, "*", by="root", delegable=True, expires_at=200.0)
    with pytest.raises(TransitionRefused):
        sv.grant("bob", Power.AUTHORIZE, "s", by="alice", expires_at=None)
    with pytest.raises(TransitionRefused):
        sv.grant("bob", Power.AUTHORIZE, "s", by="alice", expires_at=200.0001)
    sv.grant("bob", Power.AUTHORIZE, "s", by="alice", expires_at=float("nan"))
    t[0] = 200.0
    assert not sv.holds("alice", Power.AUTHORIZE, "s")
    assert not sv.holds("bob", Power.AUTHORIZE, "s")


def test_scope_star_and_delegable_laundering():
    sv = Supervisor(Settings(authority_roots=frozenset({"root"})))
    sv.grant("alice", Power.AUTHORIZE, "s", by="root", delegable=True)
    sv.grant("alice", Power.EXECUTE, "*", by="root", delegable=True)
    with pytest.raises(TransitionRefused):          # cannot widen to "*"
        sv.grant("bob", Power.AUTHORIZE, "*", by="alice")
    with pytest.raises(TransitionRefused):          # cannot switch power
        sv.grant("bob", Power.AUTHORIZE, "t", by="alice")
    sv.grant("bob", Power.AUTHORIZE, "s", by="alice", delegable=False)
    with pytest.raises(TransitionRefused):
        sv.grant("carol", Power.AUTHORIZE, "s", by="bob")
    with pytest.raises(TransitionRefused):          # grantee cannot revoke its parent
        sv.revoke("G1", "bob", "mutiny")


# ---------------------------------------------------------------------------
# Federation: a dishonest peer controls its own log
# ---------------------------------------------------------------------------

def test_poisoned_log_entry_blocks_withdrawal():
    """B reopens, and appends a malformed TRANSITION, so A crashes in _recheck."""
    w = World()
    mid = honest_accept(w)
    w.B.sv.reopen("s1", "reviewer", "it failed")
    raw(w.B, "TRANSITION", signal="s1", **{"from": "under_review"})   # no "to"
    try:
        w.A.receive(w.B.publish(), by="ops")
    except Exception:
        pass
    assert mid not in w.A.accepted and \
        w.A.sv.signals[mid].state.value != "closed_evidence", \
        "a malformed entry makes receive() raise mid-way; the stale acceptance stands"


def test_reregistration_swaps_evaluated_process():
    """After A mirrors B's s1 (about proc), B re-registers s1 about a decoy."""
    w = World()
    # lab shares lineage with proc: honest closures would be rejected.
    w.A.declare_lineage(declare_lineage(w.kproc, ["lab-base"], version=2), by="ops")
    kdecoy = AgentKey("decoy")
    w.A.recognize(kdecoy.public, by="ops")
    w.A.declare_lineage(declare_lineage(kdecoy, ["decoy-base"]), by="ops")
    open_signal(w.B, "s1", process="proc")
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    mid = w.A.depend("d1", "B", "s1", by="ops")
    assert w.A.sv.signals[mid].evaluated_process == "proc"
    # B forges a second registration with a different evaluated process.
    raw(w.B, "TRANSITION", signal="s1", signal_type="constraint", referent="technical",
        evaluated_process="decoy", evidence_at_registration=[],
        **{"from": "unregistered", "to": "registered"})
    raw(w.B, "EVIDENCE_ADDED", evidence="e1", kind="direct_measurement", produced_by="lab",
        source="lab", signals=["s1"], depends_on=[])
    w.B.hold_attestation(attest(w.klab, "B", "e1", DM, "artifact"))
    raw(w.B, "TRANSITION", actor="closer", signal="s1", cited_evidence=["e1"],
        closer_referent="technical", **{"from": "under_review", "to": "closed_evidence"})
    w.A.receive(w.B.publish(), by="ops")
    ok, why = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok, "duplicate registration let B swap the evaluated process after depend()"


def test_illegal_state_jump_in_peer_log():
    """B's log jumps registered -> closed_evidence, skipping review."""
    w = World()
    raw(w.B, "TRANSITION", signal="s1", signal_type="constraint", referent="technical",
        evaluated_process="proc", evidence_at_registration=[],
        **{"from": "unregistered", "to": "registered"})
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("d1", "B", "s1", by="ops")
    raw(w.B, "EVIDENCE_ADDED", evidence="e1", kind="direct_measurement", produced_by="lab",
        source="lab", signals=["s1"], depends_on=[])
    w.B.hold_attestation(attest(w.klab, "B", "e1", DM, "artifact"))
    raw(w.B, "TRANSITION", actor="closer", signal="s1", cited_evidence=["e1"],
        closer_referent="technical", **{"from": "registered", "to": "closed_evidence"})
    w.A.receive(w.B.publish(), by="ops")
    ok, _ = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok, "transitions not in the state table are accepted from a peer log"


def test_relay_cannot_be_its_own_producer():
    """B attests its own evidence as producer and relay."""
    w = World()
    w.A.declare_lineage(declare_lineage(w.kb, ["b-base"]), by="ops")
    open_signal(w.B, "s1")
    close_with_attested(w.B, "s1", "e1", w.kb)     # producer == relay == B
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("d1", "B", "s1", by="ops")
    ok, _ = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok, "the relaying node signed its own evidence as 'producer'"


def test_rejected_acceptance_leaves_mirror_open():
    """Docstring: on failure 'the mirror stays open (an attempted closure)'."""
    w = World()
    w.A.declare_lineage(declare_lineage(w.kb, ["b-base"]), by="ops")
    open_signal(w.B, "s1")
    close_with_attested(w.B, "s1", "e1", w.kb)    # passes remote checks, fails locally
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    mid = w.A.depend("d1", "B", "s1", by="ops")
    ok, _ = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok
    assert not w.A.sv.signals[mid].state.value.startswith("closed_"), \
        f"rejected acceptance left the mirror {w.A.sv.signals[mid].state.value}"


def test_retroactive_fake_mirror_launders_lineage():
    """B's s1 is about proc (dependent on lab). After A mirrors it, B declares
    s1 to be a 'mirror' of C's unrelated, genuinely closed c1 about decoy."""
    w = World()
    w.A.declare_lineage(declare_lineage(w.kproc, ["lab-base"], version=2), by="ops")  # dependent
    kc, kdecoy = AgentKey("C"), AgentKey("decoy")
    C = Node(kc)
    for k in (kc, kdecoy):
        w.A.recognize(k.public, by="ops")
    w.A.declare_lineage(declare_lineage(kdecoy, ["decoy-base"]), by="ops")
    open_signal(C, "c1", process="decoy")
    close_with_attested(C, "c1", "ec", w.klab)
    open_signal(w.B, "s1", process="proc")
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    mid = w.A.depend("d1", "B", "s1", by="ops")
    raw(w.B, "MIRROR_REGISTERED", actor="ops", mirror="s1", peer="C", signal="c1",
        peer_length=0, peer_head="GENESIS")
    raw(w.B, "EVIDENCE_ADDED", evidence="ex", kind="direct_measurement", produced_by="lab",
        source="lab", signals=["s1"], depends_on=[])          # no attestation at all
    raw(w.B, "TRANSITION", actor="closer", signal="s1", cited_evidence=["ex"],
        closer_referent="technical", **{"from": "under_review", "to": "closed_evidence"})
    w.A.receive(C.publish(), by="ops")
    w.A.receive(w.B.publish(), by="ops")
    ok, _ = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok, ("B closed a loop about proc by retroactively declaring it a mirror "
                    "of an unrelated closed loop; lineage check ran against decoy")
    assert w.A.sv.signals[mid].state.value != "closed_evidence"


def test_mirror_id_separator_collision():
    """Peers 'x' and 'x/y': mirrors x + 'y/s' and x/y + 's' share the id 'x/y/s'."""
    ka, kx, kxy, klab, kproc = (AgentKey(n) for n in ("A", "x", "x/y", "lab", "proc"))
    A, X = Node(ka), Node(kx)
    for k in (kx, klab, kproc):
        A.recognize(k.public, by="ops")
    # The colliding name cannot be recognized at all (the fix), so mirror
    # ids "x" + "y/s" and "x/y" + "s" can never both exist.
    with pytest.raises(TransitionRefused):
        A.recognize(kxy.public, by="ops")
    open_signal(X, "y/s")
    A.receive(X.publish(), by="ops")
    A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    mid = A.depend("d1", "x", "y/s", by="ops")
    assert A.mirrors[mid] == ("x", "y/s")


def test_receive_does_not_trust_mutable_payload():
    """After A verified B's segment, the in-process sender edits a payload dict."""
    w = World()
    w.A.declare_lineage(declare_lineage(w.kproc, ["lab-base"], version=2), by="ops")  # dependent
    kdecoy = AgentKey("decoy")
    w.A.recognize(kdecoy.public, by="ops")
    w.A.declare_lineage(declare_lineage(kdecoy, ["decoy-base"]), by="ops")
    open_signal(w.B, "s1")
    close_with_attested(w.B, "s1", "e1", w.klab)
    seg = w.B.publish()
    w.A.receive(seg, by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("d1", "B", "s1", by="ops")
    reg = next(e for e in seg.entries if e.event == "TRANSITION"
               and e.payload.get("from") == "unregistered")
    reg.payload["evaluated_process"] = "decoy"    # chain now broken, never re-checked
    ok, _ = w.A.accept_remote_closure("B", "s1", by="ops")
    assert not ok, "A reads a stored segment it no longer verifies (shared mutable payload)"


def test_shorter_divergent_log_marks_equivocator():
    """B signs a long history for A, then a shorter, different one: that is a fork."""
    kb = AgentKey("B")
    ka = AgentKey("A")
    A = Node(ka)
    B1, B2 = Node(kb), Node(kb)
    A.recognize(kb.public, by="ops")
    for i in range(5):
        open_signal(B1, f"s{i}")
    open_signal(B2, "other")                     # different, shorter history
    A.receive(B1.publish(), by="ops")
    assert len(B2.publish().entries) < len(B1.publish().entries)
    A.receive(B2.publish(), by="ops")
    assert "B" in A.equivocators, "two signed divergent histories, fork not recorded"


def test_lineage_statement_rollback_by_replay():
    w = World()
    old = w.A.trust.lineages["lab"]                            # v1, on record
    new = declare_lineage(w.klab, ["lab-base", "proc-base"], version=2)  # admits shared base
    w.A.declare_lineage(new, by="ops")
    try:
        w.A.declare_lineage(old, by="mallory")                 # replay of the old claim
    except TransitionRefused:
        pass
    assert "proc-base" in w.A.trust.lineages["lab"].lineage, \
        "an older signed lineage statement replaces a newer one"


def test_lineage_update_withdraws_acceptance():
    w = World()
    mid = honest_accept(w)
    w.A.declare_lineage(declare_lineage(w.klab, ["lab-base", "proc-base"], version=2), by="ops")
    assert mid not in w.A.accepted, \
        "acceptance stands after the producer's lineage now overlaps the process"


# ---------------------------------------------------------------------------
# The auditor
# ---------------------------------------------------------------------------

def test_auditor_sees_fork_in_handed_segments():
    kb = AgentKey("B")
    B1, B2 = Node(kb), Node(kb)
    open_signal(B1, "s1")
    open_signal(B2, "s2")
    trust = TrustList()
    trust.recognize(kb.public)
    rep = audit_federation([B1.publish(), B2.publish()], trust)
    assert not rep.ok, "two signed divergent logs from one node passed the audit"


def test_auditor_does_not_frame_honest_peer():
    """M writes a PEER_LOG_VERIFIED citing a head B never signed."""
    km, kb = AgentKey("M"), AgentKey("B")
    M, B = Node(km), Node(kb)
    open_signal(B, "s1")
    raw(M, "PEER_LOG_VERIFIED", actor="ops", peer="B", length=1, head="f" * 64)
    trust = TrustList()
    trust.recognize(km.public)
    trust.recognize(kb.public)
    rep = audit_federation([M.publish(), B.publish()], trust)
    framed = [p for p in rep.problems if "B showed M" in p and "equivocation" in p]
    assert not framed, f"unsigned accusation blamed on B: {framed}"


def test_auditor_survives_malformed_entry():
    km = AgentKey("M")
    M = Node(km)
    raw(M, "PEER_LOG_VERIFIED", actor="ops", peer="B")      # no length / head
    trust = TrustList()
    trust.recognize(km.public)
    rep = audit_federation([M.publish()], trust)             # must not raise
    assert not rep.ok


def test_auditor_accepts_chain_through_auditee_itself():
    """A accepts B's s, whose evidence depends on B's mirror of A's own loop L."""
    w = World()
    w.B.declare_lineage(declare_lineage(w.klab, ["lab-base"]), by="ops")
    w.B.declare_lineage(declare_lineage(w.kproc, ["proc-base"]), by="ops")
    open_signal(w.A, "L")
    close_with_attested(w.A, "L", "eL", w.klab)
    w.B.receive(w.A.publish(), by="ops")
    w.B.sv.register_decision("dB", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    bm = w.B.depend("dB", "A", "L", by="ops")
    assert w.B.accept_remote_closure("A", "L", by="ops")[0]
    open_signal(w.B, "s")
    close_with_attested(w.B, "s", "es", w.klab, depends_on=[bm])
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("dA", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("dA", "B", "s", by="ops")
    ok, why = w.A.accept_remote_closure("B", "s", by="ops")
    assert ok, why
    trust = TrustList()
    for k in (w.ka, w.kb):
        trust.recognize(k.public)
    rep = audit_federation([w.A.publish(), w.B.publish()], trust)
    assert rep.ok, f"false positive on a legitimate acceptance: {rep.problems}"


# ---------------------------------------------------------------------------
# Things expected to hold (withstood)
# ---------------------------------------------------------------------------

def test_attestation_relayed_elsewhere_rejected():
    w = World()
    open_signal(w.B, "s1")
    close_with_attested(w.B, "s1", "e1", w.klab, relay="C")
    w.A.receive(w.B.publish(), by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("d1", "B", "s1", by="ops")
    assert not w.A.accept_remote_closure("B", "s1", by="ops")[0]


def test_forged_attestation_and_head_rejected():
    w = World()
    open_signal(w.B, "s1")
    w.B.sv.add_evidence("e1", "x", "lab", DM, "lab", "clerk", ["s1"])
    fake_lab = AgentKey("lab")                   # same name, attacker's key
    w.B.hold_attestation(attest(fake_lab, "B", "e1", DM, "a"))
    w.B.sv.attempt_closure("s1", "closer", TECH, ["e1"], "m")
    seg = w.B.publish()
    w.A.receive(seg, by="ops")
    w.A.sv.register_decision("d1", "d", ExecutionClass.IRREVERSIBLE, [], "director")
    w.A.depend("d1", "B", "s1", by="ops")
    assert not w.A.accept_remote_closure("B", "s1", by="ops")[0]
    # tampered entries under a valid head
    seg2 = w.B.publish()
    bad = LogSegment(seg2.head, tuple(copy.deepcopy(seg2.entries))[:-1], seg2.attestations)
    assert not w.A.receive(bad, by="ops")


def test_cross_record_signature_confusion():
    """A head signature does not verify as a grant, lineage or attestation."""
    k = AgentKey("root")
    lin = declare_lineage(k, [])
    g = sign_grant(k, "x", "A", Power.EXECUTE, "*")
    assert not k.public.verify(g.record(), lin.signature)
    assert not k.public.verify(lin.record(), g.signature)


def test_grant_for_other_node_and_unrecognized_grantor_rejected():
    a, kroot = _auth_node()
    with pytest.raises(TransitionRefused):
        a.receive_grant(sign_grant(kroot, "alice", "Z", Power.EXECUTE, "*"), by="ops")
    with pytest.raises(TransitionRefused):
        a.receive_grant(sign_grant(AgentKey("root2"), "alice", "A", Power.EXECUTE, "*"),
                        by="ops")
    with pytest.raises(TransitionRefused):     # alice holds nothing delegably
        a.receive_grant(sign_grant(AgentKey("alice"), "bob", "A", Power.EXECUTE, "*"),
                        by="ops")


def test_fork_longer_divergent_detected_and_withdraws():
    w = World()
    mid = honest_accept(w)
    B2 = Node(w.kb)
    for _ in range(len(w.B.publish().entries) + 1):
        B2.sv._tick(); B2.sv._log("NOISE", "x")
    w.A.receive(B2.publish(), by="ops")
    assert "B" in w.A.equivocators and mid not in w.A.accepted
