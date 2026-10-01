## Context
See proposal.md. This sample runs on Windows but its contract is portable.

## Goals / Non-Goals
Provide lexical validation only. Symlink resolution and real containment belong to the caller and are not demonstrated here.

## Decisions
Use explicit segment checks rather than the host OS path normalizer: normalization would erase invalid dot segments. Reject reserved Windows device names even on other platforms.

## Risks / Trade-offs
Lexical safety is not filesystem containment; document this limit and never import the sample into production.

## Migration Plan
Add a standalone sample module and unittest suite. Reverting the sample has no production effect.
