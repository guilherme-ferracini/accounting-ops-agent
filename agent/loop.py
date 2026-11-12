"""A small tool-using agent with native tool calling for Anthropic and OpenAI,
plus a deterministic 'mock' planner so the demo and tests run without keys.

Guardrails: a step limit, read-only tools, and a full trace of every tool call
so a person can audit how each answer was produced."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .tools import TOOL_SPECS, Toolbox

SYSTEM = (
    "You are an operations assistant inside a Brazilian accounting firm. Answer the "
    "team's questions about clients using ONLY the tools provided. Always look up the "
    "client first. Never estimate numbers yourself: quote the tool results. If a tool "
    "returns an error, say so plainly. Answer in English, in at most 6 short lines."
)

DEFAULT_MODELS = {"anthropic": "claude-sonnet-5-5", "openai": "gpt-4.1-mini"}


@dataclass
class Step:
    tool: str
    arguments: Dict[str, Any]
    result: Dict[str, Any]


@dataclass
class AgentResult:
    answer: str
    trace: List[Step] = field(default_factory=list)


class Agent:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None,
                 toolbox: Optional[Toolbox] = None, max_steps: int = 6) -> None:
        self.provider = (provider or os.getenv("LLM_PROVIDER") or "mock").lower()
        self.model = model or os.getenv("LLM_MODEL") or DEFAULT_MODELS.get(self.provider, "mock")
        self.tools = toolbox or Toolbox()
        self.registry = self.tools.registry()
        self.max_steps = max_steps

    def run(self, question: str) -> AgentResult:
        if self.provider == "anthropic":
            return self._run_anthropic(question)
        if self.provider == "openai":
            return self._run_openai(question)
        if self.provider == "mock":
            return self._run_mock(question)
        raise ValueError(f"Unknown provider {self.provider}")

    def _call(self, name: str, args: Dict[str, Any], trace: List[Step]) -> Dict[str, Any]:
        fn = self.registry.get(name)
        result = {"error": f"Unknown tool {name}"} if fn is None else fn(**args)
        trace.append(Step(name, args, result))
        return result

    # -- Anthropic: native tool use -------------------------------------------
    def _run_anthropic(self, question: str) -> AgentResult:
        import anthropic

        client = anthropic.Anthropic()
        messages: List[Dict[str, Any]] = [{"role": "user", "content": question}]
        trace: List[Step] = []
        for _ in range(self.max_steps):
            resp = client.messages.create(model=self.model, max_tokens=1024, system=SYSTEM,
                                          tools=TOOL_SPECS, messages=messages)
            if resp.stop_reason != "tool_use":
                text = "".join(b.text for b in resp.content if b.type == "text")
                return AgentResult(text, trace)
            messages.append({"role": "assistant", "content": resp.content})
            results = []
            for block in resp.content:
                if block.type == "tool_use":
                    out = self._call(block.name, dict(block.input), trace)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(out)})
            messages.append({"role": "user", "content": results})
        return AgentResult("Stopped: step limit reached.", trace)

    # -- OpenAI: function calling -------------------------------------------
    def _run_openai(self, question: str) -> AgentResult:
        import openai

        client = openai.OpenAI()
        tools = [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                                    "parameters": t["input_schema"]}} for t in TOOL_SPECS]
        messages: List[Dict[str, Any]] = [{"role": "system", "content": SYSTEM},
                                          {"role": "user", "content": question}]
        trace: List[Step] = []
        for _ in range(self.max_steps):
            msg = client.chat.completions.create(model=self.model, tools=tools, messages=messages).choices[0].message
            if not msg.tool_calls:
                return AgentResult(msg.content or "", trace)
            messages.append(msg.model_dump(exclude_none=True))
            for call in msg.tool_calls:
                out = self._call(call.function.name, json.loads(call.function.arguments or "{}"), trace)
                messages.append({"role": "tool", "tool_call_id": call.id, "content": json.dumps(out)})
        return AgentResult("Stopped: step limit reached.", trace)

    # -- Mock: deterministic planner for demos and tests -----------------------
    def _run_mock(self, question: str) -> AgentResult:
        trace: List[Step] = []
        q = question.lower()
        name = next((c["name"] for c in self.tools.clients
                     if c["name"].split()[0].lower() in q), None)
        if name is None:
            return AgentResult("I could not identify the client in the question.", trace)
        client = self._call("find_client", {"name": name.split()[0]}, trace)
        if "error" in client:
            return AgentResult(client["error"], trace)
        cid = client["id"]
        lines = [f"{client['name']} ({client['regime'].replace('_', ' ')})."]

        if re.search(r"\b(tax|das|simples)\b", q):
            r = self._call("estimate_simples_tax", {"client_id": cid}, trace)
            lines.append(r["error"] if "error" in r else
                         f"Effective Simples rate {r['effective_rate']:.2%} (annex {r['annex']}); "
                         f"estimated DAS R$ {r['estimated_das']:,.2f} on R$ {r['month_revenue']:,.2f} of revenue.")
        if re.search(r"\b(deadline|deadlines|due|routine|routines)\b", q):
            ref = (re.search(r"\d{4}-\d{2}", q) or [None])[0]
            r = self._call("monthly_routines", {"client_id": cid, "reference": ref} if ref else {"client_id": cid}, trace)
            lines.append("Due: " + "; ".join(f"{i['routine']} on {i['due']}" for i in r["routines"]) + ".")
        if re.search(r"\b(document|documents|pending|missing)\b", q):
            r = self._call("pending_documents", {"client_id": cid}, trace)
            docs = [d["document"] for d in r["pending"]]
            lines.append("Pending: " + (", ".join(docs) if docs else "nothing") + ".")
        if len(trace) == 1:
            lines.append("Ask about taxes, deadlines or pending documents.")
        lines.append("(Demo mode: rule-based planner. Set LLM_PROVIDER=anthropic or openai for the real agent.)")
        return AgentResult("\n".join(lines), trace[: self.max_steps])
