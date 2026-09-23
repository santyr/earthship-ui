#!/usr/bin/env python3
"""Render the current simple JDBC strategy DTO; never deploy or mutate REST.

Unsupported configuration is refused, not silently discarded. This intentionally
does not export JDBC connection settings, which contain credentials.
"""
import re


def render(dto, *, allow_file=False):
    keys = {'serviceId', 'configs', 'aliases', 'cronStrategies', 'thresholdFilters',
            'timeFilters', 'equalsFilters', 'includeFilters', 'editable'}
    if (set(dto) != keys or dto['serviceId'] != 'jdbc' or
            dto['editable'] is not True and not (allow_file and dto['editable'] is False)):
        raise ValueError('expected complete JDBC strategy DTO from the selected provider')
    if dto['aliases'] != {} or any(dto[k] != [] for k in keys -
                                  {'serviceId', 'configs', 'aliases', 'editable'}):
        raise ValueError('aliases, custom strategies and filters require explicit support')
    if not isinstance(dto['configs'], list) or not dto['configs']:
        raise ValueError('nonempty configuration list required')
    lines = ['// Canonical JDBC strategy; exactly one provider must own this service.',
             '// Preserve change-only collection and explicit immutable power writes.',
             'Strategies {', '}', '', 'Items {']
    for config in dto['configs']:
        if set(config) != {'items', 'strategies', 'filters'} or config['filters'] != []:
            raise ValueError('unsupported configuration fields or filters')
        items, strategies = config['items'], config['strategies']
        if (not isinstance(items, list) or not items or
                not all(isinstance(x, str) and re.fullmatch(r'\*|!?[A-Za-z_][A-Za-z_0-9]*\*?', x)
                        for x in items)):
            raise ValueError('invalid Item selector')
        if (not isinstance(strategies, list) or not strategies or
                not all(isinstance(x, str) and x in
                        {'everyChange', 'everyUpdate', 'restoreOnStartup', 'forecast'}
                        for x in strategies)):
            raise ValueError('unsupported strategy')
        lines.append('    ' + ', '.join(items) + ' : strategy = ' + ', '.join(strategies))
    return '\n'.join(lines + ['}', ''])


if __name__ == '__main__':
    from openhab_sanity_check import get
    print(render(get('/persistence/jdbc'), allow_file=True), end='')
