"""
Boeing 737 MAX MCAS Evidence Sequence
======================================
Five evidence items introduced one at a time, tracing the path from a
known single-sensor design decision to type certification.

The ACO (Adversarial Commitment Opacity) here is concealment from the
regulator: the FAA held formal authority to block certification but
approved documentation describing MCAS's original, smaller authority.
"""

MCAS_SCENARIO: list[dict] = [
    {
        "evidence_id": "mcas-001",
        "content": (
            "AOA sensor divergence flagged in Lion Air JT610 FDR data. "
            "Single sensor driving MCAS inputs with no cross-check. "
            "Engineering analysis notes this was a known design decision."
        ),
        "source": "Boeing FDR Analysis Team",
    },
    {
        "evidence_id": "mcas-002",
        "content": (
            "Pilot bulletin issued omitting MCAS from flight manual. "
            "Decision: MCAS characteristics classified as 'non-novel' "
            "to avoid full simulator retraining requirement for airlines."
        ),
        "source": "Boeing Flight Crew Operations",
    },
    {
        "evidence_id": "mcas-003",
        "content": (
            "FAA Aircraft Evaluation Group was not informed of MCAS authority "
            "expansion from 0.6° to 2.5° ANU. Approval documentation "
            "references the original, smaller authority."
        ),
        "source": "FAA Joint Operations Evaluation Board",
    },
    {
        "evidence_id": "mcas-004",
        "content": (
            "Safety assessment assumed pilots would respond to MCAS runaway "
            "within 3 seconds — a figure not validated in human factors testing "
            "and not disclosed to certification authority."
        ),
        "source": "Boeing Safety Engineering",
    },
    {
        "evidence_id": "mcas-005",
        "content": (
            "737 MAX FAA type certification granted. First aircraft delivered "
            "to Southwest Airlines. Production rate: 52/month. "
            "Order backlog: ~4,600 aircraft."
        ),
        "source": "Boeing Commercial Airplanes Program Management",
    },
]
