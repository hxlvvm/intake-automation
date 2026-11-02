from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from intake.extract import ClaudeExtractor, ExtractionError, KeywordExtractor
from intake.schema import Extracted, IntakeForm


def form(ins="", why="", when="2026-08-10T12:00:00Z"):
    return IntakeForm(submission_id="X", submitted_at=when, first_name="A", last_name="B",
                      insurance_text=ins, reason_text=why)


def test_prediabetes_is_not_read_as_diabetes():
    assert KeywordExtractor().extract(form(why="I have pre-diabetes")).conditions == ["prediabetes"]


def test_longest_carrier_alias_wins():
    k = KeywordExtractor()
    assert k.extract(form("BCBS of Illinois PPO")).carrier == "BCBS IL"
    assert k.extract(form("blue cross, not sure which")).carrier == "BCBS"


def test_member_ids_including_medicare_mbi():
    k = KeywordExtractor()
    assert k.extract(form("Aetna id W123456789")).member_id == "W123456789"
    assert k.extract(form("Medicare 1EG4TE5MK73")).member_id == "1EG4TE5MK73"


def test_referral_mentions():
    k = KeywordExtractor()
    assert k.extract(form(why="my doctor referred me")).has_referral is True
    assert k.extract(form(why="I don't have a referral yet")).has_referral is False
    assert k.extract(form(why="diabetes")).has_referral is None


class FakeClient:
    """Stands in for anthropic.Anthropic: records the call and returns a canned parse result."""

    def __init__(self, parsed, stop_reason="end_turn"):
        self.calls = []
        self.messages = SimpleNamespace(parse=self._parse)
        self._resp = SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)

    def _parse(self, **kw):
        self.calls.append(kw)
        return self._resp


def test_claude_extractor_uses_the_schema_and_lists_known_carriers():
    fake = FakeClient(Extracted(carrier="Aetna", member_id="W1", conditions=["pcos"]))
    out = ClaudeExtractor(client=fake).extract(form("aetna"))
    call = fake.calls[0]
    assert call["output_format"] is Extracted and call["model"] == "claude-opus-5-5"
    prompt = call["messages"][0]["content"]
    assert "Aetna" in prompt and "BCBS IL" in prompt and "Humana" in prompt  # out-of-network names too, to route them
    assert out.carrier == "Aetna"


def test_claude_extractor_drops_an_invented_carrier():
    fake = FakeClient(Extracted(carrier="Acme Health", conditions=["other"]))
    assert ClaudeExtractor(client=fake).extract(form("acme")).carrier is None


def test_claude_refusal_raises_so_a_person_reviews():
    fake = FakeClient(None, stop_reason="refusal")
    with pytest.raises(ExtractionError):
        ClaudeExtractor(client=fake).extract(form("x"))
