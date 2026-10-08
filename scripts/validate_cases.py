"""Validate published case inputs before replacing the live viewer (stdlib only)."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_FIELDS = ('origin_system', 'request_type', 'event', 'race_number', 'hearing_datetime')
LIST_FIELDS = ('parties', 'procedural_matters', 'facts', 'rules', 'conclusions', 'decision')
JURY_FIELDS = frozenset(('type', 'chair', 'members'))
ALLOWED_FIELDS = frozenset((*TEXT_FIELDS, *LIST_FIELDS, 'jury'))
MAX_FILE_BYTES = 1_000_000
MAX_TEXT_LENGTH = 1_000
MAX_LIST_ITEMS = 500
MAX_LIST_ITEM_LENGTH = 20_000


def validate_case(path: Path) -> None:
    if path.is_symlink():
        raise ValueError('symbolic links are not allowed')
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f'file exceeds the {MAX_FILE_BYTES:,}-byte limit')
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Each file must contain one case object, not an array')
    unexpected = sorted(set(data) - ALLOWED_FIELDS)
    if unexpected:
        raise ValueError(f'unexpected fields: {", ".join(unexpected)}')
    if not isinstance(data.get('event'), str) or not data['event'].strip():
        raise ValueError('event must be a non-empty string')
    for field in TEXT_FIELDS:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f'{field} must be a string')
        if len(data.get(field, '')) > MAX_TEXT_LENGTH:
            raise ValueError(f'{field} exceeds {MAX_TEXT_LENGTH:,} characters')
    for field in LIST_FIELDS:
        if field in data and (not isinstance(data[field], list) or
                             any(not isinstance(item, str) for item in data[field])):
            raise ValueError(f'{field} must be an array of strings')
        values = data.get(field, [])
        if len(values) > MAX_LIST_ITEMS:
            raise ValueError(f'{field} exceeds {MAX_LIST_ITEMS:,} entries')
        if any(len(item) > MAX_LIST_ITEM_LENGTH for item in values):
            raise ValueError(f'an item in {field} exceeds {MAX_LIST_ITEM_LENGTH:,} characters')
    jury = data.get('jury')
    if jury is not None:
        if not isinstance(jury, dict):
            raise ValueError('jury must be an object')
        unexpected_jury_fields = sorted(set(jury) - JURY_FIELDS)
        if unexpected_jury_fields:
            raise ValueError(f'unexpected jury fields: {", ".join(unexpected_jury_fields)}')
        for field in ('type', 'chair'):
            if field in jury and not isinstance(jury[field], str):
                raise ValueError(f'jury.{field} must be a string')
            if len(jury.get(field, '')) > MAX_TEXT_LENGTH:
                raise ValueError(f'jury.{field} exceeds {MAX_TEXT_LENGTH:,} characters')
        members = jury.get('members', [])
        if not isinstance(members, list) or any(not isinstance(item, str) for item in members):
            raise ValueError('jury.members must be an array of strings')
        if len(members) > MAX_LIST_ITEMS:
            raise ValueError(f'jury.members exceeds {MAX_LIST_ITEMS:,} entries')
        if any(len(item) > MAX_LIST_ITEM_LENGTH for item in members):
            raise ValueError(f'an item in jury.members exceeds {MAX_LIST_ITEM_LENGTH:,} characters')


def main() -> None:
    errors = []
    files = []
    root = ROOT / 'data/decisions'
    files.extend(path for path in root.rglob('*.json')
                 if not any(part.startswith('.') for part in path.relative_to(root).parts))
    for path in sorted(files):
        try:
            validate_case(path)
        except (ValueError, OSError) as error:
            errors.append(f'{path.relative_to(ROOT)}: {error}')
    if not files:
        errors.append('No case JSON files found')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        raise SystemExit(1)
    print(f'Validated {len(files)} case JSON files.')


if __name__ == '__main__':
    main()
