---
paths:
  - "**/*.json"
---

# JSON Rules

Most JSON files in this repository are configuration files. Prettier controls their layout. The rules below cover content that a person chooses.

- Use snake_case for keys in hand-written JSON, for example `config/settings.json`. This matches the Python field names.
- Add new words to `cspell.json` in alphabetical order, in lower case. cspell matching ignores case, so a mixed-case entry adds nothing.
- End every JSON file with exactly one trailing newline.
