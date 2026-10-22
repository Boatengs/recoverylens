# Security policy

## Supported versions

RecoveryLens is pre-release software. Security fixes are applied to the latest code on `main`.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose credentials, private information, or systems. Use GitHub's private vulnerability reporting feature when it is enabled for this repository.

Include a concise description, affected component, reproduction steps, potential impact, and any suggested mitigation. Do not include real secrets or sensitive personal data in a report.

## Data safety

RecoveryLens is designed for public, aggregate government data. The project should not ingest personally identifiable information, individual disaster-assistance records, credentials, or restricted datasets. Secrets must be supplied through environment variables and must never be committed.
