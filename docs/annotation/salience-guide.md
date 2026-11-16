# Salience annotation guide

> **Draft for the authors to review.** The categories are the ones defined in the
> repository README. The decision procedure and the boundary cases below are a proposal
> written for this toolkit; they are not yet validated with annotators.

You label every element of a **reference** design, never a generated page. You read the
page's [task brief](brief-template.md) first: salience depends on what the learner must
do on that page, not on how the element looks.

## The three categories

| Category | Definition |
|---|---|
| **Essential** | Removing it prevents the learner from interpreting, performing, navigating or completing the activity. |
| **Supporting** | Removing it does not prevent completion, but reduces comprehension, orientation, feedback or context. |
| **Decorative** | Removing it only changes the visual presentation. |

## Decision procedure

Ask, in this order, imagining the element is gone and everything else stays:

1. **Could the learner still complete the activity described in the brief?**
   If not, the element is **Essential**. Stop.
2. **Would the learner understand less, lose their bearings, or get less feedback or
   context?** If yes, **Supporting**. Stop.
3. Otherwise, **Decorative**.

Judge each element on its own. Do not upgrade an element because it is large, colorful
or at the top of the page, and do not downgrade it because it is small.

## Boundary cases

| Element | Usually | Because | But |
|---|---|---|---|
| The control that completes the activity (submit, next, answer options of a question) | Essential | The completion criterion cannot be met without it | A second, redundant control for the same action is Supporting |
| The instruction that says what to do ("Choose one answer") | Essential when the action is not obvious without it; otherwise Supporting | Interpreting the activity is part of completing it | |
| The content the learner must read to answer or continue | Essential | | Examples and asides around it are Supporting |
| Page title | Supporting | Orientation | Essential if the brief asks the learner to find or identify that page |
| Progress indicator, breadcrumbs, course name | Supporting | Orientation | |
| Feedback after an action (correct, incorrect, saved) | Supporting | Feedback | Essential if the brief's completion criterion depends on seeing it |
| An image that carries information the text does not (a diagram, a chart, a labeled figure) | Essential or Supporting, by step 1 or 2 | It is content, not decoration | |
| An image that repeats or illustrates the text without adding to it | Decorative | | |
| Logo, background shapes, dividers, icons next to a labeled button | Decorative | | An icon-only control is a control: apply step 1 |
| Footer, legal text, unrelated links | Decorative or Supporting | Rarely affects the activity | |

## Practical rules

- Label **every** element in the sheet. A blank or unknown label makes the sheet invalid.
- Use the `note` column for any doubt. Notes are read during adjudication.
- Do not talk to the other annotators about specific elements before both sheets are in.
- An element without a strict majority goes to **adjudication**: a decision with a
  written reason, recorded in a file next to the sheets. Adjudication never overwrites
  an element that already has a majority.

## What the toolkit does with your labels

`edufidelity resolve-salience` resolves the sheets by strict majority, lists the
elements that need adjudication, and reports agreement between annotators
(Krippendorff's alpha, nominal and ordinal, with Decorative < Supporting < Essential).
Once every element is resolved, it writes the labeled reference. Its digest is fixed
before any generated page is measured.
