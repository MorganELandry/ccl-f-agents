"""
THE FEDERATION, TESTED
A Play in Twenty-Six Scenes
===========================

PROLOGUE
--------
Tests for cclf/federation.py: commitment governance across agents that
share no central authority. Each node keeps its own Supervisor, its own
signed log and its own trust list. The draft's rules these tests hold the
federation to:

  Attempted Closure (Key Definitions): "A closure signal transmitted across
    an autonomy boundary ... does not constitute loop resolution." A
    peer's closure leaves the local mirror open until this node accepts it.
  Local Closure (Key Definitions): the receiving node closes the loop
    itself, under its own rules.
  External Evidence Source (Layer 2): evidence whose "errors cannot share
    a cause with the errors of the process making the claim"; its producer
    is not the claimant (the closing agent) nor the process the claim
    evaluates. Across nodes this is checked by a producer's signed
    attestation and signed lineage statements that share nothing.
  Closure Chain (Layer 2): a closure is only as sound as every loop that
    any cited item rests on, now including loops at other nodes; an
    upstream loop superseded with an EES counts as resolved.
  Audit Trail: append-only. Across nodes, a signed head commits a node to
    its whole history, so two different signed histories are proof of
    equivocation.

The world in every scene: three nodes (bell, acme, cobalt), an
independent lab that produces measurements, and a design model ("the
process under evaluation") whose output raised the concern.

THE PLAYBILL
    Prelude   World, world() (fixture), close_at() (helper)
    Scene 1   test_remote_closure_leaves_the_mirror_open_until_accepted
    Scene 2   test_accepted_closure_lets_the_local_gate_pass
    Scene 3   test_relayer_cannot_forge_the_producers_attestation
    Scene 4   test_attestation_cannot_be_replayed_into_another_log
    Scene 5   test_swapped_artifact_is_caught_by_its_hash
    Scene 6   test_shared_lineage_is_not_independent
    Scene 7   test_missing_lineage_means_independence_cannot_be_checked
    Scene 8   test_remote_authority_closure_is_not_accepted
    Scene 9   test_restated_registration_evidence_is_not_novel  (a dishonest peer)
    Scene 10  test_unrecognized_or_tampered_logs_are_rejected
    Scene 11  test_rollback_is_rejected
    Scene 12  test_fork_is_proof_of_equivocation
    Scene 13  test_reopen_at_the_peer_withdraws_the_acceptance
    Scene 14  test_broken_upstream_at_the_peer_is_rejected
    Scene 15  test_chain_through_a_third_node_is_followed_to_its_owner
    Scene 16  test_peer_cannot_vouch_for_a_third_nodes_loop
    Scene 17  test_nominal_remote_classification_is_not_inherited
    Scene 18  test_formal_proof_is_rechecked_by_the_receiver
    Scene 19  test_auditor_catches_equivocation_no_node_saw
    Scene 20  test_trust_list_refuses_takeover_and_unsigned_lineage
    Scene 21  test_no_node_changes_another_nodes_state
    Scene 22  test_honest_scenario_logs_parse_clean             (parametrized, 3 runs)
    Scene 23  test_honest_random_logs_parse_clean               (randomized, 100 runs)
    Scene 24  test_remote_ees_excludes_the_closer_not_the_registrant
    Scene 25  test_remote_closure_with_one_unsound_cited_item_is_rejected
    Scene 26  test_remote_superseded_upstream_and_late_dependency

READER'S NOTE — two Nodes with one key
    Scenes 12 and 19 need a dishonest node: one that signs two different
    histories. The tests build it as two Node objects holding the same
    AgentKey, so the "same" node can do different things in each.
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# dataclasses.replace   build a tampered copy of a frozen record.
# random                the seeded generator for Scene 23.
# pytest                fixtures and raises.
# cclf                  Supervisor vocabulary.
# cclf.federation       the module under test.
# stagehands            TECH (a referent); RULE3 (a Rule 3 registration).
# ===========================================================================

import random
from dataclasses import replace

import pytest

from cclf import (Advisor, CommitmentState, EvidenceKind, ExecutionClass, ExitType,
                  OperationalState, SignalType, Supervisor, TransitionRefused, replay)
from cclf.federation import (AgentKey, Node, TrustList, _remote_sound, attest,
                             audit_federation, declare_lineage, parse_log)
from scenarios import SCENARIOS
from stagehands import RULE3, TECH


# ===========================================================================
# PRELUDE — the world every scene starts from
# ===========================================================================

# DESIGN — the process under evaluation, in every signal.
# LAB    — the independent producer of measurements.
DESIGN = "design-model"
LAB = "lab"


class World:
    """
    Three nodes that recognize each other, the lab and the design model,
    with signed lineage statements that share nothing.

    Fields:
      keys      name -> AgentKey
      bell, acme, cobalt   the three Nodes
    """

    def __init__(self):
        self.keys = {n: AgentKey(n) for n in ("bell", "acme", "cobalt", LAB, DESIGN)}
        self.bell, self.acme, self.cobalt = (Node(self.keys[n]) for n in ("bell", "acme", "cobalt"))
        statements = [declare_lineage(self.keys[LAB], ["lab-instruments"]),
                      declare_lineage(self.keys[DESIGN], ["base-model-x", "corpus-1"])]
        for node in self.nodes:
            for name, key in self.keys.items():
                if name != node.name:
                    node.recognize(key.public, by=f"{node.name}-ops")
            for st in statements:
                node.declare_lineage(st, by=f"{node.name}-ops")

    @property
    def nodes(self):
        return (self.bell, self.acme, self.cobalt)


@pytest.fixture
def world() -> World:
    return World()


def register_at(node: Node, sid: str, evidence_at_registration=()) -> None:
    """
    Register a constraint signal at a node and put it under review.

    Enter:   node, sid                 where, and the signal id
             evidence_at_registration  evidence ids attached at registration
    Exit:    None
    """
    node.sv.register_signal(sid, SignalType.CONSTRAINT, "seal fails cold", "eng1", TECH,
                            DESIGN, steward="eng1", successor="eng2", failure_mode="seal",
                            evidence_ids=evidence_at_registration)
    node.sv.classify(sid, OperationalState.ELEVATED_UNCERTAINTY, "eng1")
    node.sv.open_review(sid, "eng1")


def close_at(w: World, node: Node, sid: str, eid: str = None, artifact: str = "cold-test data",
             producer: str = LAB, relay: str = None, depends_on=(), attest_it: bool = True,
             register: bool = True) -> str:
    """
    A node closes a signal by evidence from the lab, with the lab's
    attestation published alongside.

    Enter:   w, node, sid    the world, the node, the signal
             eid             evidence id (default "<sid>-ev")
             artifact        the evidence's content
             producer        who produced it
             relay           whom the producer gave it to (default: node)
             depends_on      loops the evidence rests on
             attest_it       publish an attestation from the producer
             register        register the signal first
    Exit:    the evidence id
    """
    eid = eid or f"{sid}-ev"
    if register:
        register_at(node, sid)
    node.sv.add_evidence(eid, "cold test", "lab report", EvidenceKind.DIRECT_MEASUREMENT,
                         producer, "eng1", [sid], depends_on=depends_on)
    if attest_it:
        node.hold_attestation(attest(w.keys[producer], relay or node.name, eid,
                                     EvidenceKind.DIRECT_MEASUREMENT, artifact))
    node.sv.attempt_closure(sid, "eng2", TECH, [eid], "lab measurement")
    return eid


def mirror(w: World, at: Node, peer: Node, sid: str, decision: str = "launch") -> str:
    """
    `at` receives `peer`'s log and makes a decision depend on `peer`'s sid.

    Enter:   w, at, peer, sid, decision
    Exit:    the mirror id
    """
    assert at.receive(peer.publish(), by=f"{at.name}-ops")
    if decision not in at.sv.decisions:
        at.sv.register_decision(decision, "launch", ExecutionClass.IRREVERSIBLE, [], "mgr")
    return at.depend(decision, peer.name, sid, by=f"{at.name}-ops")


def events(node: Node, name: str):
    """Every audit entry with this event name."""
    return [e for e in node.sv.audit.entries() if e.event == name]


# ===========================================================================
# SCENE 1 — A transmitted closure is not a resolution
# ===========================================================================

def test_remote_closure_leaves_the_mirror_open_until_accepted(world):
    close_at(world, world.bell, "frr-3")
    mid = mirror(world, world.acme, world.bell, "frr-3")
    # bell's loop is closed; acme's mirror of it is still open.
    assert world.acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert ok, why
    assert world.acme.sv.signals[mid].state == CommitmentState.CLOSED_EVIDENCE
    assert world.acme.sv.chain_sound(mid)
    accepted = events(world.acme, "REMOTE_CLOSURE_ACCEPTED")[-1].payload
    assert accepted["producer"] == LAB and accepted["evidence_owner"] == "bell"


# ===========================================================================
# SCENE 2 — The local gate treats an accepted mirror like any loop
# ===========================================================================

def test_accepted_closure_lets_the_local_gate_pass(world):
    close_at(world, world.bell, "frr-3")
    mirror(world, world.acme, world.bell, "frr-3")
    # The principal risk claim needs its own External Evidence Source in
    # the acceptance (October 2026): the mirror's closure evidence does not
    # substitute for it.
    world.acme.sv.add_evidence("launch-check", "joint inspected", "inspection",
                               EvidenceKind.DIRECT_MEASUREMENT, "acme-inspection", "acme-ops")
    world.acme.sv.accept_decision("launch", "mgr", "accept risk", evidence_ids=["launch-check"],
                                  risk_claim="the joint seals at launch temperature", **RULE3)
    world.acme.sv.attest_risk_evidence("launch", "acme-safety",
                                       "the inspection measures the joint seal")
    blocked = world.acme.sv.request_execution("launch", "mgr")
    assert not blocked.permitted
    world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    passed = world.acme.sv.request_execution("launch", "mgr")
    assert passed.permitted and not passed.overridden, passed.failures


# ===========================================================================
# SCENE 3 — Only the producer's key can sign its attestation
# ===========================================================================

def test_relayer_cannot_forge_the_producers_attestation(world):
    close_at(world, world.bell, "frr-3", attest_it=False)
    # bell signs an attestation that claims the lab as producer.
    forged = attest(AgentKey(LAB, world.keys["bell"]._private), "bell", "frr-3-ev",
                    EvidenceKind.DIRECT_MEASUREMENT, "cold-test data")
    world.bell.hold_attestation(forged)
    mid = mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "signature" in why
    assert world.acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW
    assert events(world.acme, "REMOTE_CLOSURE_REJECTED")


# ===========================================================================
# SCENE 4 — An attestation given to one node cannot be cited from another
# ===========================================================================

def test_attestation_cannot_be_replayed_into_another_log(world):
    # The lab gave this measurement to cobalt; bell cites it as its own.
    close_at(world, world.bell, "frr-3", relay="cobalt")
    mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "given to cobalt" in why


# ===========================================================================
# SCENE 5 — A content hash pins the artifact
# ===========================================================================

def test_swapped_artifact_is_caught_by_its_hash(world):
    close_at(world, world.bell, "frr-3")
    att = world.bell.attestations["frr-3-ev"]
    world.bell.hold_attestation(replace(att, artifact="different data"))
    mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "hash" in why


# ===========================================================================
# SCENE 6 — Shared ancestry is not independence
# ===========================================================================

def test_shared_lineage_is_not_independent(world):
    # A "lab" whose analysis runs on the same base model as the design model.
    twin = AgentKey("twin-lab")
    world.keys["twin-lab"] = twin
    world.acme.recognize(twin.public, by="acme-ops")
    world.acme.declare_lineage(declare_lineage(twin, ["base-model-x"]), by="acme-ops")
    close_at(world, world.bell, "frr-3", producer="twin-lab")
    mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "shares lineage ['base-model-x']" in why


# ===========================================================================
# SCENE 7 — No lineage statement, no independence claim
# ===========================================================================

def test_missing_lineage_means_independence_cannot_be_checked(world):
    quiet = AgentKey("quiet-lab")
    world.keys["quiet-lab"] = quiet
    world.acme.recognize(quiet.public, by="acme-ops")
    close_at(world, world.bell, "frr-3", producer="quiet-lab")
    mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "no lineage statement for quiet-lab" in why


# ===========================================================================
# SCENE 8 — A peer's authority closure is not evidence
# ===========================================================================

def test_remote_authority_closure_is_not_accepted(world):
    register_at(world.bell, "frr-3")
    world.bell.sv.attempt_closure("frr-3", "manager", TECH, [], "schedule pressure")
    assert world.bell.sv.signals["frr-3"].state == CommitmentState.CLOSED_AUTHORITY
    mid = mirror(world, world.acme, world.bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "closed by evidence" in why
    assert world.acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW


# ===========================================================================
# SCENE 9 — Evidence Novelty is recomputed from the peer's log
# ===========================================================================

def test_restated_registration_evidence_is_not_novel(world):
    bell = world.bell
    bell.sv.add_evidence("old", "cold test", "lab report", EvidenceKind.DIRECT_MEASUREMENT,
                         LAB, "eng1")
    bell.hold_attestation(attest(world.keys[LAB], "bell", "old",
                                 EvidenceKind.DIRECT_MEASUREMENT, "x"))
    register_at(bell, "frr-3", evidence_at_registration=["old"])
    # bell's own Supervisor would call this an authority closure. A
    # dishonest bell writes an evidence closure into its log directly.
    bell.sv._log("TRANSITION", "eng2", signal="frr-3", cited_evidence=["old"],
                 **{"from": "under_review", "to": "closed_evidence"})
    mirror(world, world.acme, bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "cites no novel" in why


# ===========================================================================
# SCENE 10 — Unrecognized or edited logs are refused
# ===========================================================================

def test_unrecognized_or_tampered_logs_are_rejected(world):
    stranger = Node(AgentKey("stranger"))
    assert not world.acme.receive(stranger.publish(), by="acme-ops")
    close_at(world, world.bell, "frr-3")
    seg = world.bell.publish()
    edited = list(seg.entries)
    edited[3] = replace(edited[3], actor="someone-else")
    assert not world.acme.receive(replace(seg, entries=tuple(edited)), by="acme-ops")
    reasons = [e.payload["reason"] for e in events(world.acme, "PEER_LOG_REJECTED")]
    assert "not recognized" in reasons[0] and "chain" in reasons[1]
    with pytest.raises(TransitionRefused):
        world.acme.depend("launch", "bell", "frr-3", by="acme-ops")


# ===========================================================================
# SCENE 11 — A log may only grow
# ===========================================================================

def test_rollback_is_rejected(world):
    early = world.bell.publish()
    close_at(world, world.bell, "frr-3")
    assert world.acme.receive(world.bell.publish(), by="acme-ops")
    assert not world.acme.receive(early, by="acme-ops")
    assert "rollback" in events(world.acme, "PEER_LOG_REJECTED")[-1].payload["reason"]


# ===========================================================================
# SCENE 12 — Two signed histories are proof
# ===========================================================================

def test_fork_is_proof_of_equivocation(world):
    honest = world.bell
    close_at(world, honest, "frr-3")
    mid = mirror(world, world.acme, honest, "frr-3")
    assert world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")[0]
    # The same key signs a different history, at least as long.
    twin = Node(world.keys["bell"])
    for _ in range(len(honest.sv.audit.entries()) + 1):
        twin.sv._log("NOTE", "bell", text="another story")
    assert not world.acme.receive(twin.publish(), by="acme-ops")
    fork = events(world.acme, "PEER_FORK_DETECTED")[-1].payload
    bell_id = world.keys["bell"].public
    # Both heads verify under bell's key: the fork is attributable.
    assert bell_id.verify(fork["earlier_head"], fork["earlier_signature"])
    assert bell_id.verify(fork["later_head"], fork["later_signature"])
    assert world.acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW
    assert events(world.acme, "REMOTE_CLOSURE_WITHDRAWN")
    # Afterwards even its honest log is refused.
    assert not world.acme.receive(honest.publish(), by="acme-ops")


# ===========================================================================
# SCENE 13 — A peer's reopen reaches every node that accepted the closure
# ===========================================================================

def test_reopen_at_the_peer_withdraws_the_acceptance(world):
    close_at(world, world.bell, "frr-3")
    mid = mirror(world, world.acme, world.bell, "frr-3")
    world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    world.bell.sv.reopen("frr-3", "eng3", "new cold-weather data")
    assert world.acme.receive(world.bell.publish(), by="acme-ops")
    assert world.acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW
    assert "acme-ops" == events(world.acme, "REMOTE_CLOSURE_WITHDRAWN")[-1].actor
    # The auditor finds the history consistent: acceptance, then withdrawal.
    assert audit_federation([world.acme.publish(), world.bell.publish()],
                            world.acme.trust).ok


# ===========================================================================
# SCENE 14 — The chain is checked at the peer too
# ===========================================================================

def test_broken_upstream_at_the_peer_is_rejected(world):
    bell = world.bell
    register_at(bell, "upstream")
    bell.sv.attempt_closure("upstream", "manager", TECH, [], "decided")  # authority
    close_at(world, bell, "frr-3", depends_on=["upstream"])
    mirror(world, world.acme, bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "upstream" in why


# ===========================================================================
# SCENE 15 — A chain through a third node is followed to its owner
# ===========================================================================

def test_chain_through_a_third_node_is_followed_to_its_owner(world):
    bell, acme, cobalt = world.bell, world.acme, world.cobalt
    close_at(world, cobalt, "seal-spec")
    # bell mirrors cobalt's loop and accepts it.
    up = mirror(world, bell, cobalt, "seal-spec", decision="bell-plan")
    assert bell.accept_remote_closure("cobalt", "seal-spec", by="bell-ops")[0]
    # bell's own loop rests on that mirror.
    close_at(world, bell, "frr-3", depends_on=[up])
    mid = mirror(world, acme, bell, "frr-3")
    ok, why = acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "no verified log from cobalt" in why
    assert acme.receive(cobalt.publish(), by="acme-ops")
    assert acme.accept_remote_closure("bell", "frr-3", by="acme-ops")[0]
    # cobalt reopens; acme hears it from cobalt, not from bell.
    cobalt.sv.reopen("seal-spec", "eng3", "spec revised")
    assert acme.receive(cobalt.publish(), by="acme-ops")
    assert acme.sv.signals[mid].state == CommitmentState.UNDER_REVIEW
    assert audit_federation([n.publish() for n in world.nodes], acme.trust).ok


# ===========================================================================
# SCENE 16 — A peer's mirror is not its own word
# ===========================================================================

def test_peer_cannot_vouch_for_a_third_nodes_loop(world):
    bell, acme, cobalt = world.bell, world.acme, world.cobalt
    register_at(cobalt, "seal-spec")              # still open at cobalt
    up = mirror(world, bell, cobalt, "seal-spec", decision="bell-plan")
    # bell closes its mirror itself with lab evidence, without cobalt.
    close_at(world, bell, up, eid="bell-own", register=False)
    assert bell.sv.signals[up].state == CommitmentState.CLOSED_EVIDENCE
    mirror(world, acme, bell, up, decision="launch")
    acme.receive(cobalt.publish(), by="acme-ops")
    ok, why = acme.accept_remote_closure("bell", up, by="acme-ops")
    assert not ok and "via bell" in why and "cobalt" in why


# ===========================================================================
# SCENE 17 — Rule 2 at the boundary
# ===========================================================================

def test_nominal_remote_classification_is_not_inherited(world):
    bell = world.bell
    bell.sv.register_signal("ok-1", SignalType.CONSTRAINT, "fine", "eng1", TECH, DESIGN,
                            steward="eng1", successor="eng2")
    bell.sv.add_evidence("m", "measured", "lab", EvidenceKind.DIRECT_MEASUREMENT, LAB, "eng1",
                         ["ok-1"])
    bell.sv.classify("ok-1", OperationalState.NOMINAL, "eng1", evidence_ids=["m"])
    assert bell.sv.signals["ok-1"].operational_state == OperationalState.NOMINAL
    mid = mirror(world, world.acme, bell, "ok-1")
    assert (world.acme.sv.signals[mid].operational_state
            == OperationalState.ELEVATED_UNCERTAINTY)
    # The federation layer does this itself; acme's own Rule 2 check (which
    # would log CLASSIFICATION_REJECTED) is a second line, not the first.
    assert not events(world.acme, "CLASSIFICATION_REJECTED")


# ===========================================================================
# SCENE 18 — A proof the receiver can check needs no one's word
# ===========================================================================

def test_formal_proof_is_rechecked_by_the_receiver(world):
    def checker(proof: str) -> bool:
        return proof.endswith("QED")
    acme = Node(AgentKey("acme"), checkers={EvidenceKind.FORMAL_VERIFICATION.value: checker})
    for name, key in world.keys.items():
        if name != "acme":
            acme.recognize(key.public, by="acme-ops")
    for name in (LAB, DESIGN):
        acme.declare_lineage(world.bell.trust.lineages[name], by="acme-ops")
    bell = world.bell
    register_at(bell, "frr-3")
    bell.sv.add_evidence("proof", "model check", "lab", EvidenceKind.FORMAL_VERIFICATION, LAB,
                         "eng1", ["frr-3"])
    bell.hold_attestation(attest(world.keys[LAB], "bell", "proof",
                                 EvidenceKind.FORMAL_VERIFICATION, "lemma 1 ... (gap)"))
    bell.sv.attempt_closure("frr-3", "eng2", TECH, ["proof"], "proved")
    mirror(world, acme, bell, "frr-3")
    ok, why = acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "failed the receiver's check" in why
    # Shipping only the hash is not enough for a kind the receiver re-checks.
    bell.hold_attestation(attest(world.keys[LAB], "bell", "proof",
                                 EvidenceKind.FORMAL_VERIFICATION, "lemma 1 ... QED",
                                 ship_artifact=False))
    acme.receive(bell.publish(), by="acme-ops")
    ok, why = acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "no artifact shipped" in why


# ===========================================================================
# SCENE 19 — The auditor sees what no single node saw
# ===========================================================================

def test_auditor_catches_equivocation_no_node_saw(world):
    shown = world.bell                       # the history acme is shown
    close_at(world, shown, "frr-3")
    mirror(world, world.acme, shown, "frr-3")
    world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    published = Node(world.keys["bell"])     # the history bell publishes
    register_at(published, "frr-3")
    while len(published.sv.audit.entries()) < len(shown.sv.audit.entries()):
        published.sv._log("NOTE", "bell", text="padding, so only the fork differs")
    report = audit_federation([world.acme.publish(), published.publish()], world.acme.trust)
    assert not report.ok
    assert any("different history" in p for p in report.problems)
    # The honest pair passes.
    assert audit_federation([world.acme.publish(), shown.publish()], world.acme.trust).ok


# ===========================================================================
# SCENE 20 — No central registry, and no name taken over
# ===========================================================================

def test_trust_list_refuses_takeover_and_unsigned_lineage(world):
    impostor = AgentKey(LAB)
    with pytest.raises(TransitionRefused):
        world.acme.recognize(impostor.public, by="acme-ops")
    with pytest.raises(TransitionRefused):
        world.acme.declare_lineage(declare_lineage(impostor, ["nothing-shared"]), by="acme-ops")
    # Each node's trust list is its own.
    alone = TrustList()
    assert LAB not in alone.identities


# ===========================================================================
# SCENE 21 — Separate machines
# Everything a node does changes only its own state. (The TLA+ model checks
# the same as NodeIsolation.)
# ===========================================================================

def snapshot(node: Node):
    """A node's state, as comparable values: log head and length, signals, grants."""
    return (node.sv.audit.head(), len(node.sv.audit.entries()),
            {k: (v.state, v.operational_state) for k, v in node.sv.signals.items()},
            list(node.sv.grants), dict(node.accepted), set(node.equivocators))


def test_no_node_changes_another_nodes_state(world):
    bell, acme, cobalt = world.bell, world.acme, world.cobalt
    close_at(world, bell, "frr-3")
    before = {n.name: snapshot(n) for n in (bell, cobalt)}
    seg = bell.publish()
    mid = mirror(world, acme, bell, "frr-3")
    acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    # acme scribbles on what it received, then works on as usual.
    seg.entries[0].payload["signal"] = "scribbled"
    acme.receive(bell.publish(), by="acme-ops")
    acme.sv.reopen(mid, "acme-ops", "local doubt")
    assert {n.name: snapshot(n) for n in (bell, cobalt)} == before
    assert bell.sv.audit.verify(bell.sv.audit.entries(), bell.sv.audit.head())[0]


# ===========================================================================
# SCENE 22 — The strict reader never rejects an honest log
# parse_log refuses any entry an honest Supervisor could not have written.
# Every scenario's log must therefore come out clean.
# ===========================================================================

@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_honest_scenario_logs_parse_clean(name):
    sv = replay(SCENARIOS[name], advisor=Advisor(ask=lambda system, user: ""))
    assert parse_log(sv.audit.entries()).problems == []


# ===========================================================================
# SCENE 23 — Nor a random one
# Random operations through the Supervisor's public methods (refusals
# included, since they are logged too); the log must still parse clean.
# ===========================================================================

@pytest.mark.parametrize("seed", range(100))
def test_honest_random_logs_parse_clean(seed):
    rng = random.Random(seed)
    sv = Supervisor()
    ids = [f"s{i}" for i in range(4)]
    ops = [
        lambda s: sv.register_signal(s, rng.choice(list(SignalType)), "x", "eng1", TECH, DESIGN,
                                     steward="eng1", successor="eng2"),
        lambda s: sv.classify(s, rng.choice([OperationalState.ELEVATED_UNCERTAINTY] * 6
                                            + list(OperationalState)), "eng1"),
        lambda s: sv.open_review(s, "eng1"),
        lambda s: sv.add_evidence(f"{s}-{rng.random()}", "m", "lab",
                                  EvidenceKind.DIRECT_MEASUREMENT, LAB, "eng1", [s]),
        lambda s: sv.attempt_closure(s, rng.choice(["eng1", "eng2"]), TECH,
                                     list(sv.signals[s].evidence_ids), "c"),
        lambda s: sv.reopen(s, "eng3", "r"),
        lambda s: sv.suppress(s, "mgr", "no"),
        lambda s: sv.reenter_suppressed(s, "eng3", "back"),
        lambda s: sv.exit(s, rng.choice([ExitType.TERMINAL, ExitType.RECOVERABLE,
                                         ExitType.SUPERSEDED]), "eng1", "done"),
        lambda s: sv.reenter(s, "eng2", "again"),
    ]
    weights = [3, 3, 3, 3, 4, 2, 1, 1, 1, 1]      # favor the paths to closure
    for _ in range(80):
        try:
            rng.choices(ops, weights)[0](rng.choice(ids))
        except (TransitionRefused, KeyError):
            pass
    assert parse_log(sv.audit.entries()).problems == []


# ===========================================================================
# SCENE 24 — One EES definition across the boundary
# Proves: the remote recomputation uses the claimant (the closing agent),
# not the registrant, as the Supervisor does (Layer 2, EES): the
# registrant's own measurement can carry another agent's closure; the
# closer's own cannot.
# ===========================================================================

def test_remote_ees_excludes_the_closer_not_the_registrant(world):
    bell = world.bell
    # eng1 registered "by-registrant"; the measurement is eng1's; eng2 closes.
    register_at(bell, "by-registrant")
    bell.sv.add_evidence("reg-ev", "cold test", "eng1's reading",
                         EvidenceKind.DIRECT_MEASUREMENT, "eng1", "eng1", ["by-registrant"])
    bell.sv.attempt_closure("by-registrant", "eng2", TECH, ["reg-ev"], "measured")
    # eng2 closes "by-closer" on eng2's own reading.
    register_at(bell, "by-closer")
    bell.sv.add_evidence("own-ev", "cold test", "eng2's reading",
                         EvidenceKind.DIRECT_MEASUREMENT, "eng2", "eng1", ["by-closer"])
    bell.sv.attempt_closure("by-closer", "eng2", TECH, ["own-ev"], "measured")
    log = bell.sv.audit.entries()
    assert _remote_sound(log, "by-registrant", "bell")[0] is True
    assert bell.sv.chain_sound("by-registrant") is True
    assert _remote_sound(log, "by-closer", "bell")[0] is False
    assert bell.sv.signals["by-closer"].state == CommitmentState.CLOSED_AUTHORITY


# ===========================================================================
# SCENE 25 — Every cited item is load-bearing, at the peer too
# Proves: a peer's closure pairing a clean, attested item with one that
# rests on an authority-closed loop is not sound when recomputed, and is
# not accepted (Layer 2, Closure Chain).
# ===========================================================================

def test_remote_closure_with_one_unsound_cited_item_is_rejected(world):
    bell = world.bell
    register_at(bell, "rig")
    bell.sv.attempt_closure("rig", "manager", TECH, [], "decided")        # authority
    register_at(bell, "frr-3")
    bell.sv.add_evidence("clean", "cold test", "lab report", EvidenceKind.DIRECT_MEASUREMENT,
                         LAB, "eng1", ["frr-3"])
    bell.hold_attestation(attest(world.keys[LAB], "bell", "clean",
                                 EvidenceKind.DIRECT_MEASUREMENT, "cold-test data"))
    bell.sv.add_evidence("on-rig", "rig reading", "lab report", EvidenceKind.DIRECT_MEASUREMENT,
                         LAB, "eng1", ["frr-3"], depends_on=["rig"])
    bell.sv.attempt_closure("frr-3", "eng2", TECH, ["clean", "on-rig"], "two readings")
    assert _remote_sound(bell.sv.audit.entries(), "frr-3", "bell")[0] is False
    mirror(world, world.acme, bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert not ok and "on-rig" in why


# ===========================================================================
# SCENE 26 — A superseded upstream loop, and a dependency found later
# Proves: an upstream loop exited as superseded with an attested EES
# resolves the chain at the peer, as in the Supervisor; a dependency added
# later (DEPENDENCY_ADDED) is replayed from the log and breaks it again.
# ===========================================================================

def test_remote_superseded_upstream_and_late_dependency(world):
    bell = world.bell
    register_at(bell, "old-rig")
    bell.sv.add_evidence("retired", "rig retired", "asset register",
                         EvidenceKind.PRIMARY_DOCUMENT, LAB, "eng1")
    bell.hold_attestation(attest(world.keys[LAB], "bell", "retired",
                                 EvidenceKind.PRIMARY_DOCUMENT, "asset register entry"))
    bell.sv.exit("old-rig", ExitType.SUPERSEDED, "eng1", "the old rig was retired",
                 evidence_ids=["retired"])
    close_at(world, bell, "frr-3", depends_on=["old-rig"])
    assert _remote_sound(bell.sv.audit.entries(), "frr-3", "bell")[0] is True
    mid = mirror(world, world.acme, bell, "frr-3")
    ok, why = world.acme.accept_remote_closure("bell", "frr-3", by="acme-ops")
    assert ok, why
    assert world.acme.sv.signals[mid].state == CommitmentState.CLOSED_EVIDENCE
    # --- Later: the evidence is found to rest on an authority-closed loop ---
    register_at(bell, "calibration")
    bell.sv.attempt_closure("calibration", "manager", TECH, [], "decided")
    bell.sv.add_dependency("frr-3-ev", "calibration", "auditor")
    assert parse_log(bell.sv.audit.entries()).evidence["frr-3-ev"]["depends_on"] == \
        ["old-rig", "calibration"]
    assert _remote_sound(bell.sv.audit.entries(), "frr-3", "bell")[0] is False

# EXEUNT — end of file.
