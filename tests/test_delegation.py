"""
THE CHAIN OF HANDS
A Play in Eight Scenes
======================

PROLOGUE
--------
Tests for multi-hop delegation, revocation and expiry (Supervisor ACT VIII,
Scene 2b; federation ACT I, Scene 4 and ACT V, Scene 8).

The invariant under test:

    No delegation chain can produce permissions broader than those
    legitimately granted along that chain.

"Broader" has four directions, and every hop may try each one:
  power       a different power from the one held (recommend -> authorize)
  scope       a wider scope ("travel-booking" -> "*", or a different one)
  delegation  the right to grant on, when it was not given
  lifetime    a later expiry than the grantor's own, or none at all

And the harder half: authority that WAS valid can stop being valid
(revoked, or expired) partway through a handoff. The gate checks
authority when it is used, so an acceptance made under a grant that has
since lapsed authorizes nothing.

Across nodes, one limit no design removes: a revocation binds a node only
once it arrives. Scene 6 shows that window plainly, and shows the expiry
that bounds it.

THE PLAYBILL
    Prelude   Clock, chain() (fixture)
    Scene 1   test_every_hop_that_widens_is_refused
    Scene 2   test_revocation_halfway_through_a_handoff
    Scene 3   test_expiry_halfway_through_a_handoff
    Scene 4   test_only_the_chain_above_may_revoke
    Scene 5   test_execute_power_revoked_before_use
    Scene 6   test_cross_node_revocation_and_its_window
    Scene 7   test_expiry_bounds_the_window_when_a_revocation_never_arrives
    Scene 8   test_no_chain_exceeds_its_grants          (randomized, 300 runs)
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# random    the seeded generator for Scene 7.
# pytest    fixtures, raises, parametrize.
# cclf      the Supervisor and its vocabulary.
# cclf.federation   nodes, signed grants and revocations.
# stagehands        RULE3, the Rule 3 registration a passing acceptance needs;
#                   attest(), the independent risk-evidence attestation.
# ===========================================================================

import random

import pytest

from cclf import (EvidenceKind, ExecutionClass, Power, Settings, Supervisor,
                  TransitionRefused)
from cclf.federation import AgentKey, Node, sign_grant, sign_revocation
from stagehands import RULE3, attest


# ===========================================================================
# PRELUDE — a clock the tests control, and a chain A -> B -> C -> D
# ===========================================================================

# ROOT  — the principal every chain starts from.
# SCOPE — the bookings scope.
ROOT = "traveler"
SCOPE = "travel-booking"

# RISK — the principal risk claim and Rule 3 registration a Rule 4 acceptance
#   needs for the irreversible gate (October 2026), as accept_decision
#   keywords. The fare quote cited with it is the claim's External Evidence
#   Source.
RISK = dict(risk_claim="the fare is as quoted and refundable", **RULE3)


class Clock:
    """A wall clock that only moves when a test moves it."""

    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def sv(clock) -> Supervisor:
    """
    A Supervisor with this chain of AUTHORIZE grants over SCOPE:

        traveler -> A (delegable, until t+100)
                 -> B (delegable, until t+90)
                 -> C (not delegable, until t+80)

    and D holding EXECUTE from the traveler. A booking is tabled with an
    airline fare quote on hand.
    """
    s = Supervisor(Settings(authority_roots=frozenset({ROOT})), now=clock)
    t = clock.t
    s.grant("A", Power.AUTHORIZE, SCOPE, by=ROOT, delegable=True, expires_at=t + 100)
    s.grant("B", Power.AUTHORIZE, SCOPE, by="A", delegable=True, expires_at=t + 90)
    s.grant("C", Power.AUTHORIZE, SCOPE, by="B", delegable=False, expires_at=t + 80)
    s.grant("D", Power.EXECUTE, SCOPE, by=ROOT)
    s.add_evidence("fare-quote", "9:40 fare", "airline", EvidenceKind.PRIMARY_DOCUMENT,
                   "airline", "A")
    s.register_decision("book-flight", "buy the 9:40 fare", ExecutionClass.IRREVERSIBLE,
                        [], "A", scope=SCOPE)
    return s


def accept(sv: Supervisor, who: str) -> None:
    """`who` gives the Rule 4 acceptance, citing the fare quote, and the
    attester attests it."""
    sv.accept_decision("book-flight", who, "approved", evidence_ids=["fare-quote"], **RISK)
    attest(sv, "book-flight", root=ROOT)


# ===========================================================================
# SCENE 1 — Each hop tries to widen, a little; each attempt is refused
# ===========================================================================

def test_every_hop_that_widens_is_refused(sv, clock):
    t = clock.t
    widenings = [
        # (grantor, grantee, power, scope, delegable, expires_at)   why it widens
        ("B", "C2", Power.EXECUTE, SCOPE, False, t + 50),          # another power
        ("B", "C2", Power.AUTHORIZE, "*", False, t + 50),          # every scope
        ("B", "C2", Power.AUTHORIZE, "payroll", False, t + 50),    # another scope
        ("B", "C2", Power.AUTHORIZE, SCOPE, False, t + 95),        # outlives B (t+90)
        ("B", "C2", Power.AUTHORIZE, SCOPE, False, None),          # never lapses
        ("C", "D2", Power.AUTHORIZE, SCOPE, False, t + 10),        # C may not delegate
        ("D", "E", Power.EXECUTE, SCOPE, False, t + 10),           # D may not delegate
        ("D", "E", Power.AUTHORIZE, SCOPE, False, t + 10),         # D never held it
    ]
    for grantor, grantee, power, scope, delegable, expires in widenings:
        with pytest.raises(TransitionRefused):
            sv.grant(grantee, power, scope, by=grantor, delegable=delegable,
                     expires_at=expires)
    assert len([e for e in sv.audit.entries() if e.event == "GRANT_REFUSED"]) == len(widenings)
    assert not any(sv.holds(x, p, s) for x in ("C2", "D2", "E")
                   for p in Power for s in (SCOPE, "*", "payroll"))
    # Narrowing is fine: same power and scope, shorter life, no delegation.
    g = sv.grant("C3", Power.AUTHORIZE, SCOPE, by="B", expires_at=t + 30)
    assert g.parent == "G2" and sv.holds("C3", Power.AUTHORIZE, SCOPE)
    # C's acceptance stands, and D executes.
    accept(sv, "C")
    assert sv.request_execution("book-flight", "D").permitted


# ===========================================================================
# SCENE 2 — A link is revoked after C accepted, before D executes
# ===========================================================================

def test_revocation_halfway_through_a_handoff(sv):
    accept(sv, "C")                                    # valid when made
    voided = sv.revoke("G2", by="A", reason="B is no longer trusted with bookings")
    assert voided == ["G2", "G3"]                      # B's grant and C's beneath it
    r = sv.request_execution("book-flight", "D", override_rationale="it was approved")
    assert not r.permitted and "no longer backed" in r.failures[0]
    assert not sv.decisions["book-flight"].executed
    # Someone still holding authority must accept again.
    accept(sv, "A")
    assert sv.request_execution("book-flight", "D").permitted


# ===========================================================================
# SCENE 3 — The same, by expiry
# ===========================================================================

def test_expiry_halfway_through_a_handoff(sv, clock):
    accept(sv, "C")
    clock.t += 85                       # C's grant lapsed at t+80
    assert not sv.request_execution("book-flight", "D").permitted
    assert sv.holds("B", Power.AUTHORIZE, SCOPE)        # B's lasts until t+90
    clock.t += 10                       # now B's has lapsed too
    assert not sv.holds("B", Power.AUTHORIZE, SCOPE)
    with pytest.raises(TransitionRefused):
        accept(sv, "B")
    accept(sv, ROOT)
    assert sv.request_execution("book-flight", "D").permitted


# ===========================================================================
# SCENE 4 — Who may revoke
# ===========================================================================

def test_only_the_chain_above_may_revoke(sv):
    with pytest.raises(TransitionRefused):
        sv.revoke("G2", by="C", reason="C revokes its own source")   # below, not above
    with pytest.raises(TransitionRefused):
        sv.revoke("G2", by="D", reason="an outsider")
    sv.revoke("G3", by="A", reason="A, two links up")              # above: allowed
    assert not sv.holds("C", Power.AUTHORIZE, SCOPE)
    assert sv.holds("B", Power.AUTHORIZE, SCOPE)                   # unaffected


# ===========================================================================
# SCENE 5 — The executor's own power, withdrawn before it is used
# ===========================================================================

def test_execute_power_revoked_before_use(sv):
    accept(sv, "C")
    sv.revoke("G4", by=ROOT, reason="D's booking access withdrawn")
    r = sv.request_execution("book-flight", "D", override_rationale="already approved")
    assert not r.permitted and "does not hold execute" in r.failures[0]


# ===========================================================================
# SCENE 6 — Across nodes: a revocation binds once it arrives
# ===========================================================================

def test_cross_node_revocation_and_its_window(clock):
    keys = {n: AgentKey(n) for n in ("booking-node", ROOT, "B")}
    node = Node(keys["booking-node"], Settings(authority_roots=frozenset({ROOT})))
    node.sv.now = clock
    node.recognize(keys[ROOT].public, by="ops", principal=True)
    node.recognize(keys["B"].public, by="ops")
    g = sign_grant(keys[ROOT], "B", "booking-node", Power.AUTHORIZE, SCOPE,
                   expires_at=clock.t + 60)
    node.receive_grant(g, by="ops")
    node.sv.grant("D", Power.EXECUTE, SCOPE, by=ROOT)
    node.sv.add_evidence("q", "fare", "airline", EvidenceKind.PRIMARY_DOCUMENT, "airline", "B")
    for d in ("trip-1", "trip-2", "trip-3"):
        node.sv.register_decision(d, d, ExecutionClass.IRREVERSIBLE, [], "B")
        node.sv.assign_scope(d, SCOPE, by=ROOT)
        node.sv.accept_decision(d, "B", "approved", evidence_ids=["q"], **RISK)
        attest(node.sv, d, root=ROOT)
    # The traveler signs a revocation. Until it arrives, the node cannot
    # know: trip-1 goes ahead. This is the window, stated, not hidden.
    revocation = sign_revocation(keys[ROOT], g, "trip cancelled")
    assert node.sv.request_execution("trip-1", "D").permitted
    # It arrives; trip-2, accepted under that grant, is blocked.
    assert node.receive_revocation(revocation, by="ops") == ["G1"]
    assert not node.sv.request_execution("trip-2", "D").permitted
    # Revocations are bound and signed like grants.
    with pytest.raises(TransitionRefused, match="addressed"):
        node.receive_revocation(sign_revocation(keys[ROOT], sign_grant(
            keys[ROOT], "B", "other-node", Power.AUTHORIZE, SCOPE), "x"), by="ops")
    forged = sign_revocation(AgentKey(ROOT, keys["B"]._private), g, "forged")
    with pytest.raises(TransitionRefused, match="invalid"):
        node.receive_revocation(forged, by="ops")


# ===========================================================================
# SCENE 7 — A revocation lost in transit: expiry still ends the grant
# ===========================================================================

def test_expiry_bounds_the_window_when_a_revocation_never_arrives(clock):
    keys = {n: AgentKey(n) for n in ("booking-node", ROOT)}
    node = Node(keys["booking-node"], Settings(authority_roots=frozenset({ROOT})))
    node.sv.now = clock
    node.recognize(keys[ROOT].public, by="ops", principal=True)
    node.receive_grant(sign_grant(keys[ROOT], "B", "booking-node", Power.AUTHORIZE, SCOPE,
                                  expires_at=clock.t + 60), by="ops")
    node.sv.grant("D", Power.EXECUTE, SCOPE, by=ROOT)
    node.sv.add_evidence("q", "fare", "airline", EvidenceKind.PRIMARY_DOCUMENT, "airline", "B")
    node.sv.register_decision("trip", "trip", ExecutionClass.IRREVERSIBLE, [], "B")
    node.sv.assign_scope("trip", SCOPE, by=ROOT)
    node.sv.accept_decision("trip", "B", "approved", evidence_ids=["q"], **RISK)
    attest(node.sv, "trip", root=ROOT)
    clock.t += 61                      # the revocation was lost; the grant lapses anyway
    assert not node.sv.request_execution("trip", "D").permitted


# ===========================================================================
# SCENE 8 — The invariant, over many random histories
# ===========================================================================

AGENTS = [ROOT, "A", "B", "C", "D", "E"]
SCOPES = ["s1", "s2", "*"]


def in_force(sv: Supervisor, now: float) -> set[str]:
    """
    Which grants are in force, computed from scratch (an oracle written
    apart from the Supervisor's own): a least fixed point from the roots.
    """
    good: set[str] = set()
    changed = True
    while changed:
        changed = False
        for g in sv.grants:
            if g.grant_id in good or g.grant_id in sv.revoked:
                continue
            if g.expires_at is not None and now >= g.expires_at:
                continue
            if (g.parent is None and g.granted_by == ROOT) or g.parent in good:
                good.add(g.grant_id)
                changed = True
    return good


def check_invariant(sv: Supervisor, now: float) -> None:
    """
    No grant in force is broader than the grant it came from, and holds()
    agrees with the oracle.
    """
    by_id = {g.grant_id: g for g in sv.grants}
    good = in_force(sv, now)
    for gid in good:
        g = by_id[gid]
        if g.parent is None:
            assert g.granted_by == ROOT
            continue
        p = by_id[g.parent]
        assert p.grant_id in good
        assert p.grantee == g.granted_by          # the grantor held it
        assert p.power == g.power                 # same power
        assert p.scope in (g.scope, "*")          # no wider scope
        assert p.delegable                        # it was delegable
        assert p.expires_at is None or (g.expires_at is not None
                                        and g.expires_at <= p.expires_at)  # no longer life
    for agent in AGENTS[1:]:
        for power in Power:
            for scope in SCOPES:
                oracle = any(by_id[x].grantee == agent and by_id[x].power == power
                             and by_id[x].scope in (scope, "*") for x in good)
                assert sv.holds(agent, power, scope) == oracle, (agent, power, scope)


@pytest.mark.parametrize("seed", range(300))
def test_no_chain_exceeds_its_grants(seed):
    rng = random.Random(seed)
    clock = Clock(0.0)
    sv = Supervisor(Settings(authority_roots=frozenset({ROOT})), now=clock)
    for _ in range(40):
        op = rng.random()
        try:
            if op < 0.7:
                sv.grant(rng.choice(AGENTS[1:]), rng.choice(list(Power)), rng.choice(SCOPES),
                         by=rng.choice(AGENTS), delegable=rng.random() < 0.6,
                         expires_at=rng.choice([None, clock.t + rng.randint(1, 30)]))
            elif op < 0.85 and sv.grants:
                sv.revoke(rng.choice(sv.grants).grant_id, by=rng.choice(AGENTS), reason="r")
            else:
                clock.t += rng.randint(1, 10)
        except TransitionRefused:
            pass
        check_invariant(sv, clock.t)
