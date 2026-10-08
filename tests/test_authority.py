"""
THE HANDOFF
A Play in Eight Scenes
======================

PROLOGUE
--------
Tests for authority: who may recommend, authorize and execute a decision
(Supervisor ACT VIII, Scene 2b; federation ACT I, Scene 4 and ACT V,
Scene 8).

The case that started it:

    Agent A has permission to research and recommend. Agent B has
    permission to execute authorized bookings. Agent A hands a
    recommendation to Agent B, which mistakes the handoff for
    authorization to purchase.

    Expected result: BLOCKED.
    Reason: neither interoperability nor delegation should manufacture
    authority that wasn't granted.

Before this suite, the runtime let it through. Rule 4 took any named
agent's acceptance, so B could accept on A's word. The only thing that
blocked the purchase was an unrelated evidence check, and B could override
it.

Draft basis: Rule 4 (Layer 1): "a single agent must explicitly accept
authorization, risk acceptance, and rationale documentation as their
responsibility." The draft does not say who may. Here the answer is an
IMPLEMENTATION DECISION: an authority root, or whoever a root's chain of
grants reaches, each grant no wider than what its grantor held.

THE PLAYBILL
    Prelude   booking() (helper), the cast
    Scene 1   test_handoff_is_not_authorization           (the case above)
    Scene 2   test_recommender_cannot_authorize_either
    Scene 3   test_delegation_cannot_exceed_what_was_granted
    Scene 4   test_genuinely_authorized_booking_executes
    Scene 5   test_override_cannot_supply_a_missing_power
    Scene 6   test_cross_node_handoff_is_not_authorization   (the case, federated)
    Scene 7   test_signed_grants_are_bound_and_verified
    Scene 8   test_without_roots_authority_is_not_enforced   (the old behavior)
"""

# ===========================================================================
# STAGE MANAGEMENT (imports)
# ---------------------------------------------------------------------------
# pytest            raises.
# cclf              Supervisor, Settings, Power, ExecutionClass, EvidenceKind,
#                   TransitionRefused.
# cclf.federation   AgentKey, Node, sign_grant.
# stagehands        RULE3, the Rule 3 registration a passing acceptance needs;
#                   attest(), the independent risk-evidence attestation.
# ===========================================================================

import pytest

from cclf import (EvidenceKind, ExecutionClass, Power, Settings, Supervisor,
                  TransitionRefused)
from cclf.federation import AgentKey, Node, sign_grant
from stagehands import RULE3, attest


# ===========================================================================
# PRELUDE — the cast
# ===========================================================================

# TRAVELER — the principal: the person the agents act for (the root).
# A, B     — the researcher-recommender and the booking executor.
# SCOPE    — the authority scope of every booking decision.
TRAVELER = "traveler"
A = "agent-a"
B = "agent-b"
SCOPE = "travel-booking"

# RISK — the principal risk claim and Rule 3 registration a Rule 4 acceptance
#   needs for the irreversible gate (October 2026), as accept_decision
#   keywords. The fare quote cited with it is the claim's External Evidence
#   Source.
RISK = dict(risk_claim="the fare is as quoted and refundable", **RULE3)


def booking(sv: Supervisor) -> None:
    """
    Grant A and B exactly the permissions in the case, and table a booking.

    Enter:   sv   a Supervisor whose authority root is TRAVELER
    Exit:    None. A holds RECOMMEND, B holds EXECUTE, both over SCOPE and
             neither delegable; decision "book-flight" is registered with
             an airline fare quote (an independent party's document) on
             hand for its acceptance to cite. A tables it; the traveler
             puts it in SCOPE (choosing a scope is an act of authority).
    """
    sv.grant(A, Power.RECOMMEND, SCOPE, by=TRAVELER)
    sv.grant(B, Power.EXECUTE, SCOPE, by=TRAVELER)
    sv.add_evidence("fare-quote", "9:40 fare, refundable within 24h", "airline",
                    EvidenceKind.PRIMARY_DOCUMENT, "airline", A)
    sv.register_decision("book-flight", "buy the 9:40 fare", ExecutionClass.IRREVERSIBLE,
                         [], A)
    sv.assign_scope("book-flight", SCOPE, by=TRAVELER)   # A may not choose the scope


@pytest.fixture
def sv() -> Supervisor:
    s = Supervisor(Settings(authority_roots=frozenset({TRAVELER})))
    booking(s)
    return s


def events(sv: Supervisor, name: str):
    """Every audit entry with this event name."""
    return [e for e in sv.audit.entries() if e.event == name]


# ===========================================================================
# SCENE 1 — A recommendation handed on is not an authorization
# ===========================================================================

def test_handoff_is_not_authorization(sv):
    sv.recommend("book-flight", A, "cheapest refundable fare")
    # B mistakes the handoff for authorization and accepts on A's word.
    with pytest.raises(TransitionRefused, match="does not hold authorize"):
        sv.accept_decision("book-flight", B, "agent-a recommended it",
                           evidence_ids=["fare-quote"], **RISK)
    assert sv.decisions["book-flight"].accepted_by is None
    # Then tries to purchase, with or without an override.
    for override in (None, "the user wants it booked"):
        r = sv.request_execution("book-flight", B, override_rationale=override)
        assert not r.permitted and not r.overridden          # BLOCKED
        assert "Rule 4" in r.failures[0]
    assert not sv.decisions["book-flight"].executed
    refused = events(sv, "ACCEPTANCE_REFUSED")[-1]
    assert refused.actor == B and refused.payload["power"] == "authorize"


# ===========================================================================
# SCENE 2 — Recommending does not include authorizing
# ===========================================================================

def test_recommender_cannot_authorize_either(sv):
    with pytest.raises(TransitionRefused):
        sv.accept_decision("book-flight", A, "I researched it", evidence_ids=["fare-quote"],
                           **RISK)
    # And B, holding only EXECUTE, cannot recommend.
    with pytest.raises(TransitionRefused):
        sv.recommend("book-flight", B, "looks good")
    assert events(sv, "RECOMMENDATION_REFUSED")


# ===========================================================================
# SCENE 3 — Delegation passes on only what was held
# ===========================================================================

def test_delegation_cannot_exceed_what_was_granted(sv):
    # A cannot grant a power it does not hold.
    with pytest.raises(TransitionRefused):
        sv.grant(B, Power.AUTHORIZE, SCOPE, by=A)
    # B holds EXECUTE, but not delegably: it cannot pass it on.
    with pytest.raises(TransitionRefused):
        sv.grant("agent-c", Power.EXECUTE, SCOPE, by=B)
    # A manager given delegable AUTHORIZE for bookings cannot widen the scope.
    sv.grant("manager", Power.AUTHORIZE, SCOPE, by=TRAVELER, delegable=True)
    with pytest.raises(TransitionRefused):
        sv.grant(B, Power.AUTHORIZE, "*", by="manager")
    with pytest.raises(TransitionRefused):
        sv.grant(B, Power.AUTHORIZE, "payroll", by="manager")
    # ... but can delegate within it, and the grantee then may not delegate.
    sv.grant(B, Power.AUTHORIZE, SCOPE, by="manager")
    assert sv.holds(B, Power.AUTHORIZE, SCOPE)
    assert not sv.holds(B, Power.AUTHORIZE, SCOPE, delegable=True)
    assert len(events(sv, "GRANT_REFUSED")) == 4


# ===========================================================================
# SCENE 4 — With a real authorization, the same booking goes ahead
# ===========================================================================

def test_genuinely_authorized_booking_executes(sv):
    sv.recommend("book-flight", A, "cheapest refundable fare")
    sv.accept_decision("book-flight", TRAVELER, "yes, book it", evidence_ids=["fare-quote"],
                       **RISK)
    attest(sv, "book-flight", root=TRAVELER)
    r = sv.request_execution("book-flight", B)
    assert r.permitted and not r.overridden, r.failures


# ===========================================================================
# SCENE 5 — An override is not a grant
# ===========================================================================

def test_override_cannot_supply_a_missing_power(sv):
    sv.accept_decision("book-flight", TRAVELER, "yes, book it", evidence_ids=["fare-quote"],
                       **RISK)
    attest(sv, "book-flight", root=TRAVELER)
    # A was never given EXECUTE; an override does not change that.
    r = sv.request_execution("book-flight", A, override_rationale="I'll just do it")
    assert not r.permitted and "does not hold execute" in r.failures[0]
    assert not sv.decisions["book-flight"].executed
    # B still can.
    assert sv.request_execution("book-flight", B).permitted


# ===========================================================================
# SCENE 6 — The case again, with A and B on different nodes
# ===========================================================================

def test_cross_node_handoff_is_not_authorization():
    keys = {n: AgentKey(n) for n in ("research-node", "booking-node", A, B, TRAVELER)}
    research = Node(keys["research-node"])
    booker = Node(keys["booking-node"], Settings(authority_roots=frozenset({TRAVELER})))
    for name, key in keys.items():
        for node in (research, booker):
            if name != node.name:
                node.recognize(key.public, by="ops", principal=(name == TRAVELER))
    booking(booker.sv)
    # A recommends at its own node; booking-node reads that verified log.
    research.sv.register_decision("book-flight", "buy the 9:40 fare",
                                  ExecutionClass.IRREVERSIBLE, [], A, scope=SCOPE)
    research.sv.recommend("book-flight", A, "cheapest refundable fare")
    assert booker.receive(research.publish(), by="ops")
    # B mistakes the verified, signed handoff for authorization.
    with pytest.raises(TransitionRefused):
        booker.sv.accept_decision("book-flight", B, "research-node recommended it",
                                  evidence_ids=["fare-quote"], **RISK)
    # A even signs a grant of AUTHORIZE: the signature is genuine, the
    # power is not A's to give.
    with pytest.raises(TransitionRefused, match="does not hold authorize"):
        booker.receive_grant(sign_grant(keys[A], B, "booking-node", Power.AUTHORIZE, SCOPE),
                             by="ops")
    assert booker.sv.request_execution("book-flight", B, "just book it").permitted is False
    # The traveler's own signed grant does make B an authorizer.
    booker.receive_grant(sign_grant(keys[TRAVELER], B, "booking-node", Power.AUTHORIZE, SCOPE),
                         by="ops")
    booker.sv.accept_decision("book-flight", B, "traveler authorized bookings",
                              evidence_ids=["fare-quote"], **RISK)
    attest(booker.sv, "book-flight", root=TRAVELER)
    assert booker.sv.request_execution("book-flight", B).permitted


# ===========================================================================
# SCENE 7 — A signed grant is checked before it is used
# ===========================================================================

def test_signed_grants_are_bound_and_verified():
    keys = {n: AgentKey(n) for n in ("booking-node", TRAVELER, B)}
    booker = Node(keys["booking-node"], Settings(authority_roots=frozenset({TRAVELER})))
    booker.recognize(keys[TRAVELER].public, by="ops", principal=True)
    # Addressed to another node: cannot be replayed here.
    with pytest.raises(TransitionRefused, match="addressed to"):
        booker.receive_grant(sign_grant(keys[TRAVELER], B, "other-node", Power.AUTHORIZE,
                                        SCOPE), by="ops")
    # Signed by someone else under the traveler's name.
    forged = sign_grant(AgentKey(TRAVELER, keys[B]._private), B, "booking-node",
                        Power.AUTHORIZE, SCOPE)
    with pytest.raises(TransitionRefused, match="invalid"):
        booker.receive_grant(forged, by="ops")
    assert len([e for e in booker.sv.audit.entries() if e.event == "GRANT_REJECTED"]) == 2
    assert not booker.sv.holds(B, Power.AUTHORIZE, SCOPE)


# ===========================================================================
# SCENE 8 — No roots, no enforcement (as before this suite)
# ===========================================================================

def test_without_roots_authority_is_not_enforced():
    sv = Supervisor()
    sv.register_decision("book-flight", "buy", ExecutionClass.IRREVERSIBLE, [], A)
    sv.accept_decision("book-flight", B, "agent-a recommended it")
    assert sv.decisions["book-flight"].accepted_by == B
    assert not sv.authority_enforced
