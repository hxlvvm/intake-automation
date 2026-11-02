"""Typed contracts between the website form, the extractor, the rules and the CRM."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

Condition = Literal["diabetes", "prediabetes", "pcos", "kidney_disease", "eating_disorder",
                    "weight_management", "heart_health", "gi", "other"]
Route = Literal["book_now", "needs_info", "clinical_review", "self_pay_offer"]


class IntakeForm(BaseModel):
    """What the website's intake form posts to the webhook."""
    submission_id: str
    submitted_at: datetime
    first_name: str
    last_name: str
    email: str | None = None
    phone: str | None = None
    date_of_birth: date | None = None
    state: str | None = None        # free text: "Illinois", "il", "IL"
    insurance_text: str = ""        # free text: "BCBS of Illinois PPO, member id XOF123456789"
    reason_text: str = ""           # free text: why they want to see a dietitian


class Extracted(BaseModel):
    """What the extractor reads out of the free-text fields."""
    carrier: str | None = Field(None, description="Canonical carrier name from the policy list, 'BCBS' if only "
                                                  "'Blue Cross' without a state is given, or null")
    self_pay: bool = Field(False, description="True if the patient says they have no insurance or will pay themselves")
    member_id: str | None = Field(None, description="Insurance member id exactly as written, or null")
    conditions: list[Condition] = Field(default_factory=list)
    has_referral: bool | None = Field(None, description="True/False if the text says so, null if not mentioned")


class CrmPayload(BaseModel):
    contact: dict
    stage: str
    task: str | None


class Decision(BaseModel):
    submission_id: str
    route: Route
    missing: list[str]
    reasons: list[str]
    citations: list[str]            # "<policy id>@v<version>" for every policy the decision used
    state: str | None
    age: int | None
    extracted: Extracted
    crm: CrmPayload
