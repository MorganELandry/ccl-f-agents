/*
 * CLOSURE AND ARCHITECTURE, STRUCTURALLY
 * A Model in Six Scenes
 * =====================================
 *
 * PROLOGUE
 * An Alloy model of two CCL-F v0.2 definitions the runtime enforces:
 *   - closure typing (Layer 2): evidence closure needs evidence that is both
 *     novel (Evidence Novelty) and external (External Evidence Source);
 *     otherwise a closure is role-switch or authority closure;
 *   - the Layer 0 voids the runtime checks: AP-A (no steward), AP.1b (no
 *     successor) and AP-F (captured channel);
 *   - Closure Chain (Layer 2): an evidence closure counts only if every
 *     loop its qualifying evidence depends on is itself chain-sound;
 *   - the decision-level independence rules (Layer 4): the evidence that a
 *     reversal path was tested (Execution Class Assignment) and the
 *     decision's External Evidence Source.
 * The Alloy Analyzer searches every small instance (up to the scope in each
 * `check`) for a counterexample to each assertion, and confirms with `run`
 * that each closure type and each void can actually occur.
 *
 * Definitions mirror cclf/supervisor.py (is_novel, is_ees, attempt_closure,
 * architecture_check, _closure_sound, _reversal_supported, _applied_class,
 * _decision_ees); the assertions restate what the draft says those
 * definitions must guarantee.
 *
 * THE PLAYBILL
 *   Scene 1  the cast: agents, evidence kinds, referents, time
 *   Scene 2  closure typing, and what it must guarantee
 *   Scene 3  Layer 0 voids, and what they must guarantee
 *   Scene 4  Closure Chain, computed step by step from nothing
 *   Scene 5  decision-level independence: reversal evidence and the
 *            decision's External Evidence Source
 *   Scene 6  the commands (check = look for a counterexample; run = find
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
open util/ordering[Step] as stepord

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
  at: one Time,
  dependsOn: set Signal        // upstream loops (Closure Chain)
}

sig Signal {
  registrant: one Agent,
  evaluated: one Agent,        // the process under evaluation
  referent: one Referent,      // which referent generated the signal
  registeredAt: one Time,
  attached: set Evidence,      // evidence present at registration
  current: lone Closure        // its current (latest real) closure, if closed
}
fact { all s: Signal | s.current.signal in s }
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
// SCENE 4 - CLOSURE CHAIN
// The runtime computes chain soundness as a least fixed point: start with
// no sound loops, and repeatedly add every loop whose current closure is an
// evidence closure with at least one qualifying item whose upstream loops
// are all sound already. Step mirrors that iteration; with at least one
// more Step than there are Signals, the last Step holds the answer.
// ===========================================================================

sig Step { snd: set Signal }

// The qualifying evidence of a signal's current closure (novel and EES).
fun qual[s: Signal] : set Evidence {
  { e: s.current.cites | novel[e, s] and ees[e, s] }
}

// One round of the iteration: loops supported by the set `known`.
fun grow[known: set Signal] : set Signal {
  { s: Signal | s.current.ctype = EvidenceClosure
                and some e: qual[s] | e.dependsOn in known }
}

fact iteration {
  no stepord/first.snd
  all st: Step - stepord/last | st.(stepord/next).snd = grow[st.snd]
}

fun Sound : set Signal { stepord/last.snd }

// A candidate set of loops, to test that Sound is the LEAST closed set.
sig Candidate { xs: set Signal }

// Enough steps: one more round changes nothing (Sound is a fixed point).
assert SoundIsAFixedPoint { grow[Sound] = Sound }

// Least: any set closed under one round contains Sound, so cycles and
// other self-supporting structures never count.
assert SoundIsLeast { all c: Candidate | grow[c.xs] in c.xs implies Sound in c.xs }

// A loop whose every qualifying item depends on the loop itself is never
// sound ("A loop cannot be its own upstream").
assert SelfSupportNeverSound {
  all s: Signal | (all e: qual[s] | s in e.dependsOn) implies s not in Sound
}

// Two loops each resting only on the other are never sound.
assert MutualSupportNeverSound {
  all disj s, t: Signal |
    ((all e: qual[s] | t in e.dependsOn) and (all e: qual[t] | s in e.dependsOn))
      implies (s + t) & Sound = none
}

// Evidence resting on a loop not closed by evidence makes nothing sound:
// if every qualifying item depends on such a loop, the closure doesn't count.
assert NonEvidenceUpstreamBreaksTheChain {
  all s: Signal |
    (all e: qual[s] | some u: e.dependsOn | u.current.ctype != EvidenceClosure)
      implies s not in Sound
}

// Everything sound is closed by evidence, all the way up.
assert SoundAllTheWayUp {
  all s: Sound | s.current.ctype = EvidenceClosure
    and some e: qual[s] | e.dependsOn in Sound
}

// ===========================================================================
// SCENE 5 - DECISION-LEVEL INDEPENDENCE
// Execution Class Assignment: a class below irreversible applies only with
// a tested reversal path, shown by "evidence of an eligible kind produced
// by neither the agent who registered or reclassified the decision, nor the
// agent accepting it, nor a process under evaluation in its loops".
// Execution Gates: the decision's External Evidence Source comes from its
// loops' chain-sound evidence closures or its Rule 4 acceptance, produced by
// neither a process under evaluation in its loops nor the accepting agent.
// ===========================================================================

abstract sig Class {}
one sig Routine, Elevated, Irreversible extends Class {}

sig Decision {
  loops: set Signal,
  setters: some Agent,                 // registered or reclassified it
  acceptor: lone Agent,
  declared: one Class,
  hasPath: lone Decision,              // non-empty = a reversal path is registered
  reversalEvidence: set Evidence,
  acceptanceEvidence: set Evidence
}
fact { all d: Decision | d.hasPath in d }

pred reversalSupported[d: Decision] {
  some d.hasPath
  some e: d.reversalEvidence |
    e.kind in EESKinds and e.producer not in d.setters + d.acceptor + d.loops.evaluated
}

fun applied[d: Decision] : one Class {
  (d.declared = Irreversible or reversalSupported[d]) => d.declared else Irreversible
}

// The decision's support: evidence cited in its acceptance, plus the
// qualifying evidence of its loops' chain-sound evidence closures.
fun support[d: Decision] : set Evidence {
  d.acceptanceEvidence + { e: Evidence | some s: d.loops & Sound | e in qual[s] }
}

pred decisionEES[d: Decision] {
  some e: support[d] | e.kind in EESKinds and e.producer not in d.loops.evaluated + d.acceptor
}

// "Every execution-class decision is irreversible unless shown otherwise."
assert LowerClassNeedsIndependentProof {
  all d: Decision | applied[d] != Irreversible implies
    (some d.hasPath and some e: d.reversalEvidence |
       e.kind in EESKinds and e.producer not in d.setters + d.acceptor)
}

// No one can vouch for their own reversal path: if every piece of reversal
// evidence came from someone who set the class or accepts the decision, it
// is gated as irreversible.
assert NoSelfCertifiedReversal {
  all d: Decision | d.reversalEvidence.producer in d.setters + d.acceptor
    implies applied[d] = Irreversible
}

// Model output, assertions and internal analysis never show a path tested.
assert NonEESNeverSupportsReversal {
  all d: Decision | d.reversalEvidence.kind in (InternalAnalysis + Assertion + ModelOutput)
    implies applied[d] = Irreversible
}

// A decision supported only by its acceptor's own evidence has no External
// Evidence Source ("A decision reasoned through entirely inside one
// process ... does not meet this requirement").
assert AcceptorCannotSupplyTheEES {
  all d: Decision | support[d].producer in d.acceptor implies not decisionEES[d]
}

// Evidence inside a closure that isn't chain-sound never supplies it: with
// nothing cited in the acceptance and no sound loop, there is none.
assert UnsoundClosuresNeverSupplyTheEES {
  all d: Decision | (no d.acceptanceEvidence and no d.loops & Sound)
    implies not decisionEES[d]
}

// ===========================================================================
// SCENE 6 - THE COMMANDS
// ===========================================================================

check RestatementIsNotEvidence              for 5 but 4 Time
check NonEESKindsNeverClose                 for 5 but 4 Time
check NoSelfCertification                   for 5 but 4 Time
check EvidenceClosureHasIndependentSource   for 5 but 4 Time
check RoleSwitchIsSelfClosure               for 5 but 4 Time
check NoSinglePointOfStewardship            for 5
check UncapturedMeansIndependentReporter    for 5
check SoundIsAFixedPoint                    for 4 but 4 Time, exactly 5 Step
check SoundIsLeast                          for 4 but 4 Time, exactly 5 Step
check SelfSupportNeverSound                 for 4 but 4 Time, exactly 5 Step
check MutualSupportNeverSound               for 4 but 4 Time, exactly 5 Step
check NonEvidenceUpstreamBreaksTheChain     for 4 but 4 Time, exactly 5 Step
check SoundAllTheWayUp                      for 4 but 4 Time, exactly 5 Step
check LowerClassNeedsIndependentProof       for 4 but 4 Time, exactly 5 Step
check NoSelfCertifiedReversal               for 4 but 4 Time, exactly 5 Step
check NonEESNeverSupportsReversal           for 4 but 4 Time, exactly 5 Step
check AcceptorCannotSupplyTheEES            for 4 but 4 Time, exactly 5 Step
check UnsoundClosuresNeverSupplyTheEES      for 4 but 4 Time, exactly 5 Step

// Non-vacuity: each closure type and each void can actually occur.
run SomeEvidenceClosure   { some c: Closure | c.ctype = EvidenceClosure }   for 3
run SomeRoleSwitchClosure { some c: Closure | c.ctype = RoleSwitchClosure } for 3
run SomeAuthorityClosure  { some c: Closure | c.ctype = AuthorityClosure }  for 3
run SomeCapturedChannel   { some m: FailureMode | apF[m] }                  for 3
run SomeSuccessionVoid    { some m: FailureMode | ap1b[m] and not apA[m] }  for 3
run SomeTwoLevelChain     { some s: Sound | some qual[s].dependsOn & Sound } for 4 but 4 Time, exactly 5 Step
run SomeUnsoundEvidenceClosure { some s: Signal | s.current.ctype = EvidenceClosure and s not in Sound } for 4 but 4 Time, exactly 5 Step
run SomeLowerClassApplied { some d: Decision | applied[d] = Routine } for 4 but 4 Time, exactly 5 Step
run SomeDecisionWithEES { some d: Decision | decisionEES[d] and no d.acceptanceEvidence } for 4 but 4 Time, exactly 5 Step
run SomeDeclaredLowerGatedIrreversible { some d: Decision | d.declared = Routine and applied[d] = Irreversible } for 4 but 4 Time, exactly 5 Step

// EXEUNT - end of model.
