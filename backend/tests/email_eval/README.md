# Email parser eval harness — Round-18 skeleton

A golden-file regression harness for the email-parsing pipeline.
Each fixture is a fully-formed scenario: raw input (mail body /
attachment) + expected parse result. The harness runs every
fixture through the pipeline and reports recall / precision
metrics.

## Why this exists

Pre-Round-18 we had unit tests proving each parser handles a
given input *type* (xlsx happy / HTML XSS / etc.), but no
end-to-end regression on real-shaped customer mails. A future
prompt edit or model bump can drop recall by 30% without
breaking a single unit test.

The harness's job is to surface that kind of silent regression
on every PR.

## Layout

```
email_eval/
  fixtures/
    01_plain_text_tr.json          ← input + expected
    02_html_table.json
    03_xlsx_rfq.json
    ...
  test_eval_corpus.py              ← runs the corpus, reports
                                     pass-rate, fails the build
                                     when below threshold.
```

## Fixture schema

Every JSON fixture follows this shape:

```json
{
  "name": "Short human label",
  "tags": ["plain_text", "tr"],
  "input": {
    "subject": "...",
    "body_text": "...",
    "body_html": null,
    "attachments_json": null,
    "thread_history": []
  },
  "expected": {
    "min_recall": 1.0,
    "min_precision": 1.0,
    "category": "spare_part_request",
    "parts": [
      { "part_code": "C7061A1012", "quantity": 5 }
    ]
  }
}
```

Recall = parsed_parts ∩ expected_parts / expected_parts
Precision = parsed_parts ∩ expected_parts / parsed_parts

Two parts are equal when their normalized ``part_code`` matches
(see ``part_catalog_resolver._normalize``). Quantity differences
flag as a soft mismatch.

## Running

```bash
# Local — uses the test PostgreSQL DB.
pytest tests/email_eval/test_eval_corpus.py -v

# CI — gated to fail if aggregate recall drops below 90%.
pytest tests/email_eval/test_eval_corpus.py --eval-floor=0.90
```

## Adding fixtures

1. Drop a JSON file in `fixtures/` named ``NN_short_label.json``.
2. Run the harness — if it fails because the pipeline doesn't
   produce the expected parts, decide: is the pipeline wrong, or
   is the expectation wrong? Iterate.
3. Once green, commit. The fixture becomes part of the regression
   baseline.

## Synthetic fixtures included

Round-18 seeds the corpus with 10 synthetic fixtures spanning the
common shapes. Real customer mails (anonymised) are intentionally
NOT committed to the repo — they belong in a private corpus repo
or KMS-encrypted blob.
