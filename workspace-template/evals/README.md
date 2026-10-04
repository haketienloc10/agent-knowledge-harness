# QiQi real-agent evals

Headless end-to-end evaluation harness for QiQi orchestration.

The runner starts a fresh QiQi parent through Herdr/native Codex or Claude, injects a natural-language user prompt, lets QiQi use the normal workspace MCP/qiqi_delegate path, then collects repository/runtime evidence and scores deterministic assertions.

## Prerequisites

The same prerequisites as interactive delegation apply:

- \`uv\`;
- \`herdr\`;
- the configured native agent CLI (\`codex\` for the default parent route);
- current Herdr integration for that adapter;
- valid native-agent authentication available to the local environment.

No ChatGPT/Codex/Claude UI interaction is required.

## Run

Single scenario:

\`\`\`bash
bash evals/run.sh --scenario evals/suites/graph-core/01-single-repo.yaml
\`\`\`

Whole suite, five fresh repetitions per scenario:

\`\`\`bash
bash evals/run.sh --suite graph-core --runs 5
\`\`\`

Validate scenario files without launching agents:

\`\`\`bash
bash evals/run.sh --suite graph-core --validate-only
\`\`\`

Failed workspaces can be retained for debugging:

\`\`\`bash
bash evals/run.sh \
  --suite graph-core \
  --keep-workspace-on-failure \
  --output-dir .eval-results/debug
\`\`\`

## Execution contract

Each repetition:

1. copies the workspace template into a fresh temporary workspace;
2. materializes fixture repositories as independent Git roots at pinned baseline commits;
3. rewrites \`repos.yaml\` to the fixture registry;
4. starts a fresh QiQi parent native session;
5. sends the scenario prompt programmatically;
6. waits for the authoritative native result hook;
7. runs deterministic verification commands;
8. collects Git and qiqi_delegate SQLite evidence;
9. writes \`result.json\` and \`summary.md\`;
10. destroys the temporary workspace unless retention was requested for a failure.

Graph runs are intentionally ephemeral. A qiqi_delegate/Herdr/runtime restart may fail the current eval repetition; the next repetition starts from a clean fixture instead of attempting workflow recovery.

## Scoring

Prefer deterministic assertions:

- required/forbidden repository changes;
- verification command exit status;
- TaskGraph presence/final state;
- wave and attempt budgets;
- retry floor for fault-injection scenarios.

The MVP does not require an LLM judge. Exact graph topology is not scored unless a future scenario explicitly needs it.

## CI

Unit/schema/fixture/scorer tests are safe for normal PR CI. Real-agent evals require local credentials, Herdr integration and native agent binaries, so the MVP does not make them a default PR gate. They can be wired to a credentialed/self-hosted \`workflow_dispatch\` runner later without changing the scenario or scoring contract.
