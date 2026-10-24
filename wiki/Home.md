# RecoveryLens Wiki

> **U.S. Disaster Recovery Funding & Equity Observatory**

RecoveryLens is an open-source decision-intelligence project for examining whether federal disaster-recovery resources align with disaster exposure, documented losses, population, and social vulnerability across U.S. counties.

[View the repository](https://github.com/Boatengs/recoverylens) · [[See current status|Current-Status]] · [[Follow the roadmap|Roadmap]] · [[Run the software|CLI-Reference]]

## Project snapshot

| Area | Current state |
|---|---|
| FEMA disaster declarations | Implemented for bounded, reproducible pulls |
| FEMA Public Assistance funding | Implemented with reconciliation, county-attribution coverage, obligation categories, timing diagnostics, and run-level quality reports |
| NOAA Storm Events downloads | Implemented with revision-aware selection, atomic downloads, checksums, and manifest verification |
| NOAA damage | Implemented with parse states and annual BLS CPI adjustment; nominal values and source warnings retained |
| NOAA injuries and fatalities | Implemented with event-level aggregation and person-record reconciliation |
| FEMA–NOAA linkage | Implemented as a county/date candidate assessment with ambiguity and nonmatches preserved; no candidates are treated as confirmed links |
| ACS and SVI context | 2022 same-vintage join live-validated across 3,144 national SVI counties |
| Analysis and modeling | Review-gated indicators and temporal evaluation implemented; national empirical validation pending |
| National county ranking | **Not released**; reviewed historical panel, consistent funding valuation, and joint validation remain incomplete |
| Public dashboard | Planned for Milestone 6 |

RecoveryLens is currently suitable for **method review and bounded data pulls**. It is not an operational emergency-management system or an official federal reporting product.

## Start here

- **Decision-makers and reviewers:** [[Current Status|Current-Status]] and [[Data Quality and Review|Data-Quality-and-Review]]
- **Analysts and developers:** [[Architecture]], [[CLI Reference|CLI-Reference]], and [[Reproducibility]]
- **Data stewards:** [[Data Sources|Data-Sources]] and the repository's [methodology](https://github.com/Boatengs/recoverylens/blob/main/docs/methodology.md)
- **Contributors:** [[Contributing]] and the repository's [contribution guide](https://github.com/Boatengs/recoverylens/blob/main/CONTRIBUTING.md)

## Documentation boundaries

The Wiki is the project guide: it explains the system, current readiness, workflows, and navigation. Version-controlled definitions that must change with the code remain canonical in the repository:

- [`docs/methodology.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/methodology.md) — analytical definitions and safeguards
- [`docs/data-quality.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/data-quality.md) — validation states and review guidance
- [`docs/data-sources.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/data-sources.md) — official source registry
- [`docs/roadmap.md`](https://github.com/Boatengs/recoverylens/blob/main/docs/roadmap.md) — roadmap tracked with the code

## Core analytical principles

1. Descriptive patterns are not causal proof.
2. Missing, invalid, unmatched, and conflicting records remain visible.
3. Composite scores never replace their components.
4. Official sources and reproducible transformations come first.
5. County-level patterns must not be interpreted as individual outcomes.

## Project links

- [Issues](https://github.com/Boatengs/recoverylens/issues)
- [Pull requests](https://github.com/Boatengs/recoverylens/pulls)
- [Actions](https://github.com/Boatengs/recoverylens/actions)
- [MIT License](https://github.com/Boatengs/recoverylens/blob/main/LICENSE)
- [Security policy](https://github.com/Boatengs/recoverylens/security/policy)
