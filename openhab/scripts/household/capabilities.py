"""Descriptive registry projected from existing manifests, not control access."""
from dataclasses import dataclass
from hashlib import sha256
import re
from .codec import canonical, loads, identity

CONTRACT_FIELDS = {'requestBindings','protectedActuators','safetyInputs','legacyIngresses',
                   'manualAuthority','plannerAuthority','contractVersion','safetyInputsComplete'}


@dataclass(frozen=True)
class CapabilityRegistry:
    content: bytes

    @property
    def registry_id(self): return sha256(self.content).hexdigest()

    def to_dict(self): return {**loads(self.content), 'registry_id': self.registry_id}


def _names(values):
    if not isinstance(values, list) or len(values) > 64 or any(not isinstance(v, str) or not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,127}', v) for v in values) or len(values) != len(set(values)):
        raise ValueError('bounded unique explicit Item list required')
    return set(values)


def build_registry(managed, ownership):
    if not isinstance(managed, dict) or managed.get('schema') != 'earthship-openhab-managed-resources/v1' or not isinstance(managed.get('subsets'), dict) or not 1 <= len(managed['subsets']) <= 64:
        raise ValueError('original managed-resource manifest required')
    if not isinstance(ownership, dict) or ownership.get('version') != 1 or not isinstance(ownership.get('resources'), list) or len(ownership['resources']) > 2048:
        raise ValueError('original file ownership manifest required')
    resources = set()
    for resource in ownership['resources']:
        if not isinstance(resource, dict) or not isinstance(resource.get('kind'), str) or not isinstance(resource.get('id'), str):
            raise ValueError('explicit ownership resource required')
        key = resource['kind'], resource['id']
        if key in resources: raise ValueError('conflicting resource ownership refused')
        resources.add(key)
    capabilities, owners, ingress, actuators = {}, set(), set(), set()
    managed_items = set()
    for subset in managed['subsets'].values():
        contract = subset.get('householdContract')
        if not isinstance(contract, dict) or set(contract) != CONTRACT_FIELDS or contract['plannerAuthority'] != 'none' or contract['manualAuthority'] != 'request' or contract['contractVersion'] != 'legacy-correlated-v1' or contract['safetyInputsComplete'] is not False:
            raise ValueError('descriptive-only explicit owner contract required')
        rule = subset['rule']; owner = rule['uid']; capability = subset['capability']
        if not isinstance(owner,str) or not 1 <= len(owner) <= 128 or not isinstance(capability,str) or not 1 <= len(capability) <= 128 or owner in owners or capability in capabilities:
            raise ValueError('unique declared capability owner required')
        items = {item['name']:item['type'] for item in subset['items']}
        if len(items) != len(subset['items']) or set(items) & managed_items:
            raise ValueError('duplicate cross-owner Item declaration refused')
        if ('rule', owner) in resources or any(('item',name) in resources for name in items):
            raise ValueError('file and managed ownership overlap requires explicit migration')
        managed_items.update(items)
        dependencies = _names(subset['protectedDependencies'])
        protected, safety, legacy = [_names(contract[key]) for key in ('protectedActuators','safetyInputs','legacyIngresses')]
        if not protected or not protected <= dependencies or not safety <= dependencies or not legacy <= dependencies or protected & safety or protected & actuators:
            raise ValueError('explicit protected source dependency conflict')
        commands = {trigger['configuration']['itemName'] for trigger in rule['triggers'] if trigger['type']=='core.ItemCommandTrigger'}
        bindings = contract['requestBindings']
        if not isinstance(bindings,list) or not 1 <= len(bindings) <= 16: raise ValueError('bounded owner request bindings required')
        requests, results = set(), set()
        for binding in bindings:
            if not isinstance(binding,dict) or set(binding)!={'requestItem','resultItem'}: raise ValueError('closed request/result binding required')
            request, result = binding['requestItem'], binding['resultItem']
            _names([request,result])
            if items.get(request)!='String' or items.get(result)!='String' or request in requests or result in results or request in ingress or request in protected or result in protected:
                raise ValueError('existing separate correlated String ingress/result required')
            requests.add(request); results.add(result)
        if requests & results or requests | legacy != commands or requests & legacy or requests & actuators or results & actuators or protected & ingress:
            raise ValueError('declared ingress differs from original owner triggers')
        owners.add(owner); ingress.update(requests); actuators.update(protected)
        capabilities[capability] = dict(ownerRule=owner, ownerSource=rule['source'],
            availability='not_assessed', protectedDependencies=sorted(dependencies),
            **{key:(sorted(contract[key]) if key in ('protectedActuators','safetyInputs','legacyIngresses') else contract[key]) for key in CONTRACT_FIELDS})
    document=dict(schema='earthship-control-registry/v1', descriptiveOnly=True,
                  managed_manifest_sha256=identity(managed), ownership_manifest_sha256=identity(ownership),
                  capabilities=capabilities)
    return CapabilityRegistry(canonical(document))
