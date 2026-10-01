# Proposal

## Why

An isolated development sample needs portable validation for artifact paths before filesystem work. Demonstrate a real spec-to-test-to-implementation workflow without modifying production.

## What Changes

- Add a pure Python validator for forward-slash relative artifact paths.
- Reject traversal, absolute paths, empty segments, Windows drive syntax and reserved names.

## Capabilities

### New Capabilities
- `artifact-path`: Validate portable relative artifact names without filesystem writes.

### Modified Capabilities
None.

## Impact

Only `dev_harness/project/artifact_path.py` and its tests. No production import, network, paid API or file write.
