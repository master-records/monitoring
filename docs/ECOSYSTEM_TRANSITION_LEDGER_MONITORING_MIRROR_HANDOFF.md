# Ecosystem Transition Ledger Monitoring Mirror Handoff

`master-records/monitoring` is a read-only projection of the canonical ecosystem transition custody ledger owned by `master-records/orchestration`.

Projection tool: `tools/project_ecosystem_transition_ledger.py`

The projection may expose counts, organization distribution, and the current custody head. It does not mutate custody, reconstruct source consequences by re-execution, or create authority.

Canonical flow:

`repo ledger -> org .github ledger -> master-records/.github ingress -> master-records/orchestration custody -> master-records/monitoring projection`

Observers, including `StegVerse-Labs/.github`, consume this projection rather than bypassing Master Records to observe causal participants directly.
