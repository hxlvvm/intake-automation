# Ticket: route new intake forms automatically

**Problem (intake team):** "Every form waits in a shared inbox until someone reads it. Half need a follow-up
question, eating-disorder referrals sometimes get booked with the wrong dietitian, and nobody remembers which
payers we dropped this summer."

**Goal:** every form is routed within a minute of submission, with the reason written down, and nothing that
needs a clinician or a follow-up gets booked by mistake.

## Build vs. engineer

| Part | Where | Why |
|---|---|---|
| Webhook, CRM writes, branching, notifications | n8n workflow | changes often; operations owns it |
| Free-text reading, payer/clinical rules, policy versions | Python service (`/decide`) | must be right every time; needs tests |
| Payer and clinical policy | `kb/*.md`, versioned and dated | people edit it; the code reads it |

## Requirements

1. `POST /decide` takes the form as posted and returns a route, the missing fields, the reasons and the policy
   citations, plus the CRM payload. It has no side effects.
2. The routing order is fixed:
   1. Eating disorder mentioned → `clinical_review`, even if details are missing (the missing details go into
      the task).
   2. Under 18 → `needs_info: guardian_consent`.
   3. Missing contact (email or phone), date of birth, state, carrier, or member id → `needs_info`.
   4. Self-pay → `self_pay_offer`.
   5. Coverage under the payers policy in force on the submission date → `book_now`, `needs_info`
      (e.g. Medicare referral) or `self_pay_offer`.
3. Every decision that used a policy cites its id and version.
4. The CRM never receives the patient's free text: only categories, ids and the route.
5. If automatic reading fails (model refusal, no record), the form goes to `needs_info` for a person to handle. It
   is never dropped and never guessed.

## Edge cases

- **Policy changes:** a dropped payer (Humana, ended 30 Jun 2026). Forms dated before and after the change must
  route differently.
- **State-specific plans:** "Blue Cross" with no state. It is fine for an Illinois patient (BCBS IL), otherwise
  out of network.
- **Medicare:** covers medical nutrition therapy only for diabetes or kidney disease, with a referral. A missing
  referral → ask for it; a condition that isn't covered → self-pay offer.
- **Pre-diabetes** is not diabetes (it matters for Medicare).
- **Resubmission:** the same person submitting again updates the existing CRM contact.
- **Medicare member ids** (MBI) have letters and digits in fixed positions, so a generic "6+ digits" pattern
  misses them.

## Acceptance criteria

- [x] The 8 sample forms route as in the README table.
- [x] The same Humana form routes `book_now` on 15 Jun 2026 and `self_pay_offer` on 11 Aug 2026, citing v2 and v3.
- [x] An eating-disorder mention outranks missing information.
- [x] No free text in any CRM call (checked across all samples).
- [x] A resubmission with the missing details moves the same contact to *Ready to book*.
- [x] An extraction failure routes to `needs_info`.
- [ ] The n8n workflow, imported into a running n8n, gives the same CRM calls as `intake/flow.py`. **Not yet run.**

## Test plan

- `tests/test_rules.py`: each sample's route, missing fields and citations; policy versioning; ordering.
- `tests/test_extract.py`: keyword extractor edge cases; the Claude extractor against a fake client (schema
  passed, invented carrier dropped, refusal raises).
- `tests/test_flow.py`: all samples through the service into the mock CRM, plus resubmission and failure paths.
- Manual: import `n8n/intake_workflow.json`, replay `samples/forms.json`, and compare `GET /_calls` with the
  flow test.
