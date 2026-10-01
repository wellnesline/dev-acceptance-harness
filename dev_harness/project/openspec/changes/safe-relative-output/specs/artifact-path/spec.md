## Purpose

Permit portable relative artifact names while rejecting ambiguous and escaping names before any filesystem operation occurs.

## ADDED Requirements

### Requirement: Preserve valid relative paths
The validator SHALL return nonempty forward-slash relative paths unchanged, including Unicode names and spaces within names.

#### Scenario: Unicode output name
- **WHEN** `reports/日本語 summary.json` is submitted
- **THEN** the same string is returned

### Requirement: Reject unsafe portable names
The validator SHALL reject nonstrings, absolute names, drive or backslash syntax, empty segments, dot segments, control characters, Windows reserved names, forbidden characters and trailing spaces or dots with ValueError. It MUST NOT access the filesystem.

#### Scenario: Traversal
- **WHEN** `reports/../secret.txt` is submitted
- **THEN** ValueError is raised

#### Scenario: Windows reserved name
- **WHEN** `reports/CON.txt` is submitted
- **THEN** ValueError is raised
