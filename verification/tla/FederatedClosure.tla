--------------------------- MODULE FederatedClosure ---------------------------
(***************************************************************************)
(* THE FEDERATION, MODEL-CHECKED                                           *)
(* A Model in Five Scenes                                                  *)
(*                                                                         *)
(* PROLOGUE                                                                *)
(* Three nodes, no central authority. Node A has a decision that rests on  *)
(* a loop owned by node B; B's closing evidence may itself rest on a loop  *)
(* owned by node C. A keeps a local MIRROR of B's loop and may close it    *)
(* only after verifying B's closure from B's own signed log (and C's, if   *)
(* the chain runs through C). This is cclf/federation.py, abstracted:      *)
(*                                                                         *)
(*   - a node's log is a sequence of loop events;                          *)
(*   - an HONEST node keeps one history and follows the state machine;     *)
(*   - a DISHONEST node may keep two histories (a fork) and write any      *)
(*     event into either, in any order;                                    *)
(*   - every prefix of every history may be delivered to A, at any time,   *)
(*     in any order, any number of times (an adversarial network);         *)
(*   - signatures are unforgeable: a log segment always comes from its     *)
(*     node, and the closure kinds are as the producer attested them.      *)
(*                                                                         *)
(* Closure events: "ok" (evidence with a verified origin and independent   *)
(* lineage), "unverified" (evidence whose attestation or lineage fails),   *)
(* "auth" (authority). Only "ok" grounds a closure.                        *)
(*                                                                         *)
(* THE PLAYBILL                                                            *)
(*   Scene 1  constants, variables, helpers                                *)
(*   Scene 2  what the owners do: Write                                    *)
(*   Scene 3  what A does: Receive (verify, fork, rollback, recheck),      *)
(*            Accept                                                       *)
(*   Scene 4  the specification                                            *)
(*   Scene 5  the properties                                               *)
(*                                                                         *)
(* READER'S NOTE: Verified vs Grounded                                     *)
(*   Verified is what A's code checks. Grounded is what the draft asks     *)
(*   for, written separately. The planted-fault tests change Verified and  *)
(*   Receive, never Grounded, so a weakened check shows up as a violation. *)
(***************************************************************************)
EXTENDS Naturals, Sequences, FiniteSets

(***************************************************************************)
(* SCENE 1: constants, variables, helpers                                  *)
(***************************************************************************)
CONSTANTS
    Dishonest,      \* subset of {"B", "C"}: the nodes that may fork and lie
    BDependsOnC,    \* TRUE: B's closing evidence rests on C's loop
    MaxLen,         \* bound on each history's length
    MaxALog         \* bound on A's own log

Peers   == {"B", "C"}
Hist    == {1, 2}
Closes  == {"ok", "unverified", "auth"}
Events  == {"reg", "reopen"} \cup Closes
NoView  == [h |-> 0, n |-> 0]

VARIABLES
    logs,     \* logs[p][h]: peer p's history h (an honest peer has only 1)
    view,     \* view[p]: the segment of p's log A last accepted, [h, n]
    equiv,    \* peers A has caught signing two histories
    mirror,   \* A's mirror of B's loop: "open" or "closed"
    alog      \* A's own append-only log of what it did

vars == <<logs, view, equiv, mirror, alog>>

\* The first n events of history h of peer p (all of it, if shorter).
Pref(p, h, n) == SubSeq(logs[p][h], 1, IF n <= Len(logs[p][h]) THEN n ELSE Len(logs[p][h]))

\* The loop's state after a sequence of events: the last event decides.
LoopState(s) ==
    IF s = <<>> THEN "none"
    ELSE IF s[Len(s)] \in {"reg", "reopen"} THEN "open" ELSE s[Len(s)]

\* The loop's state in the segment A holds for p.
Seen(p, v) == IF v[p].h = 0 THEN "none" ELSE LoopState(Pref(p, v[p].h, v[p].n))

\* What A checks before relying on B's closure (the implementation).
Verified(v, eq) ==
    /\ "B" \notin eq
    /\ Seen("B", v) = "ok"
    /\ BDependsOnC => ("C" \notin eq /\ Seen("C", v) = "ok")

(***************************************************************************)
(* SCENE 2: what the owners do                                             *)
(***************************************************************************)
\* The events an honest node may append next (the Layer 4 table, reduced).
HonestNext(s) ==
    IF s = <<>> THEN {"reg"}
    ELSE IF LoopState(s) = "open" THEN Closes
    ELSE {"reopen"}

Write(p, h, e) ==
    /\ Len(logs[p][h]) < MaxLen
    /\ IF p \in Dishonest THEN TRUE ELSE (h = 1 /\ e \in HonestNext(logs[p][h]))
    /\ logs' = [logs EXCEPT ![p][h] = Append(@, e)]
    /\ UNCHANGED <<view, equiv, mirror, alog>>

(***************************************************************************)
(* SCENE 3: what A does                                                    *)
(***************************************************************************)
\* After any change to what A believes, every acceptance is checked again.
\* A closed mirror that no longer verifies is reopened, and that is logged.
Recheck(v, eq, entry) ==
    IF mirror = "closed" /\ ~Verified(v, eq)
    THEN /\ mirror' = "open"
         /\ alog' = alog \o <<entry, "withdrawn">>
    ELSE /\ mirror' = mirror
         /\ alog' = Append(alog, entry)

\* A takes in the first n events of p's history h.
Receive(p, h, n) ==
    /\ Len(alog) + 2 <= MaxALog
    /\ 1 <= n /\ n <= Len(logs[p][h])
    /\ p \notin equiv                                   \* equivocators refused
    /\ view[p] /= [h |-> h, n |-> n]                    \* nothing new: no step
    /\ view[p].h /= 0 => n >= view[p].n                 \* rollback refused
    /\ IF view[p].h /= 0 /\ Pref(p, h, view[p].n) /= Pref(p, view[p].h, view[p].n)
       THEN \* Two signed histories differ where both cover: a fork.
            /\ equiv' = equiv \cup {p}
            /\ view' = view
            /\ Recheck(view, equiv \cup {p}, "fork")
       ELSE /\ view' = [view EXCEPT ![p] = [h |-> h, n |-> n]]
            /\ equiv' = equiv
            /\ Recheck(view', equiv, "verified")
    /\ UNCHANGED logs

\* A closes its mirror locally, only on a verified closure.
Accept ==
    /\ Len(alog) < MaxALog
    /\ mirror = "open"
    /\ Verified(view, equiv)
    /\ mirror' = "closed"
    /\ alog' = Append(alog, "accepted")
    /\ UNCHANGED <<logs, view, equiv>>

(***************************************************************************)
(* SCENE 4: the specification                                              *)
(***************************************************************************)
Init ==
    /\ logs = [p \in Peers |-> [h \in Hist |-> <<>>]]
    /\ view = [p \in Peers |-> NoView]
    /\ equiv = {}
    /\ mirror = "open"
    /\ alog = <<>>

Next ==
    \/ \E p \in Peers, h \in Hist, e \in Events : Write(p, h, e)
    \/ \E p \in Peers, h \in Hist, n \in 1..MaxLen : Receive(p, h, n)
    \/ Accept

Spec == Init /\ [][Next]_vars

TypeOK ==
    /\ \A p \in Peers, h \in Hist : logs[p][h] \in Seq(Events)
    /\ \A p \in Peers : view[p].h \in {0} \cup Hist /\ view[p].n \in 0..MaxLen
    /\ equiv \subseteq Peers
    /\ mirror \in {"open", "closed"}

(***************************************************************************)
(* SCENE 5: the properties                                                 *)
(***************************************************************************)
\* What the draft asks for, stated apart from the implementation: A's own
\* verified copies show B's loop, and C's if B's evidence rests on it,
\* closed by evidence with a verified origin, from nodes not caught forking.
Grounded ==
    /\ "B" \notin equiv /\ view["B"].h /= 0
    /\ LoopState(SubSeq(logs["B"][view["B"].h], 1, view["B"].n)) = "ok"
    /\ BDependsOnC =>
         /\ "C" \notin equiv /\ view["C"].h /= 0
         /\ LoopState(SubSeq(logs["C"][view["C"].h], 1, view["C"].n)) = "ok"

\* Local Closure: A's mirror is closed only while the closure is grounded.
\* (Attempted Closure: B closing its loop never closes A's mirror by itself.)
LocalClosureOnlyWhenGrounded == mirror = "closed" => Grounded

\* An equivocator is never relied on.
EquivocatorNeverRelied == ("B" \in equiv \/ (BDependsOnC /\ "C" \in equiv)) => mirror = "open"

\* Only a node that really signed two histories is ever called an equivocator.
NoFalseAccusation == \A p \in equiv :
    \E n \in 1..MaxLen : n <= Len(logs[p][1]) /\ n <= Len(logs[p][2])
                         /\ Pref(p, 1, n) /= Pref(p, 2, n)

\* A's view of a peer only grows.
NoRollback == [][\A p \in Peers : view[p].h /= 0 => view'[p].n >= view[p].n]_vars

\* A's view of a peer never switches to a different history.
NoHistorySwitch == [][\A p \in Peers :
    view[p].h /= 0 => SubSeq(logs'[p][view'[p].h], 1, view[p].n)
                      = SubSeq(logs[p][view[p].h], 1, view[p].n)]_vars

\* The mirror closes only by an acceptance, logged in the same step.
ClosureOnlyByAcceptance == [][(mirror = "open" /\ mirror' = "closed")
                              => alog' = Append(alog, "accepted")]_vars

\* A withdrawal is logged in the same step.
WithdrawalLogged == [][(mirror = "closed" /\ mirror' = "open")
                       => alog'[Len(alog')] = "withdrawn"]_vars

\* A's log only grows.
ALogAppendOnly == [][Len(alog') >= Len(alog) /\ SubSeq(alog', 1, Len(alog)) = alog]_vars

\* Separate machines: every step changes the variables of at most one node.
\* A owns view, equiv, mirror and alog; B and C each own their own logs.
\* No step lets one node write another's state, and none moves two nodes
\* at once (no synchronous handshake, no global coordinator).
Changed == {n \in {"A", "B", "C"} :
              IF n = "A" THEN <<view', equiv', mirror', alog'>> /= <<view, equiv, mirror, alog>>
              ELSE logs'[n] /= logs[n]}
NodeIsolation == [][Cardinality(Changed) <= 1]_vars

\* Non-vacuity witnesses: each must be VIOLATED in a run (tests check this).
NeverAccepts    == mirror = "open"
NeverWithdraws  == \A i \in 1..Len(alog) : alog[i] /= "withdrawn"
NeverCatchesFork == equiv = {}
=============================================================================
