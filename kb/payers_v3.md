---
id: payers
version: 3
effective_from: 2026-07-01
---
# In-network payers (version 3)

Synthetic practice policy for this demo. Check each payer's real rules before using anything like it.

- Aetna, Cigna and UnitedHealthcare: in network in every state.
- Humana: the contract ended on 30 June 2026. Offer self-pay.
- Blue Cross Blue Shield: only BCBS of Illinois. BCBS plans are state-specific, so "Blue Cross" without a state
  is not enough to tell.
- Medicare: covers medical nutrition therapy only for diabetes or kidney disease, and only with a physician
  referral.

```json
{
  "carriers": {
    "Aetna": {"aliases": ["aetna"], "states": "all"},
    "BCBS IL": {"aliases": ["bcbs il", "bcbsil", "bcbs of illinois", "blue cross blue shield of illinois", "blue cross illinois"], "states": ["IL"]},
    "Cigna": {"aliases": ["cigna"], "states": "all"},
    "UnitedHealthcare": {"aliases": ["unitedhealthcare", "united healthcare", "uhc", "united health"], "states": "all"},
    "Medicare": {"aliases": ["medicare"], "states": "all",
                 "covered_conditions": ["diabetes", "kidney_disease"], "referral_required": true}
  },
  "generic_aliases": {"BCBS": ["bcbs", "blue cross", "blue shield"]},
  "out_of_network": {"Humana": {"aliases": ["humana"], "reason": "the Humana contract ended on 30 June 2026"}}
}
```
