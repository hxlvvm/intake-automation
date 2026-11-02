"""HTTP service the automation tool (n8n, or any webhook tool) calls. It has no side effects: it returns a
decision and the CRM payload, and the workflow does the CRM writes. That keeps the typed, tested logic in code and
the wiring in the no-code tool, where operations staff can see and change it.

Run: uvicorn intake.service:app --port 8000
"""
from fastapi import FastAPI

from .extract import ExtractionError, default_extractor
from .rules import decide
from .schema import Decision, Extracted, IntakeForm

app = FastAPI(title="intake decision service")
extractor = default_extractor()


@app.get("/health")
def health():
    return {"ok": True, "extractor": type(extractor).__name__}


@app.post("/decide", response_model=Decision)
def decide_endpoint(form: IntakeForm) -> Decision:
    try:
        ex = extractor.extract(form)
    except ExtractionError:
        # No usable record from the model: hand the form to a person rather than guess.
        ex = Extracted(conditions=["other"])
        d = decide(form, ex)
        return d.model_copy(update={"route": "needs_info", "reasons": ["automatic reading failed: review by hand"]})
    return decide(form, ex)
