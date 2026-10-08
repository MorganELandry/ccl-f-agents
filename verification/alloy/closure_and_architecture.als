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
 *     loop that any evidence it cites depends on is itself chain-sound;
 *   - the decision-level independence rules (Layer 4): the evidence that a
 *     reversal path was tested (Execution Class Assignment) and the
 *     External Evidence Source cited in the decision's Rule 4 acceptance.
 * One definition of External Evidence Source serves all three: its
 * producer is neither the agent making the claim (the closing agent, the
 * class-setter, the acceptor), nor the agent accepting the decision, nor a
 * process under evaluation. The registrant is not excluded as such.
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

// External Evidence Source for a closure: an eligible kind, produced by
// neither the agent making the claim (the closing agent) nor the process
// under evaluation. The registrant may produce it: a registrant's own
// measurement can close a loop someone else closes.
pred ees[e: Evidence, c: Closure] {
  e.kind in EESKinds
  e.producer not in c.closer + c.signal.evaluated
}

pred qualifies[c: Closure] { some e: c.cites | novel[e, c.signal] and ees[e, c] }

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

// Neither the closing agent nor the process under evaluation can close a
// signal by evidence it produced itself.
assert NoSelfCertification {
  all c: Closure |
    c.cites.producer in (c.signal.evaluated + c.closer)
      implies c.ctype != EvidenceClosure
}

// An evidence closure always rests on at least one independent producer.
assert EvidenceClosureHasIndependentSource {
  all c: Closure | c.ctype = EvidenceClosure implies
    some e: c.cites | e.producer not in c.signal.evaluated + c.closer
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
// evidence closure and EVERY item of whose cited evidence has its upstream
// loops all sound already ("Citing an item is relying on it, so every
// cited item is load-bearing"). Step mirrors that iteration; with at least
// one more Step than there are Signals, the last Step holds the answer.
// Exits are not modeled here, so "resolved" upstream means sound; the
// TLA+ model also counts an upstream supersession.
// ===========================================================================

sig Step { snd: set Signal }

// The qualifying evidence of a signal's current closure (novel and EES).
fun qual[s: Signal] : set Evidence {
  { e: s.current.cites | novel[e, s] and ees[e, s.current] }
}

// One round of the iteration: loops supported by the set `known`.
fun grow[known: set Signal] : set Signal {
  { s: Signal | s.current.ctype = EvidenceClosure
                and all e: s.current.cites | e.dependsOn in known }
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

// A loop citing any item that depends on the loop itself is never sound
// ("A loop cannot be its own upstream").
assert SelfSupportNeverSound {
  all s: Signal | (some e: s.current.cites | s in e.dependsOn) implies s not in Sound
}

// Two loops each citing evidence that rests on the other are never sound.
assert MutualSupportNeverSound {
  all disj s, t: Signal |
    ((some e: s.current.cites | t in e.dependsOn) and (some e: t.current.cites | s in e.dependsOn))
      implies (s + t) & Sound = none
}

// Evidence resting on a loop not closed by evidence makes nothing sound:
// if any cited item depends on such a loop, the closure doesn't count.
assert NonEvidenceUpstreamBreaksTheChain {
  all s: Signal |
    (some e: s.current.cites | some u: e.dependsOn | u.current.ctype != EvidenceClosure)
      implies s not in Sound
}

// Everything sound is closed by evidence, and every item it cites rests
// only on sound loops, all the way up.
assert SoundAllTheWayUp {
  all s: Sound | s.current.ctype = EvidenceClosure
    and all e: s.current.cites | e.dependsOn in Sound
}

// Weakest link: one clean item does not carry the others. A loop citing
// any item that rests on a loop not sound is not sound, however good its
// other items are (the rule before October 2026 needed only one item).
assert OneCleanItemDoesNotCarryTheRest {
  all s: Signal | (some e: s.current.cites | some e.dependsOn - Sound) implies s not in Sound
}

// ===========================================================================
// SCENE 5 - DECISION-LEVEL INDEPENDENCE
// Execution Class Assignment: a class below irreversible applies only with
// a tested reversal path, shown by "evidence of an eligible kind produced
// by neither the agent who registered or reclassified the decision, nor the
// agent accepting it, nor a process under evaluation in its loops".
// Execution Gates: the decision's External Evidence Source is cited in its
// Rule 4 acceptance, for the principal risk claim, and produced by neither
// a process under evaluation in its loops nor the accepting agent (the
// claimant). "Evidence elsewhere in the decision's support, in its loops'
// closures, does not substitute."
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

// The decision's support for its principal risk claim: the evidence cited
// in its acceptance, and nothing else.
fun support[d: Decision] : set Evidence {
  d.acceptanceEvidence
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

// Evidence in the loops' closures never supplies it, sound or not: with
// nothing cited in the acceptance, there is none.
assert LoopClosuresNeverSupplyTheEES {
  all d: Decision | no d.acceptanceEvidence implies not decisionEES[d]
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
check OneCleanItemDoesNotCarryTheRest       for 4 but 4 Time, exactly 5 Step
check LowerClassNeedsIndependentProof       for 4 but 4 Time, exactly 5 Step
check NoSelfCertifiedReversal               for 4 but 4 Time, exactly 5 Step
check NonEESNeverSupportsReversal           for 4 but 4 Time, exactly 5 Step
check AcceptorCannotSupplyTheEES            for 4 but 4 Time, exactly 5 Step
check LoopClosuresNeverSupplyTheEES        for 4 but 4 Time, exactly 5 Step

// Non-vacuity: each closure type and each void can actually occur.
run SomeEvidenceClosure   { some c: Closure | c.ctype = EvidenceClosure }   for 3
run SomeRoleSwitchClosure { some c: Closure | c.ctype = RoleSwitchClosure } for 3
run SomeAuthorityClosure  { some c: Closure | c.ctype = AuthorityClosure }  for 3
run SomeCapturedChannel   { some m: FailureMode | apF[m] }                  for 3
run SomeSuccessionVoid    { some m: FailureMode | ap1b[m] and not apA[m] }  for 3
run SomeTwoLevelChain     { some s: Sound | some qual[s].dependsOn & Sound } for 4 but 4 Time, exactly 5 Step
run SomeUnsoundEvidenceClosure { some s: Signal | s.current.ctype = EvidenceClosure and s not in Sound } for 4 but 4 Time, exactly 5 Step
run SomeLowerClassApplied { some d: Decision | applied[d] = Routine } for 4 but 4 Time, exactly 5 Step
run SomeDecisionWithEES { some d: Decision | decisionEES[d] } for 4 but 4 Time, exactly 5 Step
run SomeRegistrantEvidenceClosure { some c: Closure | c.ctype = EvidenceClosure and c.closer != c.signal.registrant and c.cites.producer = c.signal.registrant } for 4 but 4 Time
run SomeCleanItemNotEnough { some s: Signal | s.current.ctype = EvidenceClosure and s not in Sound and some e: qual[s] | no e.dependsOn } for 4 but 4 Time, exactly 5 Step
run SomeDeclaredLowerGatedIrreversible { some d: Decision | d.declared = Routine and applied[d] = Irreversible } for 4 but 4 Time, exactly 5 Step

// EXEUNT - end of model.
