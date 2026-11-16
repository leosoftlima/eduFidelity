# Task brief template

> **Draft for the authors to review.** One brief per reference page, written **before**
> any generated page exists and before salience annotation. Annotators read it; raters
> read it too, so that both judge the page against the same activity.

A brief is short and concrete. It describes the learner's activity on the page, not the
page's design.

| Field | What to write | Example (fictitious course) |
|---|---|---|
| `interface_id` | The reference page id | `quiz` |
| `function` | The role of the page in the course | assessment |
| `objective` | What the learner should achieve | Show they know how to fix a sour, wet compost pile |
| `expected_action` | What the learner does on the page | Choose one of three answers and submit it |
| `completion_criterion` | How one knows the activity is complete | An answer was submitted |

As JSON, the format read by `edufidelity annotation-sheets --brief`:

```json
{
  "interface_id": "quiz",
  "function": "assessment",
  "objective": "Show they know how to fix a sour, wet compost pile",
  "expected_action": "Choose one of three answers and submit it",
  "completion_criterion": "An answer was submitted"
}
```

## Rules

- **No reference to how the page looks.** "The green button" is design; "submit the
  answer" is the activity.
- **One activity per page.** If a page has two, write both in `expected_action` and say
  which one completes the page.
- **Frozen once annotation starts.** A brief changed after annotation invalidates the
  labels of that page.
