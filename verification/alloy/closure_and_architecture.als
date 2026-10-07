/*
 * CLOSURE AND ARCHITECTURE, STRUCTURALLY
 * A Model in Four Scenes
 * ======================================
 *
 * PROLOGUE
 * An Alloy model of two CCL-F v0.2 definitions the runtime enforces:
 *   - closure typing (Layer 2): evidence closure needs evidence that is both
 *     novel (Evidence Novelty) and external (External Evidence Source);
 *     otherwise a closure is role-switch or authority closure;
 *   - the Layer 0 voids the runtime checks: AP-A (no steward), AP.1b (no
 *     successor) and AP-F (captured channel).
 * The Alloy Analyzer searches every small instance (up to the scope in each
 * `check`) for a counterexample to each assertion, and confirms with `run`
 * that each closure type and each void can actually occur.
 *
 * Definitions mirror cclf/supervisor.py (is_novel, is_ees, attempt_closure,
 * architecture_check); the assertions restate what the draft says those
 * definitions must guarantee.
 *
 * THE PLAYBILL
 *   Scene 1  the cast: agents, evidence kinds, referents, time
 *   Scene 2  closure typing, and what it must guarantee
 *   Scene 3  Layer 0 voids, and what they must guarantee
 *   Scene 4  the commands (check = look for a counterexample; run = find
 *            an example)
 *
 * READER'S NOTE: reading Alloy
 *   A `sig` is a set of atoms; a field such as `producer: one Agent` is a
 *   relation. `fact`s constrain every instance; `pred`s are named
 *   conditions; `assert`s are claims the Analyzer tries to break.
 *   `x.f` follows relation f from x. `some`, `no`, `one`, `lone` are
 *   quantifiers: at least one, none, exactly one, at most one.
 */
module closure_and_architecture

open util/ordering[Time]

// ===========================================================================
// SCENE 1 - THE CAST
// ===========================================================================

sig Time {}
sig Agent {}

abstract sig Kind {}
one sig PrimaryDocument, DirectMeasurement, FormalVerification, IndependentParty,
        InternalAnalysis, Assertion, ModelOutput extends Kind {}

// The kinds that can be an External Evidence Source (EES_ELIGIBLE_KINDS).
fun EESKinds : set Kind {
  PrimaryDocument + DirectMeasurement + FormalVerification + IndependentParty
}

abstract sig Referent {}
one sig Technical, Customer extends Referent {}

sig Evidence {
  kind: one Kind,
  producer: one Agent,
  at: one Time
}

sig Signal {
  registrant: one Agent,
  evaluated: one Agent,        // the process under evaluation
  referent: one Referent,      // which referent generated the signal
  registeredAt: one Time,
  attached: set Evidence       // evidence present at registration
}
// Evidence present at registration existed by then.
fact { all s: Signal, e: s.attached | lte[e.at, s.registeredAt] }

// ===========================================================================
// SCENE 2 - CLOSURE TYPING
// ===========================================================================

abstract sig ClosureType {}
one sig EvidenceClosure, RoleSwitchClosure, AuthorityClosure extends ClosureType {}

sig Closure {
  signal: one Signal,
  closer: one Agent,
  closerReferent: one Referent,   // the referent the closer consulted
  cites: set Evidence,
  ctype: one ClosureType
}

// Evidence Novelty: not attached at registration, and produced afterwards.
pred novel[e: Evidence, s: Signal] {
  e not in s.attached
  gt[e.at, s.registeredAt]
}

// External Evidence Source: an eligible kind, produced by neither the
// process under evaluation nor the signal's registrant.
pred ees[e: Evidence, s: Signal] {
  e.kind in EESKinds
  e.producer not in s.evaluated + s.registrant
}

pred qualifies[c: Closure] { some e: c.cites | novel[e, c.signal] and ees[e, c.signal] }

pred roleSwitch[c: Closure] {
  c.closer = c.signal.registrant
  c.closerReferent != c.signal.referent
}

// The typing rule, as attempt_closure applies it: evidence first, then
// role switch, otherwise authority.
fact typing {
  all c: Closure |
    (qualifies[c] implies c.ctype = EvidenceClosure) and
    ((not qualifies[c] and roleSwitch[c]) implies c.ctype = RoleSwitchClosure) and
    ((not qualifies[c] and not roleSwitch[c]) implies c.ctype = AuthorityClosure)
}

// "Restating existing analysis in more confident language does not
// constitute new evidence": citing only what was there at registration
// never yields an evidence closure.
assert RestatementIsNotEvidence {
  all c: Closure | c.cites in c.signal.attached implies c.ctype != EvidenceClosure
}

// Model output, assertions and internal analysis never close a loop by
// evidence, however many of them are cited.
assert NonEESKindsNeverClose {
  all c: Closure |
    c.cites.kind in (InternalAnalysis + Assertion + ModelOutput)
      implies c.ctype != EvidenceClosure
}

// The process under evaluation cannot close its own signal by evidence it
// produced itself.
assert NoSelfCertification {
  all c: Closure |
    c.cites.producer in (c.signal.evaluated + c.signal.registrant)
      implies c.ctype != EvidenceClosure
}

// An evidence closure always rests on at least one independent producer.
assert EvidenceClosureHasIndependentSource {
  all c: Closure | c.ctype = EvidenceClosure implies
    some e: c.cites | e.producer not in c.signal.evaluated + c.signal.registrant
}

// Role-switch closure is only ever the registrant closing their own signal.
assert RoleSwitchIsSelfClosure {
  all c: Closure | c.ctype = RoleSwitchClosure implies c.closer = c.signal.registrant
}

// ===========================================================================
// SCENE 3 - LAYER 0 VOIDS
// ===========================================================================

sig FailureMode {
  steward: lone Agent,
  successor: lone Agent,
  reporters: set Agent,
  interested: set Agent       // parties structurally incentivized to deny it
}

// The checks as architecture_check performs them.
pred apA[m: FailureMode]  { no m.steward }
pred ap1b[m: FailureMode] { no m.successor or m.successor = m.steward }
pred apF[m: FailureMode]  { some m.reporters and m.reporters in m.interested }

// AP.1b: "A single named steward with no registered successor is a single
// point of failure." So: when neither AP-A nor AP.1b fires, losing any one
// agent still leaves someone named for the failure mode.
assert NoSinglePointOfStewardship {
  all m: FailureMode, gone: Agent |
    (not apA[m] and not ap1b[m]) implies some (m.steward + m.successor) - gone
}

// AP.6 / AP-F: when the channel is not captured and someone reports, an
// independent (non-interested) reporter exists.
assert UncapturedMeansIndependentReporter {
  all m: FailureMode |
    (some m.reporters and not apF[m]) implies some m.reporters - m.interested
}

// ===========================================================================
// SCENE 4 - THE COMMANDS
// ===========================================================================

check RestatementIsNotEvidence              for 5 but 4 Time
check NonEESKindsNeverClose                 for 5 but 4 Time
check NoSelfCertification                   for 5 but 4 Time
check EvidenceClosureHasIndependentSource   for 5 but 4 Time
check RoleSwitchIsSelfClosure               for 5 but 4 Time
check NoSinglePointOfStewardship            for 5
check UncapturedMeansIndependentReporter    for 5

// Non-vacuity: each closure type and each void can actually occur.
run SomeEvidenceClosure   { some c: Closure | c.ctype = EvidenceClosure }   for 3
run SomeRoleSwitchClosure { some c: Closure | c.ctype = RoleSwitchClosure } for 3
run SomeAuthorityClosure  { some c: Closure | c.ctype = AuthorityClosure }  for 3
run SomeCapturedChannel   { some m: FailureMode | apF[m] }                  for 3
run SomeSuccessionVoid    { some m: FailureMode | ap1b[m] and not apA[m] }  for 3

// EXEUNT - end of model.
