"""End to end: every sample form through the service and into the mock CRM, as the n8n workflow would run it."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import intake.service as service_module
from intake.extract import ExtractionError
from intake.flow import run
from mock_crm.app import app as crm_app

FORMS = json.loads((Path(__file__).parent.parent / "samples/forms.json").read_text())


@pytest.fixture
def clients():
    service, crm = TestClient(service_module.app), TestClient(crm_app)
    crm.post("/_reset")
    return service, crm


def test_all_samples_reach_the_crm_with_tasks_only_where_needed(clients):
    service, crm = clients
    routes = [run(f, service, crm)["route"] for f in FORMS]
    state = crm.get("/_calls").json()
    assert len(state["contacts"]) == len(FORMS)
    assert len(state["tasks"]) == sum(r != "book_now" for r in routes)
    stages = {c["custom_fields"]["intake_id"]: c["stage"] for c in state["contacts"].values()}
    assert stages["S01"] == "Ready to book" and stages["S03"] == "Clinical review"
    # minimum necessary: no free-text reason reaches the CRM
    assert "binge" not in json.dumps(state)


def test_a_resubmission_updates_the_same_contact(clients):
    service, crm = clients
    first = run(FORMS[1], service, crm)                       # missing date of birth and member id
    fixed = dict(FORMS[1], submission_id="S02b", date_of_birth="1985-03-03", insurance_text="Cigna 77123456")
    second = run(fixed, service, crm)
    assert first["contact_id"] == second["contact_id"]
    assert (first["route"], second["route"]) == ("needs_info", "book_now")
    assert crm.get("/_calls").json()["contacts"][first["contact_id"]]["stage"] == "Ready to book"


def test_failed_extraction_goes_to_a_person(clients, monkeypatch):
    service, crm = clients

    class Broken:
        def extract(self, form):
            raise ExtractionError("model gave no record")

    monkeypatch.setattr(service_module, "extractor", Broken())
    assert run(FORMS[0], service, crm)["route"] == "needs_info"
