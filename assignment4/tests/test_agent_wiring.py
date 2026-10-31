"""Offline check of the agent plumbing: a scripted fake model drives real tool calls
through create_agent, so tool wiring, audit logging, memory and the guardrail are tested
without an API key. Model *judgement* is covered by eval.py against a real LLM."""
import sys
from datetime import datetime
from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent as agent_mod  # noqa: E402
from backend import IST, Backend  # noqa: E402

NOW = datetime(2026, 11, 2, 10, 0, tzinfo=IST)


class ScriptedModel(GenericFakeChatModel):
    seen: list = []

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        ScriptedModel.seen.append(len(messages))
        return super()._generate(messages, *args, **kwargs)


def tool_call(name, **args):
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{name}_{len(args)}"}])


def make_agent(monkeypatch, script):
    monkeypatch.setattr(agent_mod, "init_chat_model", lambda *a, **k: ScriptedModel(messages=iter(script)))
    ScriptedModel.seen = []
    return agent_mod.CollectionsAgent(backend=Backend(now=NOW))


def test_tools_execute_and_memory_persists_across_turns(monkeypatch):
    a = make_agent(monkeypatch, [
        tool_call("verify_identity", account_id="A1001", dob="1988-04-12"),
        AIMessage(content="Thanks Ravi, you're verified."),
        tool_call("record_promise_to_pay", account_id="A1001", amount="3000", pay_date="2026-11-05"),
        AIMessage(content="Recorded 3000 for 5 November."),
    ])
    assert a.send("A1001, 1988-04-12") == "Thanks Ravi, you're verified."
    assert a.send("I'll pay 3000 on the 5th") == "Recorded 3000 for 5 November."
    assert a.backend.ptps == [{"account_id": "A1001", "amount_paise": 300000, "pay_date": "2026-11-05"}]
    assert [c["tool"] for c in a.backend.audit] == ["verify_identity", "record_promise_to_pay"]
    # second turn's model call saw the first turn's history (checkpointer memory)
    assert ScriptedModel.seen[2] > ScriptedModel.seen[0]


def test_rejected_tool_call_returns_reason_to_model_and_stores_nothing(monkeypatch):
    a = make_agent(monkeypatch, [
        tool_call("verify_identity", account_id="A1001", dob="1988-04-12"),
        tool_call("record_promise_to_pay", account_id="A1001", amount="500", pay_date="2026-11-05"),
        AIMessage(content="The minimum is 3000."),
    ])
    a.send("A1001 1988-04-12, I'll pay 500")
    assert a.backend.ptps == []
    last = a.backend.audit[-1]
    assert last["tool"] == "record_promise_to_pay" and last["result"]["ok"] is False
    assert "minimum due" in last["result"]["rejected"]


def test_guardrail_replaces_threatening_reply(monkeypatch):
    a = make_agent(monkeypatch, [AIMessage(content="If you don't pay we will contact your employer.")])
    assert a.send("I won't pay") == agent_mod.SAFE_FALLBACK
    assert len(a.guardrail_hits) == 1
