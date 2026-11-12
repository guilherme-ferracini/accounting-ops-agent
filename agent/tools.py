"""Tools the agent can call. Each tool is a plain, tested Python function plus a
JSON schema the model sees. The model decides *which* tool to call; the numbers
always come from code."""

from __future__ import annotations

import json
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

DATA_PATH = Path(__file__).parents[1] / "samples" / "clients.json"

# Simples Nacional (LC 123/2006): (RBT12 upper limit, nominal rate, amount to deduct)
SIMPLES_ANNEXES = {
    "I": [  # commerce
        (180000.00, 0.04, 0.0),
        (360000.00, 0.073, 5940.0),
        (720000.00, 0.095, 13860.0),
        (1800000.00, 0.107, 22500.0),
        (3600000.00, 0.143, 87300.0),
        (4800000.00, 0.19, 378000.0),
    ],
    "III": [  # services
        (180000.00, 0.06, 0.0),
        (360000.00, 0.112, 9360.0),
        (720000.00, 0.135, 17640.0),
        (1800000.00, 0.16, 35640.0),
        (3600000.00, 0.21, 125640.0),
        (4800000.00, 0.33, 648000.0),
    ],
}

# Monthly federal routines handled by the firm (day of the following month)
MONTHLY_ROUTINES = [
    {"name": "DAS (Simples Nacional)", "day": 20, "applies": lambda c: c["regime"] == "simples"},
    {"name": "eSocial payroll closing", "day": 15, "applies": lambda c: c["has_employees"]},
    {"name": "FGTS Digital", "day": 20, "applies": lambda c: c["has_employees"]},
    {"name": "PIS/COFINS", "day": 25, "applies": lambda c: c["regime"] != "simples"},
]


def _norm(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()


class Toolbox:
    def __init__(self, data_path: Path = DATA_PATH) -> None:
        data = json.loads(data_path.read_text(encoding="utf-8"))
        self.clients: List[Dict[str, Any]] = data["clients"]
        self.pending: List[Dict[str, Any]] = data["pending_documents"]

    # -- tools ---------------------------------------------------------------

    def find_client(self, name: str) -> Dict[str, Any]:
        """Find a client by (partial) name."""
        hits = [c for c in self.clients if _norm(name) in _norm(c["name"])]
        if not hits:
            return {"error": f"No client matches '{name}'."}
        if len(hits) > 1:
            return {"error": "Ambiguous name.", "candidates": [c["name"] for c in hits]}
        return hits[0]

    def estimate_simples_tax(self, client_id: str) -> Dict[str, Any]:
        """Effective Simples Nacional rate and estimated DAS for last month's revenue."""
        c = self._client(client_id)
        if c is None:
            return {"error": f"Unknown client {client_id}."}
        if c["regime"] != "simples":
            return {"error": f"{c['name']} is not in Simples Nacional (regime: {c['regime']})."}
        rbt12, revenue = c["rbt12"], c["last_month_revenue"]
        for limit, rate, deduct in SIMPLES_ANNEXES[c["simples_annex"]]:
            if rbt12 <= limit:
                effective = rate if rbt12 <= 180000 else (rbt12 * rate - deduct) / rbt12
                return {
                    "client": c["name"],
                    "annex": c["simples_annex"],
                    "rbt12": rbt12,
                    "nominal_rate": rate,
                    "effective_rate": round(effective, 6),
                    "month_revenue": revenue,
                    "estimated_das": round(revenue * effective, 2),
                }
        return {"error": "RBT12 above the Simples Nacional limit (R$ 4.8M)."}

    def monthly_routines(self, client_id: str, reference: Optional[str] = None) -> Dict[str, Any]:
        """Monthly routines due next month for a client. reference = 'YYYY-MM' (defaults to current month)."""
        c = self._client(client_id)
        if c is None:
            return {"error": f"Unknown client {client_id}."}
        ref = reference or date.today().strftime("%Y-%m")
        year, month = map(int, ref.split("-"))
        due_year, due_month = (year + 1, 1) if month == 12 else (year, month + 1)
        items = [
            {"routine": r["name"], "due": f"{due_year}-{due_month:02d}-{r['day']:02d}"}
            for r in MONTHLY_ROUTINES if r["applies"](c)
        ]
        return {"client": c["name"], "reference": ref, "routines": items,
                "note": "Nominal dates; weekends and holidays may move them."}

    def pending_documents(self, client_id: str) -> Dict[str, Any]:
        """Documents the firm is still waiting for from a client."""
        c = self._client(client_id)
        if c is None:
            return {"error": f"Unknown client {client_id}."}
        docs = [d for d in self.pending if d["client_id"] == client_id]
        return {"client": c["name"], "pending": docs}

    # -- plumbing ------------------------------------------------------------

    def _client(self, client_id: str) -> Optional[Dict[str, Any]]:
        return next((c for c in self.clients if c["id"] == client_id), None)

    def registry(self) -> Dict[str, Callable[..., Dict[str, Any]]]:
        return {
            "find_client": self.find_client,
            "estimate_simples_tax": self.estimate_simples_tax,
            "monthly_routines": self.monthly_routines,
            "pending_documents": self.pending_documents,
        }


TOOL_SPECS = [
    {
        "name": "find_client",
        "description": "Look up a client of the accounting firm by name. Returns id, tax regime, revenue and headcount.",
        "input_schema": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
    },
    {
        "name": "estimate_simples_tax",
        "description": "Compute the Simples Nacional effective rate and the estimated DAS for a client's last month revenue.",
        "input_schema": {"type": "object", "properties": {"client_id": {"type": "string"}}, "required": ["client_id"]},
    },
    {
        "name": "monthly_routines",
        "description": "List the monthly tax and payroll routines due for a client. reference is the competence month as YYYY-MM.",
        "input_schema": {
            "type": "object",
            "properties": {"client_id": {"type": "string"}, "reference": {"type": "string"}},
            "required": ["client_id"],
        },
    },
    {
        "name": "pending_documents",
        "description": "List documents the firm is still waiting for from a client.",
        "input_schema": {"type": "object", "properties": {"client_id": {"type": "string"}}, "required": ["client_id"]},
    },
]
