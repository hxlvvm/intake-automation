"""Turn a form plus its extracted record into a routing decision, citing the policies used.

Order matters and is part of the spec: safety review first, then consent, then missing information, then coverage.
"""
from datetime import date

from .policy import current, load
from .schema import CrmPayload, Decision, Extracted, IntakeForm

STATES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR", "california": "CA", "colorado": "CO",
    "connecticut": "CT", "delaware": "DE", "district of columbia": "DC", "florida": "FL", "georgia": "GA",
    "hawaii": "HI", "idaho": "ID", "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD", "massachusetts": "MA", "michigan": "MI",
    "minnesota": "MN", "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD", "tennessee": "TN", "texas": "TX",
    "utah": "UT", "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
STAGES = {"book_now": "Ready to book", "needs_info": "Needs info", "clinical_review": "Clinical review",
          "self_pay_offer": "Self-pay offer"}


def state_code(s):
    if not s:
        return None
    s = s.strip()
    if s.upper() in STATES.values():
        return s.upper()
    return STATES.get(s.lower())


def age_on(dob, day):
    return day.year - dob.year - ((day.month, day.day) < (dob.month, dob.day))


def decide(form: IntakeForm, ex: Extracted, policies=None) -> Decision:
    policies = policies or load()
    day = form.submitted_at.date()
    payers = current(policies, "payers", day)
    review = current(policies, "clinical_review", day)
    state = state_code(form.state)
    age = age_on(form.date_of_birth, day) if form.date_of_birth else None

    missing = []
    if not (form.email or form.phone):
        missing.append("email_or_phone")
    if age is None:
        missing.append("date_of_birth")
    if state is None:
        missing.append("state")
    if ex.carrier is None and not ex.self_pay:
        missing.append("insurance_carrier")
    if ex.carrier and not ex.member_id:
        missing.append("member_id")

    reasons, cites = [], []
    if set(ex.conditions) & set(review.rules["review_conditions"]):
        route, cites = "clinical_review", [review.cite]
        reasons.append("an eating disorder is mentioned: dietitian review before booking")
    elif age is not None and age < review.rules["minimum_age_without_guardian"]:
        route, cites = "needs_info", [review.cite]
        missing.append("guardian_consent")
        reasons.append(f"patient is {age}: guardian consent needed")
    elif missing:
        route = "needs_info"
        reasons.append("required details are missing")
    elif ex.self_pay:
        route = "self_pay_offer"
        reasons.append("patient chose self-pay")
    else:
        route, cites = _coverage(ex, state, payers, reasons, missing)

    task = None
    if route == "needs_info":
        task = "Ask the patient for: " + ", ".join(missing)
    elif route == "clinical_review":
        task = "Dietitian review before booking (eating disorder mentioned)" + \
               (f"; also missing: {', '.join(missing)}" if missing else "")
    elif route == "self_pay_offer":
        task = "Send self-pay pricing: " + reasons[-1]
    contact = dict(first_name=form.first_name, last_name=form.last_name, email=form.email, phone=form.phone,
                   state=state, tags=[f"route:{route}"] + ([f"carrier:{ex.carrier}"] if ex.carrier else []),
                   custom_fields=dict(member_id=ex.member_id, conditions=ex.conditions, intake_id=form.submission_id))
    # Minimum necessary: the CRM gets categories, never the patient's free text.
    return Decision(submission_id=form.submission_id, route=route, missing=missing, reasons=reasons, citations=cites,
                    state=state, age=age, extracted=ex, crm=CrmPayload(contact=contact, stage=STAGES[route], task=task))


def _coverage(ex, state, payers, reasons, missing):
    cites = [payers.cite]
    c = payers.rules["carriers"].get(ex.carrier)
    if ex.carrier in payers.rules.get("out_of_network", {}):
        reasons.append(payers.rules["out_of_network"][ex.carrier]["reason"])
        return "self_pay_offer", cites
    if c is None:
        what = "BCBS plans are state-specific and only BCBS IL is in network" if ex.carrier == "BCBS" \
            else f"{ex.carrier} is not in network"
        if ex.carrier == "BCBS" and state == "IL":
            c = payers.rules["carriers"]["BCBS IL"]
        else:
            reasons.append(what)
            return "self_pay_offer", cites
    if c["states"] != "all" and state not in c["states"]:
        reasons.append(f"{ex.carrier} is in network only in {', '.join(c['states'])}")
        return "self_pay_offer", cites
    if "covered_conditions" in c:
        if not set(ex.conditions) & set(c["covered_conditions"]):
            reasons.append(f"{ex.carrier} covers nutrition therapy only for {', '.join(c['covered_conditions'])}")
            return "self_pay_offer", cites
        if c.get("referral_required") and ex.has_referral is not True:
            missing.append("physician_referral")
            reasons.append(f"{ex.carrier} needs a physician referral")
            return "needs_info", cites
    reasons.append("in network and complete")
    return "book_now", cites
