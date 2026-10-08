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
(* Rule 4 acceptance, the gates with their logged override, and Execution  *)
(* Class Assignment (irreversible by default, tested reversal path,        *)
(* logged reclassification, the relabel-after-refusal review).            *)
(*                                                                         *)
(* Two configurations check it (see README): CommitmentStateMachine.cfg    *)
(* explores the signal lifecycle with two signals and a fixed irreversible *)
(* decision; Classes.cfg explores every class, reversal and relabel path   *)
(* with one signal. Every property is checked in both.                     *)
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
          Reclassify      \* TRUE: explore relabels, refusals and the relabel review

(***************************************************************************)
(* SCENE 1 - THE VOCABULARY                                                *)
(***************************************************************************)

\* The commitment states of Layer 4 ("exited" carries its type separately).
States == {"unregistered", "registered", "classified", "under_review",
           "closed_evidence", "closed_authority", "closed_role_switch",
           "suppressed", "escalated", "trajectory_lock", "exited"}

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
    <<"closed_role_switch", "under_review">> }
\* END TRANSITIONS

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
(*   executed        the irreversible decision has executed                *)
(*   log             the audit log: a sequence of records                  *)
(***************************************************************************)
VARIABLES state, exitType, legal, cond, modelUpdate, accepted, executed, log,
          declared, reversal, everBlocked, relabel

vars == <<state, exitType, legal, cond, modelUpdate, accepted, executed, log,
          declared, reversal, everBlocked, relabel>>

\* The decision-class variables, for UNCHANGED clauses.
classVars == <<declared, reversal, everBlocked, relabel>>

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

\* Every log record has the same fields; unused ones hold "none".
Rec(kind, sig, from, to) ==
  [kind |-> kind, sig |-> sig, from |-> from, to |-> to]

Log(r) == log' = Append(log, r)

(***************************************************************************)
(* SCENE 3 - THE STEPS                                                     *)
(***************************************************************************)

\* An ordinary move along the table. Reopen and recovery have their own
\* actions below, because the spec attaches conditions to them.
Move(s, t) ==
  /\ <<state[s], t>> \in Transitions
  /\ state[s] \notin Closed            \* reopening: see Reopen
  /\ state[s] /= "escalated"           \* recovery: see Recover
  /\ state' = [state EXCEPT ![s] = t]
  /\ Log(Rec("transition", s, state[s], t))
  /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* "A closed loop cannot be silently reopened": the reopen is its own
\* logged record (rationale, reopening agent, superseded closure).
Reopen(s) ==
  /\ state[s] \in Closed
  /\ <<state[s], "under_review">> \in Transitions
  /\ state' = [state EXCEPT ![s] = "under_review"]
  /\ Log(Rec("reopen", s, state[s], "under_review"))
  /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* Rule 8: structural review documents a model update.
DocumentModelUpdate(s) ==
  /\ state[s] = "escalated"
  /\ ~modelUpdate[s]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = TRUE]
  /\ Log(Rec("model_update", s, "escalated", "escalated"))
  /\ UNCHANGED <<state, exitType, legal, cond, accepted, executed>> /\ UNCHANGED classVars

\* escalated -> under_review, only once the model update is on record.
Recover(s) ==
  /\ state[s] = "escalated"
  /\ <<"escalated", "under_review">> \in Transitions
  /\ modelUpdate[s]
  /\ state' = [state EXCEPT ![s] = "under_review"]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = FALSE]
  /\ Log(Rec("transition", s, "escalated", "under_review"))
  /\ UNCHANGED <<exitType, legal, cond, accepted, executed>> /\ UNCHANGED classVars

\* any open state -> exited(type). A legal exit records its sub-type; a
\* containment, deferred or ambiguity exit may register a resolution
\* condition (c), and no other exit type does.
Exit(s, x, sub, c) ==
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
    /\ state'    = [state    EXCEPT ![s] = "under_review"]
    /\ exitType' = [exitType EXCEPT ![s] = "none"]
    /\ legal'    = [legal    EXCEPT ![s] = "none"]
    /\ cond'     = [cond     EXCEPT ![s] = FALSE]
    /\ Log(Rec("reentry", s, "exited", "under_review"))
    /\ UNCHANGED <<modelUpdate, accepted, executed>> /\ UNCHANGED classVars

\* Rule 4: someone explicitly accepts authorization, risk and rationale.
Accept ==
  /\ ~accepted
  /\ accepted' = TRUE
  /\ Log(Rec("acceptance", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, executed>> /\ UNCHANGED classVars

\* Exits whose "Loop State After" leaves the loop open.
LeavesOpen == {"containment", "recoverable", "delegated", "deferred", "forced",
               "exhaustion", "boundary", "ambiguity", "key_person"}

IsOpen(s) == \/ state[s] \in OpenStates
             \/ state[s] = "exited" /\ exitType[s] \in LeavesOpen

\* The irreversible gate, reduced to the requirement this model can see.
\* Every signal is treated as a constraint, and a constraint counts as
\* resolved only if closed by evidence or exited by a type whose Loop State
\* After is closed (terminal, superseded): authority and role-switch
\* closures do not satisfy it (Reversibility Logic). Chain soundness and
\* the decision-level EES requirement are not modeled here.
ResolvingExits == {"terminal", "superseded"}
GateOK == \A s \in Signals :
            \/ state[s] = "closed_evidence"
            \/ state[s] = "exited" /\ exitType[s] \in ResolvingExits

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

\* Clean execution: accepted, no relabel review open, and the gate for the
\* APPLIED class passes.
Execute ==
  /\ accepted /\ ~executed /\ ~RelabelOpen /\ GateFor(AppliedNow)
  /\ executed' = TRUE
  /\ Log(Rec("execution_permitted", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted>> /\ UNCHANGED classVars

\* Override: accepted, no relabel review open, the applied gate fails, and
\* the override is logged. At the irreversible class every signal under
\* review is latched into trajectory_lock (lock-in closure) and the
\* open-loop marker is logged too; a lower class latches nothing.
Override ==
  /\ accepted /\ ~executed /\ ~RelabelOpen /\ ~GateFor(AppliedNow)
  /\ Len(log) + 2 <= MaxLog
  /\ executed' = TRUE
  /\ IF AppliedNow = "irreversible"
       THEN /\ state' = [s \in Signals |->
                         IF state[s] = "under_review" THEN "trajectory_lock" ELSE state[s]]
            /\ log' = log \o << Rec("gate_override", "none", "none", "none"),
                               Rec("open_loop_irreversible_execution", "none", "none", "none") >>
       ELSE /\ state' = state
            /\ log' = Append(log, Rec("gate_override", "none", "none", "none"))
  /\ UNCHANGED <<exitType, legal, cond, modelUpdate, accepted>> /\ UNCHANGED classVars

\* A refused execution request: no acceptance, a relabel review open, or the
\* applied gate fails (and no override is given). Recorded, because a later
\* lowering is judged against it.
Refuse ==
  /\ Reclassify
  /\ ~executed
  /\ ~accepted \/ RelabelOpen \/ ~GateFor(AppliedNow)
  /\ everBlocked' = TRUE
  /\ Log(Rec("execution_blocked", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed,
                 declared, reversal, relabel>>

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
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed, everBlocked>>

\* Rule 8: the relabel review is resolved by a documented model update.
ResolveRelabel ==
  /\ RelabelOpen
  /\ relabel' = "resolved"
  /\ Log(Rec("model_update", "none", "relabel", "relabel"))
  /\ UNCHANGED <<state, exitType, legal, cond, modelUpdate, accepted, executed,
                 declared, reversal, everBlocked>>

Next ==
  /\ Len(log) < MaxLog
  /\ \/ \E s \in Signals, t \in States : Move(s, t)
     \/ \E s \in Signals : Reopen(s) \/ DocumentModelUpdate(s) \/ Recover(s) \/ Reenter(s)
     \/ \E s \in Signals, x \in ExitTypes, sub \in LegalSubtypes \cup {"none"}, c \in BOOLEAN :
          Exit(s, x, sub, c)
     \/ Accept \/ Execute \/ Override \/ Refuse \/ ResolveRelabel
     \/ \E c \in Classes, r \in BOOLEAN : ReclassifyTo(c, r)

(***************************************************************************)
(* SCENE 4 - THE PROPERTIES                                                *)
(* Invariants hold in every reachable state. Action properties ([][P]_v)  *)
(* hold for every step.                                                    *)
(***************************************************************************)

TypeOK ==
  /\ state \in [Signals -> States]
  /\ exitType \in [Signals -> ExitTypes \cup {"none"}]
  /\ legal \in [Signals -> LegalSubtypes \cup {"none"}]
  /\ cond \in [Signals -> BOOLEAN]
  /\ modelUpdate \in [Signals -> BOOLEAN]
  /\ accepted \in BOOLEAN /\ executed \in BOOLEAN
  /\ declared \in Classes /\ reversal \in BOOLEAN /\ everBlocked \in BOOLEAN
  /\ relabel \in {"none", "open", "resolved"}

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
         => log'[Len(log')] = Rec("reopen", s, state[s], "under_review")]_vars

\* Rules 7-8: an escalated signal leaves only for review, and only after a
\* documented model update (or by exit).
EscalatedNeedsModelUpdate ==
  [][\A s \in Signals :
       (state[s] = "escalated" /\ state'[s] = "under_review") => modelUpdate[s]]_vars

EscalatedNeverClosesDirectly ==
  [][\A s \in Signals : state[s] = "escalated" => state'[s] \notin Closed]_vars

\* trajectory_lock is terminal.
TrajectoryLockTerminal ==
  [][\A s \in Signals : state[s] = "trajectory_lock" => state'[s] = "trajectory_lock"]_vars

\* Exits with no re-entry in the spec never come back: terminal, superseded,
\* timeout (no transition), whistleblower (external process).
NoReentryTypes == {"terminal", "superseded", "timeout", "whistleblower"}
NoForbiddenReentry ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] \in NoReentryTypes) => state'[s] = "exited"]_vars

\* Containment, deferred and ambiguity exits with no resolution condition
\* registered at exit never come back (re-register as a new linked signal).
NoWaitingReentryWithoutCondition ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] \in WaitingExits /\ ~cond[s])
         => state'[s] = "exited"]_vars

\* A judicial order or statutory trigger never resumes to review.
NoLegalReentryWithoutResumableSubtype ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] = "legal" /\ legal[s] \notin LegalResumable)
         => state'[s] = "exited"]_vars

\* Audit trail: append-only. The old log is always a prefix of the new one.
AuditAppendOnly ==
  [][Len(log') >= Len(log) /\ SubSeq(log', 1, Len(log)) = log]_vars

\* Every state change of a signal is logged in the same step.
EveryChangeLogged ==
  [][(state' /= state) => Len(log') > Len(log)]_vars

\* Rule 4 is never overridden: execution implies acceptance.
Rule4 == executed => accepted

\* Execution past a failing gate is never silent: an override is on record.
OpenLoopExecutionLogged ==
  [][(~executed /\ executed' /\ ~GateFor(AppliedNow))
       => \E i \in 1..Len(log') : log'[i].kind = "gate_override"]_vars

\* After an override, nothing is left under review: each such loop was
\* latched into trajectory_lock as a permanent marker.
OverrideLatchesReviews ==
  [][(~executed /\ executed' /\ AppliedNow = "irreversible" /\ ~GateOK)
       => \A s \in Signals : state'[s] /= "under_review"]_vars

\* A constraint closed by authority or role switch never lets the
\* irreversible gate pass cleanly: clean execution at that class needs
\* every loop evidence-closed or resolved by exit.
NoCleanPassOverAuthorityClosure ==
  [][(~executed /\ executed' /\ log'[Len(log')].kind = "execution_permitted"
      /\ AppliedNow = "irreversible")
       => \A s \in Signals : state[s] \notin {"closed_authority", "closed_role_switch"}]_vars

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

(***************************************************************************)
(* SCENE 5 - THE SPECIFICATION                                             *)
(***************************************************************************)
Spec == Init /\ [][Next]_vars

\* EXEUNT - end of module.
=============================================================================
