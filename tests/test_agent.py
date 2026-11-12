import pytest

from agent.loop import Agent
from agent.tools import Toolbox

TB = Toolbox()


def test_find_client_partial_and_accents():
    assert TB.find_client("bussola")["id"] == "CL-002"
    assert "error" in TB.find_client("nonexistent")


def test_simples_effective_rate_annex_iii():
    r = TB.estimate_simples_tax("CL-002")          # RBT12 642,000 -> 3rd bracket: 13.5%, deduct 17,640
    expected = (642000 * 0.135 - 17640) / 642000
    assert r["effective_rate"] == pytest.approx(expected, abs=1e-6)
    assert r["estimated_das"] == pytest.approx(58300 * expected, abs=0.01)


def test_simples_first_bracket_uses_nominal_rate():
    r = TB.estimate_simples_tax("CL-004")          # RBT12 168,000 -> 6%
    assert r["effective_rate"] == 0.06


def test_non_simples_client_returns_error():
    assert "error" in TB.estimate_simples_tax("CL-003")


def test_routines_depend_on_profile():
    names = {i["routine"] for i in TB.monthly_routines("CL-004", "2026-11")["routines"]}
    assert names == {"DAS (Simples Nacional)"}       # no employees, Simples
    cedro = TB.monthly_routines("CL-003", "2026-12")
    assert {"PIS/COFINS", "FGTS Digital"} <= {i["routine"] for i in cedro["routines"]}
    assert all(i["due"].startswith("2027-01") for i in cedro["routines"])


def test_mock_agent_calls_the_right_tools():
    res = Agent("mock").run("What is the estimated DAS for Bussola and which documents are pending?")
    assert [s.tool for s in res.trace] == ["find_client", "estimate_simples_tax", "pending_documents"]
    assert "Payroll changes" in res.answer


def test_mock_agent_unknown_client():
    res = Agent("mock").run("Taxes for Zeta Corp?")
    assert res.trace == []
