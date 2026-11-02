# Pre-registration: lock the plan before the money moves

**Status:** v1 draft for review.

> **In plain English:** Before the campaign starts, everyone agrees in writing on which markets get which ads, what we'll measure, when, and how. FOSIT turns that agreement into a file plus a short fingerprint (a "hash"). Send the fingerprint to the advertiser and every vendor **before launch**. When results come in, FOSIT checks that the plan wasn't touched. If anyone moved a market or a date, it shows.

## Why this matters

With enough freedom after the fact (dropping a "weird" market, shifting the end date by a week, switching from orders to revenue), almost any test can be made to say almost anything. Pre-registration removes that freedom from **everyone**: the advertiser, both vendors, and us.

## What is locked

Everything in the plan's `commitment` block ([SCHEMA.md §6](SCHEMA.md#6-locked-plan-fosit-planjson)):

- Geo unit and mapping file fingerprint
- Every cell's label, geo list, and budget. The control list. The excluded list.
- Primary and secondary KPI, daily vs. weekly
- Pre-period, test, and cooldown dates
- Method and every parameter (α, test statistic, λ rule, head-to-head method, seed)
- Thresholds for every honesty check
- The decision rule (primary metric, target iCPA or break-even iROAS)
- Vendor targetability confirmations
- A fingerprint of the historical data the plan was built from

**Not locked:** the `appendix` (fit, balance, MDE, power curves, share of national sales). It's informative but doesn't change how results are computed. You can remove it before sending the plan to vendors if you'd rather not share sales shares. The hash stays the same.

## How the hash is computed

1. Take the `commitment` object.
2. Serialize it with the **JSON Canonicalization Scheme, RFC 8785** (sorted keys, no whitespace, standardized number formatting). Geo lists are already sorted by schema rule, so the same plan always gives the same bytes.
3. SHA-256 over the UTF-8 bytes, written as 64 lowercase hex characters.

This runs in your browser using the built-in Web Crypto API. You can reproduce it without FOSIT:

```bash
# Python 3, standard library only. json.dumps with these options matches RFC 8785
# for FOSIT plans: keys are ASCII, and the schema keeps every number an integer or
# a decimal between 0.0001 and 1e15, where Python and RFC 8785 number formatting
# agree. tests/test_hash.py checks this against a full RFC 8785 implementation.
python3 -c "import json,hashlib,sys; c=json.load(open(sys.argv[1]))['commitment']; \
print(hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())" plan.fosit-plan.json
```

## The ritual (what we ask users to do)

1. **Lock** the plan in FOSIT. You get `plan.fosit-plan.json`, `plan.pdf`, and the hash (shown as 64 characters plus a short 8-character version for humans).
2. **Send** the PDF and JSON, with the full hash in the email body, to the advertiser's decision-maker and every vendor **before `test_start`**. The email timestamps are your witness. FOSIT has no server and can't be your witness, and that's by design.
3. **Launch.** Vendors target exactly their cell's geo list.
4. **Read.** Load the plan JSON into FOSIT and paste the hash from the original email. FOSIT checks:
   - **Self-consistency:** the hash recomputed from the loaded plan equals the `hash.value` stored inside it.
   - **Anchor:** that hash equals the one you pasted from the pre-launch email. *This is the check that matters*, because anyone can edit a plan and recompute its internal hash.
   - **Usage:** every analysis input (geos, dates, KPI, method) is read from the plan, not from UI settings.
5. If you load the original plan as well as a changed one, FOSIT shows a **field-by-field diff** (e.g. "`cells[1].geo_ids`: removed `19100`").

A mismatch doesn't stop the analysis, because sometimes plans really do have to change mid-flight. But the report is watermarked **"NOT THE PRE-REGISTERED ANALYSIS"** on every page, and the diff is printed in full.

## Changing a plan honestly

If something forces a change before launch (a vendor can't target a market), create a new version of the plan, lock it, and re-send it. The new plan records nothing about the old one automatically, so mention the old hash in your email. After launch, don't change the plan. Run the pre-registered analysis, then optionally run an *exploratory* analysis, which is always labelled as such.

## Optional: public timestamp

For high-stakes tests, you can also post the hash (not the plan) somewhere public with a timestamp, e.g. a GitHub gist or a commit in your own repo. A hash reveals nothing about the plan's contents.
