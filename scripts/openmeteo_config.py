"""Compare OpenMeteo Thing settings using the installed binding's parameter types."""
from decimal import Decimal, InvalidOperation


def _value(value, kind):
    if kind in {'INTEGER', 'DECIMAL'} and value is not None:
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return value
    if kind == 'BOOLEAN' and value is not None:
        return str(value).lower()
    return value


def mismatch_keys(current, original, metadata):
    """Ignore old unsupported keys, but compare every current typed parameter."""
    before = original.get('configuration', {})
    after = current.get('configuration', {})
    return [parameter['name'] for parameter in metadata['configParameters']
            if _value(before.get(parameter['name'], parameter.get('default')),
                      parameter['type'])
            != _value(after.get(parameter['name'], parameter.get('default')),
                      parameter['type'])]
