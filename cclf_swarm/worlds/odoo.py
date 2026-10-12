"""
THE ODOO INVOICE WORLD
A Play in Six Scenes
======================

PROLOGUE
--------
Agents review draft customer invoices in an Odoo database, and posting them
is the irreversible step: the agents do the clerical work, CCL-F decides
what may be committed, and a person accepts.

The cast (AUTOMATION, so acceptance and attestation go to people):

  ar-clerk     reads draft invoices and their sale orders, and registers
               every discrepancy as a signal
  controller   checks the batch, closes concerns only on record evidence,
               proposes the batch to post, registers the decision, asks the
               owner to accept, and requests execution

People (configured): `owner` accepts; `attester` attests that the evidence
bears on the risk claim; `successor` takes over a concern (AP.1b).

Instrument:

  odoo-records   read_records(): a read of the database; primary document.

The effect: account.move.action_post on the proposed batch. DRY RUN BY
DEFAULT: execute() reports the call it would make and changes nothing until
the world is built with dry_run=False. Reads are limited to an allowlist of
models; agents never call an Odoo method directly.

Connection: OdooClient.from_env() reads ODOO_URL, ODOO_DB, ODOO_USER and
ODOO_API_KEY and talks XML-RPC (the external API in Odoo 17-19). FakeOdoo is
an in-memory stand-in with three draft invoices, one of them wrong, for
tests and offline demos.

THE PLAYBILL
    Scene 1  OdooClient           XML-RPC
    Scene 2  FakeOdoo             the offline stand-in
    Scene 3  OdooReview.roles()
    Scene 4  setup() and tools()
    Scene 5  execute()
    Scene 6  done() and report()
"""

from __future__ import annotations

import json
import os
import xmlrpc.client

from ..runtime import RoleSpec, Runtime, ToolSpec
from .base import World, text_arg


READ_MODELS = {
    "account.move": ["name", "partner_id", "move_type", "state", "amount_untaxed",
                     "amount_tax", "amount_total", "invoice_origin", "invoice_date"],
    "account.move.line": ["move_id", "product_id", "quantity", "price_unit", "price_subtotal",
                          "tax_ids"],
    "sale.order": ["name", "partner_id", "state", "amount_untaxed", "amount_tax",
                   "amount_total", "invoice_status"],
    "res.partner": ["name", "vat", "email", "country_id"],
}
ASKS = frozenset({"accept_decision", "attest_risk_evidence", "resolve_review"})
DOMAIN_OPS = frozenset({"=", "!=", "in"})
MAX_LIMIT = 200
SIGNAL_OPS = frozenset({"register_signal", "classify", "open_review", "attempt_closure",
                        "add_evidence", "add_dependency", "reopen", "link_signal"})


# ===========================================================================
# SCENE 1 — XML-RPC
# ===========================================================================

class OdooClient:
    """A minimal client for Odoo's external XML-RPC API."""

    def __init__(self, url: str, db: str, username: str, api_key: str) -> None:
        self.url, self.db, self.key = url.rstrip("/"), db, api_key
        common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self.uid = common.authenticate(db, username, api_key, {})
        if not self.uid:
            raise PermissionError("Odoo authentication failed")
        self.models = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    @classmethod
    def from_env(cls) -> "OdooClient":
        return cls(os.environ["ODOO_URL"], os.environ["ODOO_DB"], os.environ["ODOO_USER"],
                   os.environ["ODOO_API_KEY"])

    def search_read(self, model: str, domain: list, fields: list, limit: int = 50) -> list:
        return self.models.execute_kw(self.db, self.uid, self.key, model, "search_read",
                                      [domain], {"fields": fields, "limit": limit})

    def call(self, model: str, method: str, ids: list):
        return self.models.execute_kw(self.db, self.uid, self.key, model, method, [ids])


# ===========================================================================
# SCENE 2 — THE OFFLINE STAND-IN
# ===========================================================================

class FakeOdoo:
    """In-memory records; supports '=', '!=', 'in' domains and action_post."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, list]] = []
        self.data = {
            "account.move": [
                {"id": 1, "name": "INV/2026/0001", "partner_id": [7, "Brazos Dental"],
                 "move_type": "out_invoice", "state": "draft", "amount_untaxed": 1200.0,
                 "amount_tax": 99.0, "amount_total": 1299.0, "invoice_origin": "S00011",
                 "invoice_date": "2026-10-09"},
                {"id": 2, "name": "INV/2026/0002", "partner_id": [8, "Trinity Machining"],
                 "move_type": "out_invoice", "state": "draft", "amount_untaxed": 800.0,
                 "amount_tax": 66.0, "amount_total": 866.0, "invoice_origin": "S00012",
                 "invoice_date": "2026-10-09"},
                {"id": 3, "name": "INV/2026/0003", "partner_id": [9, "Clear Fork Clinic"],
                 "move_type": "out_invoice", "state": "draft", "amount_untaxed": 2100.0,
                 "amount_tax": 173.25, "amount_total": 2273.25, "invoice_origin": "S00013",
                 "invoice_date": "2026-10-09"},
            ],
            "sale.order": [
                {"id": 11, "name": "S00011", "partner_id": [7, "Brazos Dental"], "state": "sale",
                 "amount_untaxed": 1200.0, "amount_tax": 99.0, "amount_total": 1299.0,
                 "invoice_status": "to invoice"},
                {"id": 12, "name": "S00012", "partner_id": [8, "Trinity Machining"],
                 "state": "sale", "amount_untaxed": 800.0, "amount_tax": 66.0,
                 "amount_total": 866.0, "invoice_status": "to invoice"},
                {"id": 13, "name": "S00013", "partner_id": [9, "Clear Fork Clinic"],
                 "state": "sale", "amount_untaxed": 1200.0, "amount_tax": 99.0,
                 "amount_total": 1299.0, "invoice_status": "to invoice"},
            ],
            "res.partner": [
                {"id": 7, "name": "Brazos Dental", "vat": "US-11", "email": "ap@brazos.example",
                 "country_id": [233, "United States"]},
                {"id": 8, "name": "Trinity Machining", "vat": "US-12",
                 "email": "ap@trinity.example", "country_id": [233, "United States"]},
                {"id": 9, "name": "Clear Fork Clinic", "vat": False,
                 "email": "billing@clearfork.example", "country_id": [233, "United States"]},
            ],
            "account.move.line": [],
        }

    def search_read(self, model: str, domain: list, fields: list, limit: int = 50) -> list:
        def ok(rec):
            for field, op, value in domain:
                v = rec.get(field)
                if isinstance(v, list) and v and field.endswith("_id"):
                    v = v[0]
                if op == "=" and v != value or op == "!=" and v == value \
                        or op == "in" and v not in value:
                    return False
            return True
        rows = [r for r in self.data.get(model, []) if ok(r)][:limit]
        return [{k: r[k] for k in ["id", *fields] if k in r} for r in rows]

    def call(self, model: str, method: str, ids: list):
        self.calls.append((model, method, list(ids)))
        if model == "account.move" and method == "action_post":
            for r in self.data["account.move"]:
                if r["id"] in ids:
                    r["state"] = "posted"
        return True


# ===========================================================================
# SCENE 3 — THE CAST
# ===========================================================================

class OdooReview(World):
    """
    Enter:   client      an OdooClient or FakeOdoo
             owner       the person who accepts
             attester    the person who attests (None: irreversible posting holds)
             successor   the person who takes over a concern
             dry_run     True (default): report the posting call, make none
    """
    name = "odoo"

    def __init__(self, client=None, owner: str = "owner", attester: str | None = None,
                 successor: str = "backup-owner", dry_run: bool = True) -> None:
        self.client = client or FakeOdoo()
        self.owner, self.attester, self.successor = owner, attester, successor
        self.dry_run = dry_run
        self.batches: dict[str, list[int]] = {}
        self.posted: dict[str, str] = {}
        self._n = 0

    def roles(self) -> list[RoleSpec]:
        common = (f"Register concerns with evaluated_process 'invoice-batch', steward "
                  f"'{self.owner}', successor '{self.successor}'.")
        return [
            RoleSpec("ar-clerk", "Accounts receivable clerk",
                     "Read the draft customer invoices (account.move, state draft, move_type "
                     "out_invoice) and their sale orders (invoice_origin) and partners. Every "
                     "discrepancy (amount differs from the sale order, missing customer tax id, "
                     "wrong partner) is a signal: anomaly for a wrong figure, constraint for a "
                     "rule the invoice breaks. Classify it elevated_uncertainty and open "
                     f"review. Tell the controller what you found. {common}",
                     SIGNAL_OPS, principal=self.owner),
            RoleSpec("controller", "Controller",
                     "Decide which draft invoices are ready to post. Check the clerk's signals. "
                     "Register a constraint signal for the batch you intend to post, read the "
                     "records for exactly those invoices (attach the read to that signal), and "
                     "close it by citing that read. Leave out any invoice with an open concern. "
                     "Then propose_batch, register the decision (same id, execution_class "
                     "irreversible, listing the batch's signals), and ask the owner to accept "
                     "(ask_human, accept_decision) with a principal risk claim, the record "
                     "evidence, and known / assumed / uncertain."
                     + (f" Ask for attest_risk_evidence too; it goes to {self.attester}."
                        if self.attester else "")
                     + f" Then request_execution. {common}",
                     SIGNAL_OPS | {"register_decision", "request_execution", "recommend"},
                     principal=self.owner, asks=ASKS),
        ]

    def principal_for(self, agent: str, op: str):
        # The owner accepts, so may neither attest nor resolve a review that
        # touches the decision; both go to the attester when there is one.
        if op in ("attest_risk_evidence", "resolve_review"):
            return self.attester
        return None

    def closure_authority(self, agent: str, signal_args: dict) -> tuple:
        return ("controller",)

    def context(self) -> str:
        return ("Month-end billing in Odoo. Draft customer invoices wait to be posted. Posting "
                "sends them to the books (and usually to the customer); treat it as "
                "irreversible." + (" This run is a DRY RUN: nothing will actually be posted."
                                   if self.dry_run else ""))

    def goal(self) -> str:
        return "Post the draft invoices that are correct; hold any with an unresolved problem."

    # =======================================================================
    # SCENE 4 — SET-UP AND TOOLS
    # =======================================================================

    def setup(self, rt: Runtime) -> None:
        for who in {self.owner, self.successor} | ({self.attester} if self.attester else set()):
            rt.setup_op("register_agent", agent=who, agent_kind="person", by=self.name)
        rt.setup_op("register_agent", agent="odoo-records", agent_kind="instrument",
                    by=self.name)

    def tools(self, rt: Runtime, agent: str):
        def read_records(a, _agent=agent):
            model = a.get("model")
            if model not in READ_MODELS:
                return f"REFUSED: model not readable here. Readable: {', '.join(READ_MODELS)}"
            allowed = READ_MODELS[model]
            # An empty field list makes Odoo return EVERY field, so it falls back
            # to the allowlist rather than passing [] through.
            fields = [f for f in (a.get("fields") or []) if f in allowed] or list(allowed)
            domain = []
            for d in a.get("domain") or []:
                if not (isinstance(d, (list, tuple)) and len(d) == 3):
                    return "REFUSED: each domain term must be [field, op, value]"
                field, op, value = d
                if field not in allowed and field != "id":
                    return (f"REFUSED: domain field {field!r} is not readable here "
                            f"(no dotted paths); fields: id, {', '.join(allowed)}")
                if op not in DOMAIN_OPS:
                    return f"REFUSED: domain operator must be one of {sorted(DOMAIN_OPS)}"
                if isinstance(value, (dict, list)) and op != "in":
                    return "REFUSED: only 'in' takes a list"
                domain.append((field, op, value))
            try:
                limit = max(1, min(MAX_LIMIT, int(a.get("limit", 50))))
                rows = self.client.search_read(model, domain, fields, limit)
            except Exception as exc:                                  # network or Odoo fault
                return f"REFUSED: read failed: {exc}"
            body = json.dumps(rows, default=str)
            key = ("odoo-records", model, json.dumps(domain, default=str), tuple(fields), body)
            if key not in rt._minted:
                self._n += 1
            ev = rt.mint_evidence(f"odoo-read-{self._n}", f"{model} {domain}: {body[:3000]}",
                                  "Odoo database read", "primary_document", "odoo-records",
                                  _agent, a.get("signal_ids") or (), key=key)
            return f"{body[:8000]}\n\n{ev}"

        tools = [ToolSpec(
            "read_records",
            "Read Odoo records (an instrument: the read is qualifying evidence). Models: "
            + "; ".join(f"{m} ({', '.join(f)})" for m, f in READ_MODELS.items())
            + ". domain is a list of [field, op, value] with op '=', '!=' or 'in'.",
            text_arg({"model": {"type": "string", "enum": list(READ_MODELS)},
                      "domain": {"type": "array", "items": {"type": "array"}},
                      "fields": {"type": "array", "items": {"type": "string"}},
                      "limit": {"type": "integer"},
                      "signal_ids": {"type": "array", "items": {"type": "string"}}},
                     ["model"]), read_records)]

        if agent == "controller":
            def propose_batch(a):
                did = a.get("decision_id", "")
                if not isinstance(did, str) or not did:
                    return "REFUSED: decision_id must be a non-empty string"
                if did in self.batches or did in rt.sup.decisions:
                    return (f"REFUSED: the batch for {did} is fixed once proposed (and its "
                            "decision registered); propose a new decision id instead")
                ids = [int(i) for i in a.get("move_ids", [])]
                rows = self.client.search_read("account.move", [("id", "in", ids)],
                                               ["state", "move_type", "name"], len(ids) or 1)
                bad = [r.get("name", r["id"]) for r in rows
                       if r.get("state") != "draft" or r.get("move_type") not in
                       ("out_invoice", "out_refund")]
                missing = set(ids) - {r["id"] for r in rows}
                if not ids or bad or missing:
                    return (f"REFUSED: batch must be existing draft customer invoices; "
                            f"problems: {bad or ''} {sorted(missing) or ''}")
                self.batches[did] = ids
                return (f"batch {did} = {[r.get('name') for r in rows]}. Register a decision "
                        f"with decision_id '{did}'.")
            tools.append(ToolSpec("propose_batch", "Name the draft invoices (account.move "
                                  "ids) a posting decision covers. Posting happens only if "
                                  "the gate permits that decision.",
                                  text_arg({"decision_id": {"type": "string"},
                                            "move_ids": {"type": "array",
                                                         "items": {"type": "integer"}}},
                                           ["decision_id", "move_ids"]), propose_batch))
        return tools

    # =======================================================================
    # SCENE 5 — POSTING
    # =======================================================================

    def precheck(self, rt: Runtime, decision_id: str):
        if decision_id not in self.batches:
            return f"no batch was proposed for {decision_id}"
        return None

    def describe(self, rt: Runtime, decision_id: str) -> str:
        ids = self.batches.get(decision_id)
        if not ids:
            return f"no batch proposed for {decision_id}"
        rows = self.client.search_read("account.move", [("id", "in", ids)],
                                       ["name", "partner_id", "amount_total", "state"], len(ids))
        lines = [f"  {r.get('name')}  {r.get('partner_id', [None, ''])[1] if isinstance(r.get('partner_id'), list) else r.get('partner_id')}"
                 f"  {r.get('amount_total')}  ({r.get('state')})" for r in rows]
        return (f"{'DRY RUN: ' if self.dry_run else ''}post {len(ids)} invoice(s):\n"
                + "\n".join(lines) + "\n" + self.open_signals_text(rt))

    def execute(self, rt: Runtime, decision_id: str, gate) -> str:
        ids = self.batches.get(decision_id)
        if not ids:
            self.posted[decision_id] = "no batch proposed; nothing posted"
            return self.posted[decision_id]
        if self.dry_run:
            self.posted[decision_id] = f"DRY RUN: would call account.move.action_post({ids})"
            return self.posted[decision_id]
        self.client.call("account.move", "action_post", ids)
        rows = self.client.search_read("account.move", [("id", "in", ids)], ["name", "state"],
                                       len(ids))
        self.posted[decision_id] = "posted: " + ", ".join(
            f"{r.get('name')}={r.get('state')}" for r in rows)
        return self.posted[decision_id]

    # =======================================================================
    # SCENE 6 — DONE AND REPORT
    # =======================================================================

    def done(self, rt: Runtime) -> bool:
        return bool(self.posted)

    def report(self, rt: Runtime) -> dict:
        return {"dry_run": self.dry_run, "batches": self.batches, "posted": self.posted}

# EXEUNT — end of file.
