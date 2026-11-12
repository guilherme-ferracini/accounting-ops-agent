"""python -m agent "What is the estimated DAS for Bussola and what documents are pending?" [--trace]"""

from __future__ import annotations

import argparse
import json

from .loop import Agent


def main() -> None:
    p = argparse.ArgumentParser(description="Tool-using operations agent for an accounting firm")
    p.add_argument("question", nargs="?", help="leave empty for interactive mode")
    p.add_argument("--provider", default=None, help="mock (default), anthropic or openai")
    p.add_argument("--model", default=None)
    p.add_argument("--trace", action="store_true", help="print every tool call")
    a = p.parse_args()

    agent = Agent(a.provider, a.model)

    def ask(q: str) -> None:
        res = agent.run(q)
        if a.trace:
            for i, s in enumerate(res.trace, 1):
                print(f"  [{i}] {s.tool}({json.dumps(s.arguments)})")
        print(res.answer, "\n")

    if a.question:
        ask(a.question)
        return
    print("Ask about a client (empty line to quit).")
    while True:
        q = input("> ").strip()
        if not q:
            break
        ask(q)


if __name__ == "__main__":
    main()
