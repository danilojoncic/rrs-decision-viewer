"""Validate published case inputs before replacing the live viewer (stdlib only)."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
TEXT_FIELDS = ('origin_system', 'request_type', 'event', 'race_number', 'hearing_datetime')
LIST_FIELDS = ('parties', 'procedural_matters', 'facts', 'rules', 'conclusions', 'decision')


def validate_case(path: Path) -> None:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict):
        raise ValueError('Each file must contain one case object, not an array')
    if not isinstance(data.get('event'), str) or not data['event'].strip():
        raise ValueError('event must be a non-empty string')
    for field in TEXT_FIELDS:
        if field in data and not isinstance(data[field], str):
            raise ValueError(f'{field} must be a string')
    for field in LIST_FIELDS:
        if field in data and (not isinstance(data[field], list) or
                             any(not isinstance(item, str) for item in data[field])):
            raise ValueError(f'{field} must be an array of strings')
    if 'jury' in data and not isinstance(data['jury'], dict):
        raise ValueError('jury, if present, must be an object')


def main() -> None:
    errors = []
    files = []
    for root in (ROOT / 'data/decisions', ROOT / 'data/imports'):
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
