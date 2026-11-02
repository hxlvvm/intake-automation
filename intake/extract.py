"""Read the free-text insurance and reason fields into a typed Extracted record.

Two interchangeable extractors:
- KeywordExtractor (default): deterministic rules, no API key, used by the tests and CI.
- ClaudeExtractor (opt-in): Claude with structured output validated against the same Pydantic model. Set
  INTAKE_EXTRACTOR=claude and ANTHROPIC_API_KEY. Its output is post-checked against the policy carrier list, so the
  model can never invent a carrier the rules don't know.
"""
import os
import re

from .policy import current, load
from .schema import Extracted, IntakeForm

CONDITION_WORDS = {
    "prediabetes": ["prediabetes", "pre-diabetes", "prediabetic", "borderline diabetes"],
    "diabetes": ["diabetes", "diabetic", "type 2", "type 1", "t2d", "a1c"],
    "pcos": ["pcos", "polycystic"],
    "kidney_disease": ["kidney", "ckd", "renal"],
    "eating_disorder": ["eating disorder", "anorexia", "bulimia", "binge", "arfid", "purging", "restricting"],
    "weight_management": ["weight", "obesity", "glp-1", "wegovy", "zepbound"],
    "heart_health": ["cholesterol", "blood pressure", "hypertension", "heart"],
    "gi": ["ibs", "crohn", "celiac", "gerd", "colitis"],
}
SELF_PAY = ["self pay", "self-pay", "no insurance", "uninsured", "pay cash", "out of pocket"]
NO_REFERRAL = ["no referral", "don't have a referral", "do not have a referral", "without a referral"]
MEMBER_ID = re.compile(r"\b([A-Z]{0,4}\d{6,12}[A-Z0-9]{0,3})\b", re.I)
# Medicare Beneficiary Identifier: 11 characters, digit/letter positions fixed by CMS (no S, L, O, I, B, Z)
MBI = re.compile(r"\b([1-9][AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d[AC-HJKMNP-RT-Y][AC-HJKMNP-RT-Y0-9]\d"
                 r"[AC-HJKMNP-RT-Y]{2}\d{2})\b", re.I)


def _carrier_table(form):
    rules = current(load(), "payers", form.submitted_at.date()).rules
    table = [(alias, name) for name, c in rules["carriers"].items() for alias in c["aliases"]]
    table += [(alias, name) for name, aliases in rules["generic_aliases"].items() for alias in aliases]
    table += [(alias, name) for name, c in rules.get("out_of_network", {}).items() for alias in c["aliases"]]
    return sorted(table, key=lambda t: -len(t[0]))  # longest alias first: "bcbs of illinois" before "bcbs"


class KeywordExtractor:
    def extract(self, form: IntakeForm) -> Extracted:
        ins, why = form.insurance_text.lower(), form.reason_text.lower()
        carrier = next((name for alias, name in _carrier_table(form) if re.search(rf"\b{re.escape(alias)}\b", ins)), None)
        m = MBI.search(form.insurance_text) or MEMBER_ID.search(form.insurance_text)
        text = why
        conditions = []
        for cond, words in CONDITION_WORDS.items():   # prediabetes is checked first and removed, so it isn't read as diabetes
            if any(w in text for w in words):
                conditions.append(cond)
                for w in words:
                    text = text.replace(w, " ")
        if any(p in why for p in NO_REFERRAL):
            referral = False
        elif "referr" in why or "referred" in why:
            referral = True
        else:
            referral = None
        return Extracted(carrier=carrier, self_pay=any(p in ins for p in SELF_PAY) and carrier is None,
                         member_id=m.group(1) if m else None, conditions=conditions or ["other"], has_referral=referral)


class ClaudeExtractor:
    """Structured extraction with Claude. `client` is an anthropic.Anthropic (injected so tests can fake it)."""

    def __init__(self, client=None, model=None):
        if client is None:
            import anthropic  # optional dependency: pip install -r requirements-llm.txt
            client = anthropic.Anthropic()
        self.client = client
        self.model = model or os.environ.get("INTAKE_MODEL", "claude-opus-5-5")

    def extract(self, form: IntakeForm) -> Extracted:
        known = sorted({name for _, name in _carrier_table(form)})
        prompt = (
            "You read one patient intake form for a dietitian practice and fill in the record.\n"
            f"Use exactly one of these carrier names, or null if none fits: {', '.join(known)}.\n"
            "Use 'BCBS' when the patient names Blue Cross or Blue Shield without saying which state's plan.\n"
            "Only mark has_referral true or false when the text says so; otherwise null.\n\n"
            f"Insurance field: {form.insurance_text!r}\nReason field: {form.reason_text!r}"
        )
        resp = self.client.messages.parse(model=self.model, max_tokens=2000, output_format=Extracted,
                                          messages=[{"role": "user", "content": prompt}])
        if resp.stop_reason == "refusal" or resp.parsed_output is None:
            raise ExtractionError(f"model returned no record (stop_reason={resp.stop_reason})")
        out = resp.parsed_output
        if out.carrier is not None and out.carrier not in known:
            out = out.model_copy(update={"carrier": None})   # never trust a carrier the policy doesn't list
        return out


class ExtractionError(RuntimeError):
    """Raised when the model gives no usable record; the service routes the form to a person instead."""


def default_extractor():
    return ClaudeExtractor() if os.environ.get("INTAKE_EXTRACTOR") == "claude" else KeywordExtractor()
