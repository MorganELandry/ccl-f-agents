------------------------- MODULE CommitmentStateMachine -------------------------
(***************************************************************************)
(* THE STATE MACHINE, FORMALLY                                             *)
(* A Model in Five Scenes                                                  *)
(*                                                                         *)
(* PROLOGUE                                                                *)
(* A TLA+ model of the CCL-F v0.2 Layer 4 Commitment State Machine,        *)
(* checked by the TLC model checker. TLC explores every reachable state    *)
(* of a small system (two signals, one irreversible decision, a bounded    *)
(* audit log) and confirms that no sequence of steps breaks a property.    *)
(*                                                                         *)
(* What it covers: the transition table, the exits and their re-entry      *)
(* rules, the Rule 8 recovery condition, the append-only audit log,        *)
(* Rule 4 acceptance, the gates with their logged override, the            *)
(* post-execution latch into executed_open, Execution Class Assignment     *)
(* (irreversible by default, tested reversal path, logged                  *)
(* reclassification, the relabel-after-refusal review), the structural     *)
(* review hold and the Emergency Justification that may suspend an         *)
(* off-envelope or containment review, Closure Chain (evidence depending   *)
(* on other loops; a reopen upstream weakens every closure downstream,     *)
(* and is logged), and the decision-level External Evidence Source.        *)
(*                                                                         *)
(* Four configurations check it (see README): CommitmentStateMachine.cfg   *)
(* explores the signal lifecycle with two signals, one depending on the    *)
(* other, and a fixed irreversible decision; Classes.cfg explores every    *)
(* class, reversal and relabel path with one signal; Chain.cfg goes deep   *)
(* enough (no exits, a longer log) for a reopen to weaken a closure        *)
(* downstream; Emergency.cfg adds off-envelope and containment reviews     *)
(* and the Emergency Justification. Every property is checked in all four. *)
(* What it does NOT cover: closure typing, coherence scoring and the       *)
(* thresholds (see ../alloy and docs/DECISIONS.md). It checks the 0.2      *)
(* automaton as written; it is not the 0.3 formal semantics.               *)
(*                                                                         *)
(* THE PLAYBILL                                                            *)
(*   Scene 1  the vocabulary: states, exit types, the transition table     *)
(*   Scene 2  the variables and the starting state                         *)
(*   Scene 3  the steps a system may take (the Next relation)              *)
(*   Scene 4  the properties TLC must never see broken                     *)
(*   Scene 5  the specification                                            *)
(*                                                                         *)
(* READER'S NOTE: how to read TLA+                                         *)
(*   x' is the value of variable x in the NEXT state. An action is a      *)
(*   formula relating the current state to the next one; it is "enabled"   *)
(*   only when it can be true. [][A]_v means "every step either satisfies  *)
(*   A or leaves v unchanged". UNCHANGED v means v' = v.                   *)
(*                                                                         *)
(* READER'S NOTE: one table, two readers                                   *)
(*   Transitions (Scene 1) is a copy of cclf/statemachine.py TRANSITIONS.  *)
(*   tests/test_verification.py parses both and fails if they differ, so   *)
(*   the model and the code cannot drift apart silently.                   *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS Signals,        \* the signals in the model, e.g. {s1, s2}
          MaxLog,         \* bound on audit-log length, to keep the search finite
          DeclaredInit,   \* execution classes the decision may be registered with
          ReversalInit,   \* whether a tested reversal path may exist at registration
          Reclassify,     \* TRUE: explore relabels, refusals and the relabel review
          UpFrom, UpTo,   \* Closure Chain: UpFrom's closing evidence depends on
                          \* loop UpTo (a value outside Signals means no edge)
          CycleBack,      \* TRUE: UpTo's evidence also depends on UpFrom (a cycle)
          Exits,          \* TRUE: explore loop exits (FALSE keeps Chain.cfg small)
          EnvTriggers     \* the classification reviews that may open: a subset of
                          \* {"off_envelope", "containment"} ({} turns them off)

(***************************************************************************)
(* SCENE 1 - THE VOCABULARY                                                *)
(***************************************************************************)

\* The commitment states of Layer 4 ("exited" carries its type separately).
\* trajectory_lock and executed_open are terminal.
States == {"unregistered", "registered", "classified", "under_review",
           "closed_evidence", "closed_authority", "closed_role_switch",
           "suppressed", "escalated", "trajectory_lock", "executed_open", "exited"}

Closed     == {"closed_evidence", "closed_authority", "closed_role_switch"}
OpenStates == {"registered", "classified", "under_review", "suppressed", "escalated"}

\* The fourteen exit types of the Layer 2 Loop Exit Taxonomy.
ExitTypes == {"terminal", "containment", "recoverable", "superseded", "delegated",
              "deferred", "forced", "exhaustion", "boundary", "timeout",
              "ambiguity", "whistleblower", "legal", "key_person"}

\* Re-entry groups, one per kind of line in the spec's EXIT TRANSITIONS.
ReentryStated         == {"recoverable", "delegated"}
ReentryNeedsSuccessor == {"forced", "key_person"}            \* inferred from AP.1b
ReentryInferredFree   == {"exhaustion"}                      \* inferred, no condition
WaitingExits          == {"containment", "deferred", "ambiguity"} \* on a registered condition
\* boundary: inferred, needs a different agent; legal: sub-type and lifted.

LegalSubtypes  == {"regulatory_intervention", "judicial_order",
                   "statutory_trigger", "investigative_hold"}
LegalResumable == {"regulatory_intervention", "investigative_hold"}

\* BEGIN TRANSITIONS (machine-read by tests/test_verification.py)
Transitions ==
  { <<"unregistered", "registered">>,
    <<"registered", "classified">>,
    <<"classified", "under_review">>,
    <<"under_review", "closed_evidence">>,
    <<"under_review", "closed_authority">>,
    <<"under_review", "closed_role_switch">>,
    <<"under_review", "suppressed">>,
    <<"under_review", "escalated">>,
    <<"under_review", "trajectory_lock">>,
    <<"escalated", "under_review">>,
    <<"suppressed", "under_review">>,
    <<"closed_evidence", "under_review">>,
    <<"closed_authority", "under_review">>,
    <<"closed_role_switch", "under_review">>,
    <<"registered", "executed_open">>,
    <<"classified", "executed_open">>,
    <<"under_review", "executed_open">>,
    <<"suppressed", "executed_open">>,
    <<"escalated", "executed_open">>,
    <<"closed_evidence", "executed_open">>,
    <<"closed_authority", "executed_open">>,
    <<"closed_role_switch", "executed_open">>,
    <<"exited", "executed_open">> }
\* END TRANSITIONS
\* The last nine pairs are the POST-EXECUTION LATCH ("any loop not resolved
\* at irreversible execution -> executed_open"). Only an irreversible
\* override or Emergency Justification takes them (see Latch, Scene 3).

(***************************************************************************)
(* SCENE 2 - THE VARIABLES                                                 *)
(*   state[s]        commitment state of signal s                          *)
(*   exitType[s]     its exit type once exited, else "none"                *)
(*   legal[s]        its legal sub-type for a legal exit, else "none"      *)
(*   cond[s]         a resolution condition was registered at its exit     *)
(*   modelUpdate[s]  a Rule 8 model update has been documented for it      *)
(*   accepted        Rule 4 acceptance given for the decision              *)
(*   declared        the decision's declared execution class               *)
(*   reversal        a reversal path is registered AND backed by an EES    *)
(*                   showing it was tested (who produced the evidence is   *)
(*                   abstracted away; the Python tests cover that)         *)
(*   everBlocked     some execution request on the decision was refused    *)
(*   relabel         the relabel-after-refusal review: "none", "open" or   *)
(*                   "resolved"                                            *)
(*   accEES          the Rule 4 acceptance cites an External Evidence      *)
(*                   Source for the principal risk claim (who produced it  *)
(*                   is abstracted away)                                   *)
(*   executed        the irreversible decision has executed                *)
(*   log             the audit log: a sequence of records                  *)
(*   envRev[s]       the trigger of an unresolved off-envelope or          *)
(*                   containment review on s, else "none". These are the   *)
(*                   suspendable reviews. The other reviews are not        *)
(*                   suspendable, and are represented where they already   *)
(*                   live: an escalated or suppressed signal (recurrence,  *)
(*                   suppression) and relabel (the relabel review).        *)
(*   ruleRev[s]      an unresolved review that only a Rule 8 model update  *)
(*                   resolves (recurrence, credibility discounting, ...)   *)
(*                   escalated s. Not suspendable. An escalated signal     *)
(*                   with ruleRev FALSE and envRev set is held ONLY by an  *)
(*                   off-envelope or containment review: the runtime       *)
(*                   escalates a signal in review when such a review names *)
(*                   it, and lets an Emergency Justification suspend it.   *)
(***************************************************************************)
VARIABLES state, exitType, legal, cond, modelUpdate, accepted, executed, log,
          declared, reversal, everBlocked, relabel, accEES, envRev, ruleRev

vars == <<state, exitType, legal, cond, modelUpdate, accepted, executed, log,
          declared, reversal, everBlocked, relabel, accEES, envRev, ruleRev>>

\* The decision and review variables, for UNCHANGED clauses.
classVars == <<declared, reversal, everBlocked, relabel, accEES, envRev, ruleRev>>

Classes == {"routine", "elevated", "irreversible"}
Rank == [c \in Classes |-> IF c = "routine" THEN 0 ELSE IF c = "elevated" THEN 1 ELSE 2]

\* Execution Class Assignment: the declared class applies only if it is
\* irreversible or a tested reversal path supports it.
Applied(d, r) == IF d = "irreversible" \/ r THEN d ELSE "irreversible"
AppliedNow == Applied(declared, reversal)

Init == /\ state       = [s \in Signals |-> "unregistered"]
        /\ exitType    = [s \in Signals |-> "none"]
        /\ legal       = [s \in Signals |-> "none"]
        /\ cond        = [s \in Signals |-> FALSE]
        /\ modelUpdate = [s \in Signals |-> FALSE]
        /\ accepted    = FALSE
        /\ executed    = FALSE
        /\ log         = <<>>
        /\ declared    \in DeclaredInit
        /\ reversal    \in ReversalInit
        /\ everBlocked = FALSE
        /\ relabel     = "none"
        /\ accEES      = FALSE
        /\ envRev      = [s \in Signals |-> "none"]
        /\ ruleRev     = [s \in Signals |-> FALSE]

\* Every log record has the same fields; unused ones hold "none".
Rec(kind, sig, from, to) ==
  [kind |-> kind, sig |-> sig, from |-> from, to |-> to]

Log(r) == log' = Append(log, r)

\* The dependency edges <<s, u>>: "s's closing evidence depends on loop u".
\* (TLC configuration files cannot write pairs, so they are built here.)
Upstream == IF UpFrom \in Signals /\ UpTo \in Signals
              THEN {<<UpFrom, UpTo>>} \cup (IF CycleBack THEN {<<UpTo, UpFrom>>} ELSE {})
              ELSE {}

\* Closure Chain, computed as the runtime computes it: start from no sound
\* loops and repeatedly add every evidence-closed loop whose upstream loops
\* are all resolved already, that is sound, or exited as superseded (the
\* External Evidence Source a supersession needs is abstracted away, as
\* the gate's is); |Signals| rounds reach the least fixed point, so a loop
\* held up only by a cycle never counts. (One closing evidence item per
\* loop, so "every cited item" and "the item" coincide here: Upstream gives
\* its dependencies. The Alloy model checks several items per closure.)
RECURSIVE SoundIter(_, _, _, _)
SoundIter(st, xt, known, k) ==
  IF k = 0 THEN known
  ELSE SoundIter(st, xt, {s \in Signals : st[s] = "closed_evidence"
                                     /\ \A u \in Signals : <<s, u>> \in Upstream =>
                                          \/ u \in known
                                          \/ st[u] = "exited" /\ xt[u] = "superseded"},
                 k - 1)
SoundOf(st, xt) == SoundIter(st, xt, {}, Cardinality(Signals))
Sound == SoundOf(state, exitType)

\* The transitive closure of Upstream (for the cycle property).
RECURSIVE TCIter(_, _)
TCIter(R, k) == IF k = 0 THEN R
                ELSE TCIter(R \cup {p \in Signals \X Signals :
                                     \E b \in Signals : <<p[1], b>> \in R /\ <<b, p[2]>> \in R},
                            k - 1)
UpstreamTC == TCIter(Upstream, Cardinality(Signals))

\* A set as a sequence, in some fixed order (for logging several records).
RECURSIVE SetToSeq(_)
SetToSeq(X) == IF X = {} THEN <<>>
               ELSE LET x == CHOOSE x \in X : TRUE IN <<x>> \o SetToSeq(X \ {x})

(***************************************************************************)
(* SCENE 3 - THE STEPS                                                     *)
(***************************************************************************)

\* Pending escalation: a signal that arrives in review while an unresolved
\* off-envelope or containment review names it is escalated at once, in
\* the same step (the runtime's _apply_pending_escalations), so it cannot
\* slip into review and be closed while that review is open. Arrive(s) is
\* where it lands; ArriveRecs(s) is the extra record that logs it.
Arrive(s)     == IF envRev[s] /= "none" THEN "escalated" ELSE "under_review"
ArriveRecs(s) == IF envRev[s] /= "none"
                   THEN <<Rec("transition", s, "under_review", "escalated")>> ELSE <<>>

\* An ordinary move along the table. Reopen, escalation, recovery and the
\* latch have their own actions below, because the spec attaches
\* conditions to them.
Move(s, t) ==
  LET extra == IF t = "under_review" THEN ArriveRecs(s) ELSE <<>>
  IN /\ <<state[s], t>> \in Transitions
     /\ t /= "executed_open"           \* the latch: see Override and Emergency
     /\ t /= "escalated"               \* escalation: see Escalate
     /\ state[s] \notin Closed         \* reopening: see Reopen
     /\ state[s] /= "escalated"        \* recovery: see Recover
     /\ Len(log) + 1 + Len(extra) <= MaxLog
     /\ state' = [state EXCEPT ![s] = IF t = "under_review" THEN Arrive(s) ELSE t]
     /\ log' = log \o <<Rec("transition", s, state[s], t)>> \o extra
     /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* "A closed loop cannot be silently reopened": the reopen is its own
\* logged record (rationale, reopening agent, superseded closure).
\* Closure Chain: every closure downstream that loses its standing because
\* of this reopen is logged too ("the weakened link is logged").
Reopen(s) ==
  LET after    == [state EXCEPT ![s] = Arrive(s)]
      weakened == (Sound \ SoundOf(after, exitType)) \ {s}
  IN /\ state[s] \in Closed
     /\ <<state[s], "under_review">> \in Transitions
     /\ Len(log) + 1 + Len(ArriveRecs(s)) + Cardinality(weakened) <= MaxLog
     /\ state' = after
     /\ log' = log \o <<Rec("reopen", s, state[s], "under_review")>> \o ArriveRecs(s)
                   \o [i \in 1..Cardinality(weakened) |->
                         Rec("chain_weakened", SetToSeq(weakened)[i], "upstream", s)]
     /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* under_review -> escalated: an escalation condition that only a Rule 8
\* model update resolves (recurrence, credibility discounting, ...) opens a
\* structural review over the signal. Such a review may also join a signal
\* already escalated by an off-envelope or containment review alone; it
\* then holds the signal too, and that hold cannot be suspended.
Escalate(s) ==
  /\ \/ state[s] = "under_review"
     \/ state[s] = "escalated" /\ ~ruleRev[s] /\ envRev[s] /= "none"
  /\ <<"under_review", "escalated">> \in Transitions
  /\ state'       = [state       EXCEPT ![s] = "escalated"]
  /\ ruleRev'     = [ruleRev     EXCEPT ![s] = TRUE]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = FALSE]
  /\ Log(IF state[s] = "under_review" THEN Rec("transition", s, "under_review", "escalated")
                                      ELSE Rec("escalation", s, "none", "rule8"))
  /\ UNCHANGED <<exitType, legal, cond, accepted, executed,
                 declared, reversal, everBlocked, relabel, accEES, envRev>>

\* Rule 8: structural review documents a model update, which resolves the
\* review that escalated the signal.
DocumentModelUpdate(s) ==
  /\ state[s] = "escalated"
  /\ ruleRev[s]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = TRUE]
  /\ ruleRev'     = [ruleRev     EXCEPT ![s] = FALSE]
  /\ Log(Rec("model_update", s, "escalated", "escalated"))
  /\ UNCHANGED <<state, exitType, legal, cond, accepted, executed,
                 declared, reversal, everBlocked, relabel, accEES, envRev>>

\* escalated -> under_review, only once the model update is on record and
\* no off-envelope or containment review still holds the signal.
Recover(s) ==
  /\ state[s] = "escalated"
  /\ <<"escalated", "under_review">> \in Transitions
  /\ modelUpdate[s]
  /\ envRev[s] = "none"
  /\ state' = [state EXCEPT ![s] = "under_review"]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = FALSE]
  /\ Log(Rec("transition", s, "escalated", "under_review"))
  /\ UNCHANGED <<exitType, legal, cond, accepted, executed>> /\ UNCHANGED classVars

\* any open state -> exited(type). A legal exit records its sub-type; a
\* containment, deferred or ambiguity exit may register a resolution
\* condition (c), and no other exit type does.
Exit(s, x, sub, c) ==
  /\ Exits
  /\ state[s] \in OpenStates
  /\ (x = "legal") = (sub /= "none")
  /\ c => x \in WaitingExits
  /\ state'    = [state    EXCEPT ![s] = "exited"]
  /\ exitType' = [exitType EXCEPT ![s] = x]
  /\ legal'    = [legal    EXCEPT ![s] = sub]
  /\ cond'     = [cond     EXCEPT ![s] = c]
  /\ Log(Rec("exit", s, state[s], x))
  /\ UNCHANGED <<modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* May an exit of type x (legal sub-type sub) re-enter, given whether a
\* successor is registered, the resumer differs, a legal hold is lifted,
\* a resolution condition was registered, and it is met?
ReentryAllowed(x, sub, hasSuccessor, resumerDiffers, lifted, hasCond, met) ==
  \/ x \in ReentryStated
  \/ x \in ReentryNeedsSuccessor /\ hasSuccessor
  \/ x \in ReentryInferredFree
  \/ x = "boundary" /\ resumerDiffers
  \/ x = "legal" /\ sub \in LegalResumable /\ lifted
  \/ x \in WaitingExits /\ hasCond /\ met

\* exited -> under_review. The outside conditions are chosen freely by TLC
\* (\E ... \in BOOLEAN), so every combination is explored; whether a
\* resolution condition was registered comes from the exit itself.
Reenter(s) ==
  \E hasSuccessor, resumerDiffers, lifted, met \in BOOLEAN :
    /\ state[s] = "exited"
    /\ ReentryAllowed(exitType[s], legal[s], hasSuccessor, resumerDiffers, lifted,
                      cond[s], met)
    /\ Len(log) + 1 + Len(ArriveRecs(s)) <= MaxLog
    /\ state'    = [state    EXCEPT ![s] = Arrive(s)]
    /\ exitType' = [exitType EXCEPT ![s] = "none"]
    /\ legal'    = [legal    EXCEPT ![s] = "none"]
    /\ cond'     = [cond     EXCEPT ![s] = FALSE]
    /\ log'      = log \o <<Rec("reentry", s, "exited", "under_review")>> \o ArriveRecs(s)
    /\ UNCHANGED <<modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* Rule 4: someone explicitly accepts authorization, risk and rationale.
\* e: whether the acceptance cites an External Evidence Source for the
\* decision's principal risk claim.
Accept(e) ==
  /\ ~accepted
  /\ accepted' = TRUE
  /\ accEES' = e
  /\ Log(Rec("acceptance", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, executed,
                 declared, reversal, everBlocked, relabel, envRev, ruleRev>>

\* Escalation Conditions: classifying a signal off-envelope or containment
\* opens a structural review (t says which). The model does not track the
\* operational state itself, only the review it opens. As in the runtime,
\* any registered signal may be (re)classified so, whatever its commitment
\* state (the first classification's registered -> classified is the
\* table's own step, taken first). A signal under review is escalated in
\* the same step, and the move is logged; one not yet in review is
\* escalated when it arrives (Arrive). One such review per signal at a
\* time: the runtime keeps one per trigger.
OpenEnvReview(s, t) ==
  LET esc == state[s] = "under_review"
  IN /\ t \in EnvTriggers
     /\ ~executed
     /\ envRev[s] = "none"
     /\ state[s] \notin {"unregistered", "registered"}
     /\ Len(log) + (IF esc THEN 2 ELSE 1) <= MaxLog
     /\ envRev' = [envRev EXCEPT ![s] = t]
     /\ state'  = IF esc THEN [state EXCEPT ![s] = "escalated"] ELSE state
     /\ log'    = log \o <<Rec("escalation", s, "none", t)>>
                      \o (IF esc THEN <<Rec("transition", s, "under_review", "escalated")>>
                                 ELSE <<>>)
     /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted, executed,
                    declared, reversal, everBlocked, relabel, accEES, ruleRev>>

\* The review is resolved by what its trigger requires: evidence-based
\* reclassification for off-envelope, independent steward review for
\* containment (who resolves it, and with what, is checked by the Python
\* tests). An escalated signal that no other review holds (no Rule 8
\* review outstanding) recovers to under_review in the same step, logged.
\* After an Emergency Justification the review is still resolved, later;
\* the signal it named is executed_open by then and stays there.
ResolveEnvReview(s) ==
  LET release == state[s] = "escalated" /\ ~ruleRev[s]
  IN /\ envRev[s] /= "none"
     /\ Len(log) + (IF release THEN 2 ELSE 1) <= MaxLog
     /\ envRev' = [envRev EXCEPT ![s] = "none"]
     /\ state'  = IF release THEN [state EXCEPT ![s] = "under_review"] ELSE state
     /\ modelUpdate' = IF release THEN [modelUpdate EXCEPT ![s] = FALSE] ELSE modelUpdate
     /\ log'    = log \o <<Rec("review_resolved", s, envRev[s], "none")>>
                      \o (IF release THEN <<Rec("transition", s, "escalated", "under_review")>>
                                     ELSE <<>>)
     /\ UNCHANGED <<exitType, legal, cond, accepted, executed,
                    declared, reversal, everBlocked, relabel, accEES, ruleRev>>

\* Exits whose "Loop State After" leaves the loop open.
LeavesOpen == {"containment", "recoverable", "delegated", "deferred", "forced",
               "exhaustion", "boundary", "ambiguity", "key_person"}

IsOpen(s) == \/ state[s] \in OpenStates
             \/ state[s] = "exited" /\ exitType[s] \in LeavesOpen

\* The irreversible gate, reduced to the requirements this model can see.
\* Every signal is treated as a constraint, and a constraint counts as
\* resolved only if closed by a chain-sound evidence closure or exited as
\* superseded (Execution Gates, operational definitions). Authority and
\* role-switch closures do not satisfy it (Reversibility Logic), and
\* neither does any other exit: a terminal exit "needs no evidence at all".
\* The External Evidence Source a supersession needs is abstracted away.
ResolvingExits == {"superseded"}
Resolved(s) == \/ s \in Sound
               \/ state[s] = "exited" /\ exitType[s] \in ResolvingExits
\* Decision-level External Evidence Source: cited in the Rule 4 acceptance
\* for the principal risk claim. "Evidence elsewhere in the decision's
\* support, in its loops' closures, does not substitute."
DecisionEES == accEES
GateOK == /\ \A s \in Signals :
               \/ s \in Sound
               \/ state[s] = "exited" /\ exitType[s] \in ResolvingExits
          /\ DecisionEES

\* The elevated and routine gates, reduced the same way: routine needs
\* every signal registered; elevated also needs each one at least
\* classified (classification acknowledged, open loops documented).
GateElevated == \A s \in Signals : state[s] \notin {"unregistered", "registered"}
GateRoutine  == \A s \in Signals : state[s] /= "unregistered"
GateFor(c) == CASE c = "irreversible" -> GateOK
                [] c = "elevated"     -> GateElevated
                [] c = "routine"      -> GateRoutine

\* An unresolved relabel review blocks execution at every class, override
\* included.
RelabelOpen == relabel = "open"

\* A structural review holds an irreversible decision: nothing executes
\* past it, clean or by override (Layer 4, Overrides). Two kinds:
\*   not suspendable: an escalated signal is held by an unresolved review
\*     (only a documented Rule 8 model update releases it), and a
\*     suppressed one opens a review at the very request (Escalation
\*     Conditions: "Suppressed signal detected before irreversible
\*     execution"). No emergency justifies proceeding past these.
\*   suspendable: an off-envelope or containment review (envRev). Only an
\*     Emergency Justification proceeds past it, and only when it is all
\*     that holds the decision.
\*   An escalated signal held ONLY by an off-envelope or containment
\*   review (no Rule 8 review outstanding: EnvOnly) is of the second
\*   kind, as in the runtime, which judges the reviews, not the state.
HeldStates == {"escalated", "suppressed"}
EnvOnly(s) == state[s] = "escalated" /\ ~ruleRev[s] /\ envRev[s] /= "none"
NonSuspendableHeld == \E s \in Signals : state[s] \in HeldStates /\ ~EnvOnly(s)
SuspendableHeld    == \E s \in Signals : envRev[s] /= "none"
ReviewHold == AppliedNow = "irreversible" /\ (NonSuspendableHeld \/ SuspendableHeld)

\* POST-EXECUTION LATCH: at an irreversible execution under an open-loop
\* authorization, every loop the gate did not count as resolved moves to
\* executed_open, whatever state it was in: open, closed by authority or
\* role switch, closed by evidence that is not chain-sound, or exited by
\* any type but superseded. Resolved loops keep their state; terminal ones
\* (trajectory_lock, executed_open) and never-registered ones are left as
\* they are. A loop exited to an external process (whistleblower, legal)
\* keeps its exit state too: "it continues elsewhere, and carries the
\* authorization record as an annotation" (the annotation itself is not
\* modeled). It still fails the gate.
ExternalExits == {"whistleblower", "legal"}
External(s) == state[s] = "exited" /\ exitType[s] \in ExternalExits
Latch == [s \in Signals |->
            IF state[s] \notin {"unregistered", "trajectory_lock", "executed_open"} /\ ~Resolved(s)
               /\ ~External(s)
              THEN "executed_open" ELSE state[s]]

\* Clean execution: accepted, no relabel review open, no structural review
\* holding an irreversible decision, and the gate for the APPLIED class
\* passes.
Execute ==
  /\ accepted /\ ~executed /\ ~RelabelOpen /\ ~ReviewHold /\ GateFor(AppliedNow)
  /\ executed' = TRUE
  /\ Log(Rec("execution_permitted", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted>> /\ UNCHANGED classVars

\* Override: accepted, no relabel review open, no structural review holding
\* an irreversible decision, the applied gate fails, and the override is
\* logged. At the irreversible class the override is the open-loop
\* authorization: every loop not resolved is latched into executed_open,
\* and the open-loop marker is logged too; a lower class latches nothing.
\* The override never produces trajectory_lock. (That the overrider is
\* not the accepting agent, nor reports to them, is checked by the Python
\* tests; this model has no identities.)
Override ==
  /\ accepted /\ ~executed /\ ~RelabelOpen /\ ~ReviewHold /\ ~GateFor(AppliedNow)
  /\ Len(log) + 2 <= MaxLog
  /\ executed' = TRUE
  /\ IF AppliedNow = "irreversible"
       THEN /\ state' = Latch
            /\ log' = log \o << Rec("gate_override", "none", "none", "none"),
                               Rec("open_loop_irreversible_execution", "none", "none", "none") >>
       ELSE /\ state' = state
            /\ log' = Append(log, Rec("gate_override", "none", "none", "none"))
  /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted>> /\ UNCHANGED classVars

\* Emergency Justification: an irreversible decision held ONLY by
\* off-envelope or containment reviews may proceed before they are
\* resolved, and under no other condition. Never past a missing Rule 4
\* acceptance or an open relabel review. The justification is the
\* open-loop authorization for every other gate failure too, so the latch
\* applies. It suspends the holding reviews and does not resolve them
\* (envRev is unchanged), and it opens the mandatory post-event review.
\* Its five elements, who gives it, and the per-failure-mode count are
\* checked by the Python tests; this model has one decision and no
\* identities.
Emergency ==
  /\ accepted /\ ~executed /\ ~RelabelOpen
  /\ AppliedNow = "irreversible"
  /\ ~NonSuspendableHeld                  \* EJ: no non-suspendable review
  /\ SuspendableHeld                      \* EJ: held by a suspendable one
  /\ Len(log) + 2 <= MaxLog
  /\ executed' = TRUE
  /\ state' = Latch
  /\ log' = log \o << Rec("emergency_justification", "none", "none", "none"),
                     Rec("post_event_review", "none", "none", "none") >>
  /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted>>
  /\ UNCHANGED classVars                  \* EJ: the holding reviews stay unresolved

\* A refused execution request: no acceptance, a relabel review open, a
\* structural review holding the decision, or the applied gate fails (and
\* no override is given). Recorded, because a later lowering is judged
\* against it.
Refuse ==
  /\ Reclassify
  /\ ~executed
  /\ ~accepted \/ RelabelOpen \/ ReviewHold \/ ~GateFor(AppliedNow)
  /\ everBlocked' = TRUE
  /\ Log(Rec("execution_blocked", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed,
                 declared, reversal, relabel, accEES, envRev, ruleRev>>

\* Reclassify: change the declared class and/or the reversal support (new
\* evidence, or evidence replaced). Logged. A lowering of the declared or
\* the applied class after a refusal opens the relabel review.
ReclassifyTo(c, r) ==
  /\ Reclassify
  /\ ~executed
  /\ <<c, r>> /= <<declared, reversal>>
  /\ declared' = c
  /\ reversal' = r
  /\ LET lowered == \/ Rank[c] < Rank[declared]
                    \/ Rank[Applied(c, r)] < Rank[AppliedNow]
     IN relabel' = IF lowered /\ everBlocked THEN "open" ELSE relabel
  /\ Log(Rec("decision_reclassified", "none", declared, c))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed, everBlocked,
                 accEES, envRev, ruleRev>>

\* Rule 8: the relabel review is resolved by a documented model update.
ResolveRelabel ==
  /\ RelabelOpen
  /\ relabel' = "resolved"
  /\ Log(Rec("model_update", "none", "relabel", "relabel"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed,
                 declared, reversal, everBlocked, accEES, envRev, ruleRev>>

Next ==
  /\ Len(log) < MaxLog
  /\ \/ \E s \in Signals, t \in States : Move(s, t)
     \/ \E s \in Signals : Reopen(s) \/ Escalate(s) \/ DocumentModelUpdate(s) \/ Recover(s)
                           \/ Reenter(s)
     \/ \E s \in Signals, x \in ExitTypes, sub \in LegalSubtypes \cup {"none"}, c \in BOOLEAN :
          Exit(s, x, sub, c)
     \/ \E e \in BOOLEAN : Accept(e)
     \/ \E s \in Signals, t \in EnvTriggers : OpenEnvReview(s, t)
     \/ \E s \in Signals : ResolveEnvReview(s)
     \/ Execute \/ Override \/ Emergency \/ Refuse \/ ResolveRelabel
     \/ \E c \in Classes, r \in BOOLEAN : ReclassifyTo(c, r)

(***************************************************************************)
(* SCENE 4 - THE PROPERTIES                                                *)
(* Invariants hold in every reachable state. Action properties ([][P]_v)  *)
(* hold for every step.                                                    *)
(***************************************************************************)

\* Closure Chain: a loop that loses its standing is logged in the same step.
ChainWeakeningLogged ==
  [][\A w \in Signals :
       (w \in Sound /\ w \notin SoundOf(state', exitType') /\ state'[w] = state[w])
         => \E i \in Len(log) + 1 .. Len(log') :
              log'[i].kind = "chain_weakened" /\ log'[i].sig = w]_vars

\* "A loop cannot be its own upstream, directly or through others":
\* a loop on a dependency cycle is never sound. A supersession upstream
\* cuts the cycle: the superseded loop is resolved without resting on its
\* own evidence, so a loop depending on it may be sound.
CycleNeverSound ==
  \A s \in Signals :
    (<<s, s>> \in UpstreamTC
     /\ \A u \in Signals : <<s, u>> \in UpstreamTC
                             => ~(state[u] = "exited" /\ exitType[u] = "superseded"))
      => s \notin Sound

\* Sound loops are evidence-closed, and everything they depend on is
\* resolved (sound itself, or exited as superseded), all the way up.
SoundAllTheWayUp ==
  \A s \in Sound : state[s] = "closed_evidence"
                    /\ \A u \in Signals : <<s, u>> \in Upstream =>
                         \/ u \in Sound
                         \/ state[u] = "exited" /\ exitType[u] = "superseded"

\* The irreversible gate never passes cleanly over an evidence closure
\* whose chain is broken, or without an External Evidence Source cited in
\* the acceptance. (accEES, not DecisionEES, so that widening the
\* definition the gate uses cannot also widen the property.)
NoCleanPassOverBrokenChain ==
  [][(~executed /\ executed' /\ log'[Len(log')].kind = "execution_permitted"
      /\ AppliedNow = "irreversible")
       => /\ \A s \in Signals : state[s] = "closed_evidence" => s \in Sound
          /\ accEES]_vars

TypeOK ==
  /\ state \in [Signals -> States]
  /\ exitType \in [Signals -> ExitTypes \cup {"none"}]
  /\ legal \in [Signals -> LegalSubtypes \cup {"none"}]
  /\ cond \in [Signals -> BOOLEAN]
  /\ modelUpdate \in [Signals -> BOOLEAN]
  /\ accepted \in BOOLEAN /\ executed \in BOOLEAN
  /\ declared \in Classes /\ reversal \in BOOLEAN /\ everBlocked \in BOOLEAN
  /\ relabel \in {"none", "open", "resolved"}
  /\ accEES \in BOOLEAN
  /\ envRev \in [Signals -> {"none", "off_envelope", "containment"}]
  /\ ruleRev \in [Signals -> BOOLEAN]

\* Blocked 1: a signal cannot be closed before it is classified.
NoCloseBeforeClassified ==
  [][\A s \in Signals : state[s] \in {"unregistered", "registered"} => state'[s] \notin Closed]_vars

\* Blocked 2: a classified signal cannot be closed before review opens.
NoCloseBeforeReview ==
  [][\A s \in Signals : state[s] = "classified" => state'[s] \notin Closed]_vars

\* Blocked 3: a suppressed signal cannot be silently closed.
NoSilentCloseFromSuppressed ==
  [][\A s \in Signals : state[s] = "suppressed" => state'[s] \notin Closed]_vars

\* Blocked 4: every reopen is its own log record naming the signal.
NoSilentReopen ==
  [][\A s \in Signals :
       (state[s] \in Closed /\ state'[s] = "under_review")
         => \E i \in Len(log) + 1 .. Len(log') :
              log'[i] = Rec("reopen", s, state[s], "under_review")]_vars

\* Rules 7-8: an escalated signal leaves only for review (or by exit), and
\* only once every review holding it is resolved by what its trigger
\* requires: a Rule 8 review by a documented model update, an off-envelope
\* or containment review by its own resolution, in this very step, with no
\* Rule 8 review outstanding. No such review is left open afterwards.
EscalatedNeedsModelUpdate ==
  [][\A s \in Signals :
       (state[s] = "escalated" /\ state'[s] = "under_review")
         => /\ envRev'[s] = "none"
            /\ \/ modelUpdate[s]
               \/ envRev[s] \in {"off_envelope", "containment"} /\ ~ruleRev[s]]_vars

\* Escalation Conditions: a signal named by an unresolved off-envelope or
\* containment review is never simply under review: it is escalated as
\* soon as it is in review, on arrival or when the review opens, so it
\* cannot be closed past the review.
EnvReviewHoldsTheLoop ==
  \A s \in Signals : envRev[s] \in {"off_envelope", "containment"} => state[s] /= "under_review"

EscalatedNeverClosesDirectly ==
  [][\A s \in Signals : state[s] = "escalated" => state'[s] \notin Closed]_vars

\* trajectory_lock is terminal.
TrajectoryLockTerminal ==
  [][\A s \in Signals : state[s] = "trajectory_lock" => state'[s] = "trajectory_lock"]_vars

\* executed_open is terminal too.
ExecutedOpenTerminal ==
  [][\A s \in Signals : state[s] = "executed_open" => state'[s] = "executed_open"]_vars

\* Exits with no re-entry in the spec never come back: terminal, superseded,
\* timeout (no transition), whistleblower (external process). Here and in
\* the next two properties "never come back" means never back into review:
\* the post-execution latch may still record an exited loop as carried open
\* (exited -> executed_open), which is not a re-entry.
NoReentryTypes == {"terminal", "superseded", "timeout", "whistleblower"}
NoForbiddenReentry ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] \in NoReentryTypes)
         => state'[s] \in {"exited", "executed_open"}]_vars

\* Containment, deferred and ambiguity exits with no resolution condition
\* registered at exit never come back (re-register as a new linked signal).
NoWaitingReentryWithoutCondition ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] \in WaitingExits /\ ~cond[s])
         => state'[s] \in {"exited", "executed_open"}]_vars

\* A judicial order or statutory trigger never resumes to review.
NoLegalReentryWithoutResumableSubtype ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] = "legal" /\ legal[s] \notin LegalResumable)
         => state'[s] \in {"exited", "executed_open"}]_vars

\* Audit trail: append-only. The old log is always a prefix of the new one.
AuditAppendOnly ==
  [][Len(log') >= Len(log) /\ SubSeq(log', 1, Len(log)) = log]_vars

\* Every state change of a signal is logged in the same step.
EveryChangeLogged ==
  [][(state' /= state) => Len(log') > Len(log)]_vars

\* Rule 4 is never overridden: execution implies acceptance.
Rule4 == executed => accepted

\* Execution past a failing gate is never silent: an open-loop
\* authorization is on record, an override or an Emergency Justification.
OpenLoopExecutionLogged ==
  [][(~executed /\ executed' /\ ~GateFor(AppliedNow))
       => \E i \in 1..Len(log') :
            log'[i].kind \in {"gate_override", "emergency_justification"}]_vars

\* After an irreversible execution, by any path, no loop stands open and no
\* constraint stands as closed or exited unless that resolves it: each
\* signal is unregistered, resolved (chain-sound evidence closure, or
\* exited as superseded), exited to an external process (whistleblower,
\* legal), or in a terminal state. What was not resolved has been latched
\* into executed_open. Stated with its own literal sets, not Resolved,
\* Latch, ResolvingExits or ExternalExits, so that weakening the latch or
\* the gate cannot also weaken the property.
NoOpenLoopAfterIrreversibleExecution ==
  [][(~executed /\ executed' /\ AppliedNow = "irreversible")
       => \A s \in Signals :
            /\ state'[s] \notin {"registered", "classified", "under_review", "suppressed",
                                 "escalated", "closed_authority", "closed_role_switch"}
            /\ state'[s] = "exited" => exitType'[s] \in {"superseded", "whistleblower", "legal"}
            /\ state'[s] = "closed_evidence" => s \in SoundOf(state', exitType')]_vars

\* A loop exited to an external process keeps that exit, type and legal
\* sub-type included, through execution by any path: it continues in the
\* external process, not in executed_open.
ExternalExitKeptAtExecution ==
  [][(~executed /\ executed')
       => \A s \in Signals :
            (state[s] = "exited" /\ exitType[s] \in {"whistleblower", "legal"})
              => /\ state'[s] = "exited"
                 /\ exitType'[s] = exitType[s]
                 /\ legal'[s] = legal[s]]_vars

\* The override never produces trajectory_lock: the runtime refuses an
\* override without the separation the Overrides require, so lock-in at
\* execution is recorded only by analysis, never by the machine.
OverrideNeverLocks ==
  [][(~executed /\ executed')
       => \A s \in Signals : state'[s] = "trajectory_lock" => state[s] = "trajectory_lock"]_vars

\* A structural review that cannot be suspended holds irreversible
\* execution: nothing irreversible executes, cleanly, by override or under
\* an Emergency Justification, while any of its signals is suppressed, or
\* escalated by anything but an off-envelope or containment review alone
\* (Layer 4, Overrides; Escalation Conditions). Stated with its own sets,
\* not HeldStates or EnvOnly, so that weakening the check (ReviewHold,
\* EnvOnly or the Emergency guard) cannot also weaken the property. The
\* relabel review, the third kind that cannot be suspended, has its own
\* property (NoExecutionWhileRelabelOpen); that an escalated signal goes
\* past only under an Emergency Justification is SuspendableReviewNeedsEJ.
NoIrreversibleExecutionPastReview ==
  [][(~executed /\ executed' /\ AppliedNow = "irreversible")
       => \A s \in Signals :
            /\ state[s] /= "suppressed"
            /\ state[s] = "escalated" => /\ ~ruleRev[s]
                                         /\ envRev[s] \in {"off_envelope", "containment"}]_vars

\* An irreversible decision executes past an unresolved off-envelope or
\* containment review only under an Emergency Justification: a clean pass
\* or an ordinary override is held.
SuspendableReviewNeedsEJ ==
  [][(~executed /\ executed' /\ AppliedNow = "irreversible"
      /\ \E s \in Signals : envRev[s] \in {"off_envelope", "containment"})
       => \E i \in Len(log) + 1 .. Len(log') : log'[i].kind = "emergency_justification"]_vars

\* An Emergency Justification is given only over a decision held by an
\* off-envelope or containment review, and it suspends the holding
\* reviews without resolving them: each is still unresolved, with the
\* same trigger, right after it.
EJSuspendsWithoutResolving ==
  [][(~executed /\ executed'
      /\ \E i \in Len(log) + 1 .. Len(log') : log'[i].kind = "emergency_justification")
       => /\ \E s \in Signals : envRev[s] \in {"off_envelope", "containment"}
          /\ \A s \in Signals : envRev[s] /= "none" => envRev'[s] = envRev[s]]_vars

\* An Emergency Justification opens the mandatory post-event review in the
\* same step.
EJOpensPostEventReview ==
  [][(\E i \in Len(log) + 1 .. Len(log') : log'[i].kind = "emergency_justification")
       => \E i \in Len(log) + 1 .. Len(log') : log'[i].kind = "post_event_review"]_vars

\* A constraint closed by authority or role switch never lets the
\* irreversible gate pass cleanly: clean execution at that class needs
\* every loop evidence-closed or resolved by exit.
NoCleanPassOverAuthorityClosure ==
  [][(~executed /\ executed' /\ log'[Len(log')].kind = "execution_permitted"
      /\ AppliedNow = "irreversible")
       => \A s \in Signals : state[s] \notin {"closed_authority", "closed_role_switch"}]_vars

\* Of the exits, only a supersession resolves a constraint: a terminal,
\* timeout, whistleblower, legal or any other exit never lets the
\* irreversible gate pass cleanly (Execution Gates, operational
\* definitions; the terminal-exit loophole, closed).
NoCleanPassOverNonResolvingExit ==
  [][(~executed /\ executed' /\ log'[Len(log')].kind = "execution_permitted"
      /\ AppliedNow = "irreversible")
       => \A s \in Signals : state[s] = "exited" => exitType[s] = "superseded"]_vars

\* Execution Class Assignment. A class below irreversible applies only with
\* a tested reversal path ("Every execution-class decision is irreversible
\* unless shown otherwise").
LowerClassNeedsReversal == AppliedNow /= "irreversible" => reversal

\* A clean execution below irreversible happens only with a tested
\* reversal path behind it.
NoLowerClassExecutionWithoutReversal ==
  [][(~executed /\ executed' /\ AppliedNow /= "irreversible") => reversal]_vars

\* Lowering the declared or applied class after a refusal opens the
\* relabel review.
RelabelAfterRefusalEscalates ==
  [][(everBlocked /\ \/ Rank[declared'] < Rank[declared]
                     \/ Rank[Applied(declared', reversal')] < Rank[AppliedNow])
       => relabel' = "open"]_vars

\* Nothing executes, by override or otherwise, while that review is open.
NoExecutionWhileRelabelOpen ==
  [][(~executed /\ executed') => relabel /= "open"]_vars

\* Reclassification is never silent.
ReclassificationLogged ==
  [][(<<declared, reversal>> /= <<declared', reversal'>>)
       => log'[Len(log')].kind = "decision_reclassified"]_vars

\* Non-vacuity witnesses: each must be VIOLATED in a run (tests check this),
\* showing that a loop really is latched and an Emergency Justification
\* really is given, so the properties above constrain something.
NeverLatches   == \A s \in Signals : state[s] /= "executed_open"
NeverEmergency == \A i \in 1..Len(log) : log[i].kind /= "emergency_justification"
\* And an action-property witness (checked under PROPERTIES): an Emergency
\* Justification really is given over a signal escalated by an
\* off-envelope or containment review, and latches it.
NeverEJOverEscalated ==
  [][(\E i \in Len(log) + 1 .. Len(log') : log'[i].kind = "emergency_justification")
       => \A s \in Signals : state[s] /= "escalated"]_vars

(***************************************************************************)
(* SCENE 5 - THE SPECIFICATION                                             *)
(***************************************************************************)
Spec == Init /\ [][Next]_vars

\* EXEUNT - end of module.
=============================================================================
