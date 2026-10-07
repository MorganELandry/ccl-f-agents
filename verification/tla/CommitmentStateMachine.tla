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
(* Rule 4 acceptance and the irreversible gate with its logged override.   *)
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

CONSTANTS Signals,   \* the signals in the model, e.g. {s1, s2}
          MaxLog     \* bound on audit-log length, to keep the search finite

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
(*   modelUpdate[s]  a Rule 8 model update has been documented for it      *)
(*   accepted        Rule 4 acceptance given for the decision              *)
(*   executed        the irreversible decision has executed                *)
(*   log             the audit log: a sequence of records                  *)
(***************************************************************************)
VARIABLES state, exitType, legal, modelUpdate, accepted, executed, log

vars == <<state, exitType, legal, modelUpdate, accepted, executed, log>>

Init == /\ state       = [s \in Signals |-> "unregistered"]
        /\ exitType    = [s \in Signals |-> "none"]
        /\ legal       = [s \in Signals |-> "none"]
        /\ modelUpdate = [s \in Signals |-> FALSE]
        /\ accepted    = FALSE
        /\ executed    = FALSE
        /\ log         = <<>>

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
  /\ UNCHANGED <<exitType, legal, modelUpdate, accepted, executed>>

\* "A closed loop cannot be silently reopened": the reopen is its own
\* logged record (rationale, reopening agent, superseded closure).
Reopen(s) ==
  /\ state[s] \in Closed
  /\ <<state[s], "under_review">> \in Transitions
  /\ state' = [state EXCEPT ![s] = "under_review"]
  /\ Log(Rec("reopen", s, state[s], "under_review"))
  /\ UNCHANGED <<exitType, legal, modelUpdate, accepted, executed>>

\* Rule 8: structural review documents a model update.
DocumentModelUpdate(s) ==
  /\ state[s] = "escalated"
  /\ ~modelUpdate[s]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = TRUE]
  /\ Log(Rec("model_update", s, "escalated", "escalated"))
  /\ UNCHANGED <<state, exitType, legal, accepted, executed>>

\* escalated -> under_review, only once the model update is on record.
Recover(s) ==
  /\ state[s] = "escalated"
  /\ <<"escalated", "under_review">> \in Transitions
  /\ modelUpdate[s]
  /\ state' = [state EXCEPT ![s] = "under_review"]
  /\ modelUpdate' = [modelUpdate EXCEPT ![s] = FALSE]
  /\ Log(Rec("transition", s, "escalated", "under_review"))
  /\ UNCHANGED <<exitType, legal, accepted, executed>>

\* any open state -> exited(type). A legal exit records its sub-type.
Exit(s, x, sub) ==
  /\ state[s] \in OpenStates
  /\ (x = "legal") = (sub /= "none")
  /\ state'    = [state    EXCEPT ![s] = "exited"]
  /\ exitType' = [exitType EXCEPT ![s] = x]
  /\ legal'    = [legal    EXCEPT ![s] = sub]
  /\ Log(Rec("exit", s, state[s], x))
  /\ UNCHANGED <<modelUpdate, accepted, executed>>

\* May an exit of type x (legal sub-type sub) re-enter, given whether a
\* successor is registered, the resumer differs, and a legal hold is lifted?
ReentryAllowed(x, sub, hasSuccessor, resumerDiffers, lifted) ==
  \/ x \in ReentryStated
  \/ x \in ReentryNeedsSuccessor /\ hasSuccessor
  \/ x \in ReentryInferredFree
  \/ x = "boundary" /\ resumerDiffers
  \/ x = "legal" /\ sub \in LegalResumable /\ lifted

\* exited -> under_review. The three conditions are chosen freely by TLC
\* (\E ... \in BOOLEAN), so every combination is explored.
Reenter(s) ==
  \E hasSuccessor, resumerDiffers, lifted \in BOOLEAN :
    /\ state[s] = "exited"
    /\ ReentryAllowed(exitType[s], legal[s], hasSuccessor, resumerDiffers, lifted)
    /\ state'    = [state    EXCEPT ![s] = "under_review"]
    /\ exitType' = [exitType EXCEPT ![s] = "none"]
    /\ legal'    = [legal    EXCEPT ![s] = "none"]
    /\ Log(Rec("reentry", s, "exited", "under_review"))
    /\ UNCHANGED <<modelUpdate, accepted, executed>>

\* Rule 4: someone explicitly accepts authorization, risk and rationale.
Accept ==
  /\ ~accepted
  /\ accepted' = TRUE
  /\ Log(Rec("acceptance", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, modelUpdate, executed>>

\* Exits whose "Loop State After" leaves the loop open.
LeavesOpen == {"containment", "recoverable", "delegated", "deferred", "forced",
               "exhaustion", "boundary", "ambiguity", "key_person"}

IsOpen(s) == \/ state[s] \in OpenStates
             \/ state[s] = "exited" /\ exitType[s] \in LeavesOpen

\* The irreversible gate, reduced to the requirement this model can see:
\* no open loops (all signals are treated as constraints here).
GateOK == \A s \in Signals : state[s] /= "unregistered" /\ ~IsOpen(s)

\* Clean execution: accepted and the gate passes.
Execute ==
  /\ accepted /\ ~executed /\ GateOK
  /\ executed' = TRUE
  /\ Log(Rec("execution_permitted", "none", "none", "none"))
  /\ UNCHANGED <<state, exitType, legal, modelUpdate, accepted>>

\* Override: accepted, the gate fails, the override is logged, and every
\* signal under review is latched into trajectory_lock (lock-in closure).
\* Two records are appended: the override, then the open-loop marker.
Override ==
  /\ accepted /\ ~executed /\ ~GateOK
  /\ Len(log) + 2 <= MaxLog
  /\ executed' = TRUE
  /\ state' = [s \in Signals |->
                 IF state[s] = "under_review" THEN "trajectory_lock" ELSE state[s]]
  /\ log' = log \o << Rec("gate_override", "none", "none", "none"),
                      Rec("open_loop_irreversible_execution", "none", "none", "none") >>
  /\ UNCHANGED <<exitType, legal, modelUpdate, accepted>>

Next ==
  /\ Len(log) < MaxLog
  /\ \/ \E s \in Signals, t \in States : Move(s, t)
     \/ \E s \in Signals : Reopen(s) \/ DocumentModelUpdate(s) \/ Recover(s) \/ Reenter(s)
     \/ \E s \in Signals, x \in ExitTypes, sub \in LegalSubtypes \cup {"none"} : Exit(s, x, sub)
     \/ Accept \/ Execute \/ Override

(***************************************************************************)
(* SCENE 4 - THE PROPERTIES                                                *)
(* Invariants hold in every reachable state. Action properties ([][P]_v)  *)
(* hold for every step.                                                    *)
(***************************************************************************)

TypeOK ==
  /\ state \in [Signals -> States]
  /\ exitType \in [Signals -> ExitTypes \cup {"none"}]
  /\ legal \in [Signals -> LegalSubtypes \cup {"none"}]
  /\ modelUpdate \in [Signals -> BOOLEAN]
  /\ accepted \in BOOLEAN /\ executed \in BOOLEAN

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
\* timeout (no transition), containment/deferred/ambiguity (D2),
\* whistleblower (external process).
NoReentryTypes == {"terminal", "superseded", "timeout", "containment",
                   "deferred", "ambiguity", "whistleblower"}
NoForbiddenReentry ==
  [][\A s \in Signals :
       (state[s] = "exited" /\ exitType[s] \in NoReentryTypes) => state'[s] = "exited"]_vars

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

\* Execution with open loops is never silent: an override is on record.
OpenLoopExecutionLogged ==
  [][(~executed /\ executed' /\ ~GateOK)
       => \E i \in 1..Len(log') : log'[i].kind = "gate_override"]_vars

\* After an override, nothing is left under review: each such loop was
\* latched into trajectory_lock as a permanent marker.
OverrideLatchesReviews ==
  [][(~executed /\ executed' /\ ~GateOK)
       => \A s \in Signals : state'[s] /= "under_review"]_vars

(***************************************************************************)
(* SCENE 5 - THE SPECIFICATION                                             *)
(***************************************************************************)
Spec == Init /\ [][Next]_vars

\* EXEUNT - end of module.
=============================================================================
