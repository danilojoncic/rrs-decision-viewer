# Case JSON files

Add one `.json` file per case here. Subfolders (for example `2026/event-name/`)
are supported. Use a unique, stable filename such as `event-name-decision-42.json`.
Editing the same file updates that case; removing it removes the case from the
next published build. Hidden folders such as `.drafts` are excluded.

Push or merge to the repository's default branch. The **Build and publish
decisions** workflow validates the JSON, rebuilds the viewer, and deploys the
updated website. Once the workflow succeeds, refresh the website to see the case.
No manual edits to the generated JavaScript or HTML are needed.

Use this structure (replace the example values with the actual decision):

```json
{
  "origin_system": "rrs.org",
  "request_type": "Protest",
  "event": "Example Event 2026",
  "race_number": "3",
  "hearing_datetime": "2026-10-08 15:00",
  "parties": ["Boat A", "Boat B"],
  "procedural_matters": [],
  "facts": ["First fact found."],
  "rules": ["RRS 10"],
  "conclusions": ["Conclusion from the hearing."],
  "decision": ["Decision from the hearing."]
}
```

`event` must be a non-empty string. Text fields must be strings; the seven
list fields must contain strings (empty lists are allowed for missing source
text). Jury fields are optional and excluded from the website's generated data.
Malformed JSON or invalid field types stop deployment, keeping the last
successful website online. Errors identify the affected file in the Actions log.

Local check: `python3 scripts/validate_cases.py`
