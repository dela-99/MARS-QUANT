# Research Lab
 
This directory is the **content** layer of the M.A.R.S. Research Lab.
 
Code that enforces methodology lives in `mars/research/`.  
Research artifacts (hypotheses, math notes, literature, experiments) live here.
 
## Layout
 
```
research/
├── hypotheses/        # One JSON (+ optional MD) per hypothesis
├── mathematics/       # Formal derivations, proofs, model specs
├── literature/        # Papers, notes, citations
├── experiments/       # Experiment designs and configs
├── notebooks/         # Exploratory notebooks (not production code)
├── datasets/          # Dataset manifests / pointers (not large binaries)
├── validation/        # Validation reports and statistical summaries
└── experiment_logs/   # Machine-written run logs (from ExperimentLog)
```
 
## Methodology
 
Every idea follows:
 
```
Idea
 → Hypothesis
 → Formal mathematics
 → Feature engineering
 → Historical testing
 → Walk-forward validation
 → Statistical tests
 → Risk review
 → Approval
 → Production candidate
```
 
## Hypothesis status
 
| Status    | Meaning                                      |
|-----------|----------------------------------------------|
| Draft     | Defined but not under active testing         |
| Testing   | Experiments in progress                      |
| Accepted  | Passed statistical + risk review             |
| Rejected  | Failed validation; keep for institutional memory |
| Archived  | Superseded or retired                        |
 
## Creating a hypothesis
 
```python
from mars.research import HypothesisStore
 
store = HypothesisStore()
store.new_template(
    hypothesis_id="HYP-A-001",
    title="Asia session predicts London direction",
    problem_statement="...",
    author="Your Name",
)
```
 
Do **not** invent trading rules here. Hypotheses are research questions.