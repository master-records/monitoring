# Ecosystem Transition Ledger Monitoring Mirror Handoff

`master-records/monitoring` is a read-only projection of the ecosystem transition organization records kept by `master-records/orchestration`. The ledger role belongs to the organization transition ledger; Master Records keeps the organization records.

Projection tool: `tools/project_ecosystem_transition_ledger.py`

The projection may expose counts, organization distribution, and the current organization-record head. It does not mutate organization records, reconstruct source consequences by re-execution, or create authority.

Canonical flow:

`repo ledger -> org .github ledger -> master-records/.github ingress -> master-records/orchestration organization records -> master-records/monitoring projection`

Observers, including `StegVerse-Labs/.github`, consume this projection rather than bypassing Master Records to observe causal participants directly.
