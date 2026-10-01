# Sample Bank Credit Policy

Demo policy for this local decision desk. It is not a live bank policy and it is not legal advice.

## §2 Data required to score a file

A file can be scored only when the business name, positive revenue, positive EBITDA, positive equity, current liabilities, a credit score from 300 to 850, and a non-negative existing debt service are present. Incomplete files stay in manual review. They are not declined on missing mathematics.

Pro forma debt is existing interest-bearing debt plus the proposed loan. Pro forma debt service is existing annual principal and interest plus the annual payment on the new facility.

## §4.2 Straight-through approval

A business loan may be approved without manual underwriting only when every condition below is true.

- Probability of default is below 5 percent.
- Pro forma Debt/EBITDA is below 3.0x.
- DSCR is above 1.25x. DSCR is EBITDA divided by pro forma annual debt service.
- Commercial credit score is at least 680.
- Current ratio is at least 1.20x.
- The business has operated for at least 3 years.
- There is no delinquency in the last 12 months.
- There is no bankruptcy flag.
- Prior loans with the bank, if any, are current.

Section 4.2 is the straight-through gate. Missing any item sends the file to review unless a hard stop in Risk Policy §3.1 already requires a decline.

## §4.3 Manual review

Manual review is the outcome when the file is complete enough to discuss but misses one or more straight-through conditions, and no hard stop has been hit. The credit officer records the reason, the policy section, and the decision.
