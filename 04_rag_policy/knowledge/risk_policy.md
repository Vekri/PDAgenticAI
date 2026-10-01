# Sample Bank Risk Policy

Demo risk policy for this local decision desk. The scorecard is a teaching model, not a validated regulatory capital model.

## §1 Risk grades

Grades are bands on the policy scorecard probability of default.

- Below 2 percent: Very Low
- Below 5 percent: Low
- Below 10 percent: Medium
- Below 15 percent: High
- 15 percent and above: Very High

The reference low-risk profile is a manufacturing borrower with a 720 credit score, pro forma Debt/EBITDA of 2.0x, DSCR of 1.62x, current ratio of 1.80x, 10 years in business, 5 percent revenue growth, no delinquency, and a stable industry outlook. That profile scores 3.8 percent PD, grade Low.

Industry outlook and industry type shift the score. They are business attributes, not personal attributes.

## §3.1 Decline criteria

Decline the file when any hard stop is true.

- Probability of default is 15 percent or higher.
- Pro forma Debt/EBITDA is above 4.0x.
- DSCR is below 1.10x.
- Commercial credit score is below 620.
- Current ratio is below 0.80x.
- The business has operated for less than 2 years.
- Three or more delinquencies occurred in the last 12 months.
- A bankruptcy flag is present.

A hard stop overrides straight-through approval. The audit trail must name the failed section. Overrides, if a credit officer later approves, are outside this desk and must be written by that officer.
