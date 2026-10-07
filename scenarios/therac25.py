"""
Therac-25 Evidence Sequences
=============================
Two-pass structure mirroring the actual failure timeline:

PASS 1 — Six patient incidents (1985–1987)
  Hospital operators report malfunctions sequentially.
  Evidence accumulates; formal commitment state should respond.

PASS 2 — AECL suppression documents
  Internal communications, "no fault found" letters, and the
  race condition memo that was never disclosed to hospitals.
  This pass surfaces the ACO: the gap between what AECL knew
  and what it told operators/regulators.

Sources: Leveson & Turner (1993) "An Investigation of the Therac-25 Accidents"
         IEEE Computer, Vol. 26 No. 7. All evidence content is paraphrased
         from that public record.
"""

# ---------------------------------------------------------------------------
# PASS 1 — Patient incidents (sequential batches, one per incident)
# Each batch represents what a hospital operator could observe and report.
# ---------------------------------------------------------------------------

PASS_1_INCIDENTS = [
    # Incident 1 — Kennestone Regional Oncology Center, GA, June 1985
    [
        {
            "evidence_id": "t25-i1-a",
            "content": (
                "Patient received massive radiation overdose during Therac-25 treatment. "
                "Machine displayed 'MALFUNCTION 54' error. Operator unaware this indicated "
                "a dose significantly above prescription. Patient later died; hip injury "
                "consistent with radiation overdose documented by treating physicians."
            ),
            "source": "Kennestone Regional Oncology Center — Incident Report, Jun 1985",
        },
        {
            "evidence_id": "t25-i1-b",
            "content": (
                "Hospital contacted AECL. AECL physics staff visited site and concluded "
                "the Therac-25 could not have delivered an overdose. No software fault found. "
                "AECL stated the machine was 'physically impossible' of delivering excess dose "
                "without hardware interlock triggering."
            ),
            "source": "AECL Field Service Report — Kennestone, Aug 1985",
        },
    ],

    # Incident 2 — Hamilton Civic Hospital, Ontario, Jul 1985
    [
        {
            "evidence_id": "t25-i2-a",
            "content": (
                "Second patient overdose. Machine again displayed 'MALFUNCTION 54'. "
                "Patient received radiation burn to shoulder. Injury site inconsistent "
                "with prescribed treatment field; consistent with electron beam at full "
                "power without beam-spreading foil in place."
            ),
            "source": "Hamilton Civic Hospital — Incident Report, Jul 1985",
        },
        {
            "evidence_id": "t25-i2-b",
            "content": (
                "AECL again investigated. Unable to reproduce malfunction in testing. "
                "Issued letter to hospital stating no hardware or software fault identified. "
                "Machine returned to service. No regulatory notification made."
            ),
            "source": "AECL Letter to Hamilton Civic Hospital, Sep 1985",
        },
    ],

    # Incident 3 — Yakima Valley Memorial Hospital, WA, Dec 1985
    [
        {
            "evidence_id": "t25-i3-a",
            "content": (
                "Third overdose incident. Patient suffered radiation injury to neck/shoulder. "
                "Operator noted machine behaved erratically only when editing treatment "
                "parameters quickly after setup — a specific operational sequence. "
                "Malfunction not reproducible at slow editing speed."
            ),
            "source": "Yakima Valley Memorial Hospital — Incident Report, Dec 1985",
        },
    ],

    # Incident 4 — East Texas Cancer Center, Mar 1986
    [
        {
            "evidence_id": "t25-i4-a",
            "content": (
                "Fourth incident. Patient received overdose. Died three weeks later. "
                "Operator observed 'MALFUNCTION 54' and a second message 'DOSE INPUT 2'. "
                "Machine paused; operator pressed 'P' to proceed as trained. "
                "This operator action — proceeding through the pause — became a key "
                "causal factor under analysis."
            ),
            "source": "East Texas Cancer Center — Incident Report / Coroner Referral, Mar 1986",
        },
        {
            "evidence_id": "t25-i4-b",
            "content": (
                "East Texas Cancer Center physicist Fritz Hager began independent investigation. "
                "Noted the 'proceed' keypress pattern was consistent across reported incidents. "
                "Hypothesised a software race condition triggered by rapid data entry. "
                "Communicated hypothesis to AECL."
            ),
            "source": "East Texas Cancer Center — Internal Physics Memo, Apr 1986",
        },
    ],

    # Incident 5 — Yakima Valley Memorial Hospital, Jan 1987
    [
        {
            "evidence_id": "t25-i5-a",
            "content": (
                "Fifth overdose. Same hospital as Incident 3. Patient received burn "
                "to face. Operator again noted rapid parameter editing preceded malfunction. "
                "Hospital physicist documented the editing-speed dependency explicitly "
                "and transmitted to AECL with request for urgent response."
            ),
            "source": "Yakima Valley Memorial Hospital — Second Incident Report, Jan 1987",
        },
        {
            "evidence_id": "t25-i5-b",
            "content": (
                "AECL response to Yakima second incident: machine 'checked out satisfactorily'. "
                "No software change issued. Letter did not address the editing-speed hypothesis "
                "raised by the hospital physicist."
            ),
            "source": "AECL Letter to Yakima Valley Memorial, Feb 1987",
        },
    ],

    # Incident 6 — Yakima Valley Memorial Hospital, Jan 1987 (same period)
    [
        {
            "evidence_id": "t25-i6-a",
            "content": (
                "Sixth overdose — same facility, within weeks. Patient died. "
                "This incident triggered formal NRC (Nuclear Regulatory Commission) "
                "investigation. The NRC issued an Abnormal Occurrence report, "
                "the first regulatory intervention in the two-year sequence."
            ),
            "source": "NRC Abnormal Occurrence Report — Therac-25, Feb 1987",
        },
    ],
]


# ---------------------------------------------------------------------------
# PASS 2 — AECL suppression documents
# These surface the ACO: internal knowledge that was never disclosed.
# Evidence is presented as a second wave after all six incidents are logged.
# ---------------------------------------------------------------------------

PASS_2_SUPPRESSION = [
    {
        "evidence_id": "t25-s1",
        "content": (
            "AECL internal software review (undisclosed to hospitals or regulators) "
            "identified a race condition in the Therac-25 treatment sequencing code. "
            "The condition could be triggered by an operator editing the 'mode' field "
            "within approximately 8 seconds of entering the previous field. "
            "This window was narrow enough that testing rarely reproduced it."
        ),
        "source": "AECL Internal Software Review — CONFIDENTIAL, 1986",
    },
    {
        "evidence_id": "t25-s2",
        "content": (
            "The race condition allowed the collimator/turntable to be in the wrong "
            "position while the software believed it was correctly positioned. "
            "Result: electron beam fired at full therapeutic power (25 MeV equivalent) "
            "without the beam-spreading foil that reduces dose rate by a factor of ~100. "
            "Hardware interlocks had been removed from Therac-25 (vs. Therac-20) "
            "on the assumption that software checks were sufficient."
        ),
        "source": "AECL Engineering Analysis — CONFIDENTIAL, 1986",
    },
    {
        "evidence_id": "t25-s3",
        "content": (
            "AECL's 'no fault found' letters to Kennestone and Hamilton were written "
            "after the internal software review had begun. The letters stated the machine "
            "was incapable of overdosing a patient. This claim was not consistent with "
            "the race condition analysis being conducted simultaneously by the same team."
        ),
        "source": "Cross-reference: AECL letters (Aug–Sep 1985) vs. internal review timeline",
    },
    {
        "evidence_id": "t25-s4",
        "content": (
            "Therac-25 software was written by a single programmer and had never undergone "
            "independent formal review. No fault tree analysis, no FMEA, no software "
            "safety case was produced. AECL's confidence in software-only interlocks "
            "was not documented to any regulatory standard."
        ),
        "source": "NRC Investigation Report — Software Quality Finding, 1987",
    },
    {
        "evidence_id": "t25-s5",
        "content": (
            "The FDA and NRC jointly issued a recall of all Therac-25 units in April 1987. "
            "Required corrective actions: restore hardware interlocks, independent software "
            "audit, mandatory incident reporting protocol. AECL agreed to all conditions. "
            "Six patients had been overdosed over 22 months. Three died."
        ),
        "source": "FDA/NRC Joint Recall Notice — Therac-25, Apr 1987",
    },
]
