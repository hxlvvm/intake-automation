# intake-automation

New-patient intake automation for an insurance-billed telehealth dietitian practice. A website form arrives by
webhook and is routed in seconds to one of four outcomes:

| Route | When | What the CRM gets |
|---|---|---|
| `book_now` | in network, complete, nothing to review | contact in *Ready to book* |
| `needs_info` | a required detail is missing (or a referral or guardian consent is needed) | contact + a task naming exactly what to ask for |
| `clinical_review` | an eating disorder is mentioned | contact + a task for a dietitian to review before anyone books |
| `self_pay_offer` | out of network, a plan the practice can't take, or the patient chose self-pay | contact + a task to send pricing, with the reason |

All data here is synthetic, and the payer rules in `kb/` are made up for the demo.

## How it is split (build vs. engineer)

```
website form ──webhook──> [n8n]  Intake webhook
                                 │
                                 ├─ POST /decide ──────────> intake service (Python, typed, tested)
                                 │                            extract free text → apply policy → decision
                                 ├─ POST CRM /contacts/upsert
                                 ├─ if task: POST CRM /tasks
                                 └─ respond {route, contact_id}
```

- **In the no-code tool:** the wiring that changes often (webhook, CRM calls, branching) lives in n8n, where
  operations staff can see and change it.
- **In code:** the parts that must be right every time: reading free text, policy rules, effective dates. They are
  a small Python service with no side effects and 25 tests.

[`n8n/intake_workflow.json`](n8n/intake_workflow.json) is the workflow. [`intake/flow.py`](intake/flow.py) runs the
same steps in Python, so the whole path is tested in CI.

> **The n8n export is a hand-written reference and has not been executed.** I wrote it against the n8n 1.x node
> schemas (Webhook v2, HTTP Request v4.2, IF v2, Respond to Webhook v1.1) but have not imported it into a running
> n8n. To try it, run `npx n8n`, choose *Import from file*, start the two services below, and post a sample to
> `http://localhost:5678/webhook-test/intake`. Node parameter names can differ between n8n versions.

## Pieces

- **`intake/extract.py`**
  - `KeywordExtractor` (default) reads the insurance and reason fields with deterministic rules: carrier aliases
    from the policy file (longest first), member ids including the 11-character Medicare MBI, condition
    keywords (pre-diabetes is not read as diabetes), and referral mentions.
  - `ClaudeExtractor` (opt-in) does the same job with Claude structured outputs, validated against the same
    Pydantic model. A carrier the policy doesn't list is discarded, and a refusal or empty answer sends the form
    to a person. It needs `INTAKE_EXTRACTOR=claude` and `ANTHROPIC_API_KEY`. The tests cover it with a fake
    client only; it has not been run against the real API.
- **`kb/`**: the practice's policies as Markdown that people can read, with front matter (`id`, `version`,
  `effective_from`) and a JSON block the code reads. A decision uses the version in force on the submission date
  and cites it (`payers@v3`). This is what "making company knowledge AI-ready" means here: one current, dated
  source that both people and the code read.
- **`intake/rules.py`**: the routing order is part of the spec (safety review → consent → missing info →
  coverage). The CRM receives categories, never the patient's free text (minimum necessary).
- **`mock_crm/`**: a stand-in CRM that records every call. The endpoints are generic and not modelled on any
  vendor's API.

## Results on the 8 sample forms

| Form | Route | Why |
|---|---|---|
| S01 | book_now | Aetna, IL, complete (payers@v3) |
| S02 | needs_info | date_of_birth, member_id missing |
| S03 | clinical_review | eating disorder mentioned (clinical_review@v1) |
| S04 | self_pay_offer | Humana contract ended 30 Jun 2026 (payers@v3); the same form dated 15 Jun books (payers@v2) |
| S05 | needs_info | Medicare + diabetes, but no physician referral |
| S06 | self_pay_offer | "Blue Cross" in Texas: only BCBS IL is in network |
| S07 | needs_info | patient is 15: guardian consent |
| S08 | self_pay_offer | patient chose self-pay |

## Run it

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m pytest -q                        # 25 tests
.venv/bin/uvicorn intake.service:app --port 8000     # decision service
.venv/bin/uvicorn mock_crm.app:app --port 8001       # mock CRM; GET /_calls shows what was written
curl -s localhost:8000/decide -H 'content-type: application/json' \
     -d "$(python -c 'import json;print(json.dumps(json.load(open("samples/forms.json"))[0]))')"
```

For the Claude extractor: `pip install -r requirements-llm.txt`, then set `INTAKE_EXTRACTOR=claude`.
`INTAKE_MODEL` overrides the model; the default is `claude-opus-5-5`.

See [SPEC.md](SPEC.md) for the ticket this answers: requirements, edge cases, acceptance criteria and test plan.

MIT licence.
