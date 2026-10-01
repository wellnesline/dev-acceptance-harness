"""Isolated lexical validation example; not a filesystem containment guard."""
from __future__ import annotations

import re


def validate_artifact_path(value: str) -> str:
    if not isinstance(value, str) or not value or '\\' in value:
        raise ValueError('Expected a portable relative artifact name')
    forbidden = '<>:"|?*'
    for segment in value.split('/'):
        if (not segment or segment in ('.', '..') or segment[-1] in '. '
                or any(ord(c) < 32 or c in forbidden for c in segment)
                or re.fullmatch(r'(?i:con|prn|aux|nul|com[1-9]|lpt[1-9])', segment.split('.')[0])):
            raise ValueError('Unsafe artifact name')
    return value
