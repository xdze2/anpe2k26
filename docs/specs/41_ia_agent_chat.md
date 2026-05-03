---
status: draft
---

### Agent behaviour

- The agent MUST ask the user before running expensive or quota-consuming enrichment
  steps (Tavily).
- The agent MUST flag `unclear` eval results to the user rather than guessing.
- The agent MUST update company status immediately when the user reacts mid-browse
  (e.g. "DataVin looks interesting") — not deferred to end of session.
- The eval model and the chat agent MUST share no context. Eval steps are run
  separately and their outputs are stored to disk; the agent reads the output files.
