SYNTHETIC — DEMO ONLY

---
application_id: CA-MISSING-DATA-2026-01
application_type: missing-data
expected_judgement: missing-data
expected_policy_ids:
  - CP-DOC-2026-01
customer_name: Nia Pell
customer_id: SYN-318704
email: nia.pell@example.invalid
phone: +1-555-0160
address: 4 Harbor Lane, Contoso Bay, CD 00033
age_band: 30-39
employer: self-employed (Pell Studio)
annual_income: USD 140,000
product: owner-occupied residential mortgage
facility:
  loan_amount: USD 280,000
  property_value: USD 400,000
  ltv: 70%
  dti: 32%
  credit_score: "740"
  occupancy: owner-occupied
narrative: Nia Pell is self-employed and missing 2 years tax returns required by CP-DOC-2026-01.
missing_items:
  - 2 years tax returns
---

# Client application CA-MISSING-DATA-2026-01

This file is a synthetic demo client application. It is not a real borrower record and is not a production credit decision.

## Applicant

- Name: Nia Pell
- Customer id: SYN-318704
- Address: 4 Harbor Lane, Contoso Bay, CD 00033
- Age band: 30-39
- Employer: self-employed (Pell Studio)
- Annual income: USD 140,000
- Email: nia.pell@example.invalid
- Phone: +1-555-0160

## Product

owner-occupied residential mortgage

## Facility

- loan_amount: USD 280,000
- property_value: USD 400,000
- ltv: 70%
- dti: 32%
- credit_score: 740
- occupancy: owner-occupied
- employment: self-employed

## Missing items

- 2 years tax returns

## Narrative

Nia Pell is self-employed and applies for an owner-occupied residential mortgage that is otherwise inside 80% LTV and 43% DTI. Credit Documentation Policy requires 2 years tax returns for self-employed applicants. Those returns are not in the file.
