# Contributing

RecoveryLens welcomes improvements to data access, validation, methodology, documentation, tests, and the eventual public decision surface.

## Professional contribution workflow

1. Search existing [issues](https://github.com/Boatengs/recoverylens/issues) and [pull requests](https://github.com/Boatengs/recoverylens/pulls).
2. Open or claim an issue for a material change and define testable acceptance criteria.
3. Create one focused branch, such as `feat/event-declaration-matching` or `docs/reproducibility-guide`.
4. Implement the smallest coherent change with tests and documentation.
5. Run `ruff check .` and `pytest` locally.
6. Open a pull request that explains the rationale, evidence, limitations, and linked issue.
7. Address review and merge only after required checks pass.
8. Close the issue with completion evidence and any follow-up work.

Wiki changes follow this workflow too. Edit the reviewed source in [`wiki/`](https://github.com/Boatengs/recoverylens/tree/main/wiki); after merge, the `Publish Wiki` workflow copies managed pages into the Wiki's separate Git history.

## Definition of done

A change is complete when:

- acceptance criteria are satisfied;
- malformed, missing, duplicate, and boundary cases are tested where relevant;
- source URLs and retrieval assumptions are documented;
- methodological definitions change with the code that implements them;
- generated data, credentials, and caches remain uncommitted;
- automated checks pass; and
- uncertainty and unresolved limitations are stated plainly.

## Method changes

A pull request that changes a published metric or score must explain:

- the previous and proposed definitions;
- the policy or analytical rationale;
- expected directional effects;
- missing-data behavior;
- sensitivity or regression evidence; and
- corresponding documentation changes.

## Review priorities

1. Accuracy and traceability
2. Reproducibility
3. Honest treatment of uncertainty
4. Maintainability
5. Clear communication
6. Visual polish

See the canonical [`CONTRIBUTING.md`](https://github.com/Boatengs/recoverylens/blob/main/CONTRIBUTING.md) and [security policy](https://github.com/Boatengs/recoverylens/security/policy) before contributing.
