import json
from datetime import date
from pathlib import Path

import pytest

from intake.extract import KeywordExtractor
from intake.policy import current, load, parse
from intake.rules import decide
from intake.schema import IntakeForm

FORMS = {f["submission_id"]: f for f in json.loads((Path(__file__).parent.parent / "samples/forms.json").read_text())}

EXPECTED = {   # submission -> (route, missing, citations)
    "S01": ("book_now", [], ["payers@v3"]),
    "S02": ("needs_info", ["date_of_birth", "member_id"], []),
    "S03": ("clinical_review", [], ["clinical_review@v1"]),
    "S04": ("self_pay_offer", [], ["payers@v3"]),
    "S05": ("needs_info", ["physician_referral"], ["payers@v3"]),
    "S06": ("self_pay_offer", [], ["payers@v3"]),
    "S07": ("needs_info", ["guardian_consent"], ["clinical_review@v1"]),
    "S08": ("self_pay_offer", [], []),
}


def run(form_dict):
    form = IntakeForm(**form_dict)
    return decide(form, KeywordExtractor().extract(form))


@pytest.mark.parametrize("sid", sorted(EXPECTED))
def test_sample_routes(sid):
    d = run(FORMS[sid])
    assert (d.route, d.missing, d.citations) == EXPECTED[sid]


def test_policy_version_follows_the_submission_date():
    humana = dict(FORMS["S04"])
    humana["submitted_at"] = "2026-06-15T12:00:00Z"          # contract still active (payers v2)
    d = run(humana)
    assert (d.route, d.citations) == ("book_now", ["payers@v2"])


def test_current_picks_latest_effective_version():
    ps = load()
    assert current(ps, "payers", date(2026, 6, 30)).version == 2
    assert current(ps, "payers", date(2026, 7, 1)).version == 3
    with pytest.raises(LookupError):
        current(ps, "payers", date(2025, 12, 31))


def test_policy_file_without_json_block_is_rejected():
    with pytest.raises(ValueError):
        parse("---\nid: x\nversion: 1\neffective_from: 2026-01-01\n---\nno rules here\n")


def test_eating_disorder_beats_everything_else():
    f = dict(FORMS["S02"], reason_text="I've been restricting and purging; also cholesterol")
    d = run(f)
    assert d.route == "clinical_review"
    assert "date_of_birth" in d.crm.task              # the reviewer still sees what is missing


def test_bcbs_without_state_name_is_fine_in_illinois():
    f = dict(FORMS["S06"], state="IL")
    assert run(f).route == "book_now"


def test_medicare_without_covered_condition_is_offered_self_pay():
    f = dict(FORMS["S05"], reason_text="I was referred for weight management")
    d = run(f)
    assert d.route == "self_pay_offer" and "diabetes" in d.reasons[-1]


def test_crm_payload_carries_categories_not_free_text():
    d = run(FORMS["S03"])
    blob = json.dumps(d.crm.model_dump())
    assert "binge" not in blob and "eating_disorder" in blob
