"""The worlds a swarm can work in: simorg (simulated org), release, odoo (invoice posting)."""
from .base import World
from .odoo import FakeOdoo, OdooClient, OdooReview
from .release import GitRelease
from .simorg import SimOrg

WORLDS = {"simorg": SimOrg, "release": GitRelease, "odoo": OdooReview}

__all__ = ["World", "SimOrg", "GitRelease", "OdooReview", "OdooClient", "FakeOdoo", "WORLDS"]
