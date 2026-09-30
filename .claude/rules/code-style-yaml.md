---
paths:
  - "**/*.yaml"
  - "**/*.yml"
---

# YAML Rules

## `.github/**` — GitHub Actions workflow YAML

- Use double-quoted strings, for example `default: "main"`.
- Follow the GitHub Actions schema order for keys: `name`, `on`, `permissions`, `jobs`. Key order is not alphabetical.
- Give each workflow the smallest `permissions` block that it needs.
- Pin third-party actions to a major version tag, for example `actions/checkout@v4`.
- Add `if: always()` to a step that must run even when an earlier step in the job fails.
- Do not treat a string output that holds a boolean as truthy on its own. The string `'false'` is not empty, so it is truthy. Convert the output with `fromJSON(...)`, or compare it to the string `'true'`.
- Name a job ID or an output key in snake_case, for example `build_images`.

## Docker Compose and other YAML

- Indent with 2 spaces.
- In a Compose service block, put `image` or `build` first. Put it before `depends_on` and the other fields.
- Use one name for a given service or image in every workflow and Compose file. Use the underscore form of the project name, `rickroll_briefcase`.
- Add `:ro` to a Compose volume mapping when the container only reads from that volume.
- Do not mix snake_case and camelCase keys in one file.
- Do not use YAML anchors or aliases.
- End every YAML file with exactly one trailing newline.
