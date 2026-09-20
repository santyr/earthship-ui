"""Remove only calls to retired child rules; preserve all remaining semantics."""
from copy import deepcopy

RETIRED = {'ab8a59e1da', '4e234eabea', 'e647476610'}
SCHEDULES = {'1f692c798b': {'ab8a59e1da', '4e234eabea'},
             'b1501047a9': {'e647476610'}}


def repair(rule):
    if rule.get('uid') not in SCHEDULES or rule.get('editable') is not True:
        raise ValueError('expected a managed legacy schedule')
    result = deepcopy(rule)
    actions = []
    for action in result['actions']:
        if action.get('type') != 'core.RunRuleAction':
            actions.append(action)
            continue
        config = action['configuration']
        if set(config) != {'considerConditions', 'ruleUIDs'} or not isinstance(config['ruleUIDs'], list):
            raise ValueError('unsupported run-rule action')
        targets = config['ruleUIDs']
        if any(not isinstance(x, str) for x in targets):
            raise ValueError('invalid rule target')
        if (set(targets) & RETIRED) - SCHEDULES[rule['uid']]:
            raise ValueError('unexpected retired target')
        config['ruleUIDs'] = [x for x in targets if x not in RETIRED]
        if config['ruleUIDs']:
            actions.append(action)
        elif action.get('inputs') or any(action['id'] + '.' in str(x.get('inputs', {})) for x in result['actions']):
            raise ValueError('cannot remove a wired module')
    result['actions'] = actions
    return result
