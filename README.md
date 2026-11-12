# Accounting Ops Agent

[![tests](https://github.com/guilherme-ferracini/accounting-ops-agent/actions/workflows/tests.yml/badge.svg)](https://github.com/guilherme-ferracini/accounting-ops-agent/actions)

A **tool-using AI agent** that answers an accounting team's day-to-day questions about clients, such as "what's Bussola's estimated DAS and what are we still missing from them?", by calling real functions instead of guessing.

It uses native tool calling on **Anthropic (Claude)** or **OpenAI**, plus a deterministic mock planner so it runs and is tested without any API key.

## Why this exists

In an accounting firm, the same questions reach the senior staff all day: which regime a client is in, how much tax to expect, what's due next week, which documents are still missing. The answers already live in systems; people just need them fast and right.

The design choices are the ones I apply in production automation:

- **The model chooses, the code computes.** The LLM decides which tool to call; the Simples Nacional math, deadlines and document lists come from tested Python functions. No number in an answer is produced by the model.
- **Read-only tools.** The agent can look things up but cannot change anything, so a wrong call cannot cause damage.
- **Auditable.** Every tool call and its result is kept in a trace (`--trace`), so anyone can see how an answer was produced.
- **Bounded.** A step limit stops runaway loops.

## How it works

```
question ──► model ──► tool call ──► Python function ──► result ──► model ──► … ──► answer
                         (find_client, estimate_simples_tax,
                          monthly_routines, pending_documents)
```

## Quickstart

```bash
pip install -r requirements.txt

# Demo mode: no API key needed
python -m agent "What is the estimated DAS for Bussola and which documents are pending?" --trace
```

```
  [1] find_client({"name": "Bussola"})
  [2] estimate_simples_tax({"client_id": "CL-002"})
  [3] pending_documents({"client_id": "CL-002"})
Bussola Software Ltda (simples).
Effective Simples rate 10.75% (annex III); estimated DAS R$ 6,268.61 on R$ 58,300.00 of revenue.
Pending: Payroll changes - November.
```

With a real model (it decides the tool sequence on its own):

```bash
export LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=...     # or LLM_PROVIDER=openai OPENAI_API_KEY=...
python -m agent --trace                                 # interactive mode
```

## Tools

| Tool | What it returns |
|---|---|
| `find_client` | id, tax regime, revenue, headcount (partial, accent-insensitive name match) |
| `estimate_simples_tax` | effective rate from the Simples Nacional tables (annexes I and III) and estimated DAS |
| `monthly_routines` | monthly tax and payroll routines due for that client's profile |
| `pending_documents` | documents the firm is still waiting for |

Adding a tool means writing a function, a JSON schema and a test. The agent loop does not change.

## Tests

```bash
python -m pytest -q
```

## Notes

- All clients and figures are fictional.
- Deadlines here are nominal days; see [tax-obligations-calendar](https://github.com/guilherme-ferracini/tax-obligations-calendar) for weekend and holiday adjustment.

## License

MIT
