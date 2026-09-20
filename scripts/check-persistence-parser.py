#!/usr/bin/env python3
"""Check the prepared JDBC file using installed parser jars, without live writes."""
from pathlib import Path
import subprocess

root = Path(__file__).resolve().parents[1]
jars = sorted(str(p) for p in Path('/usr/share/openhab/runtime/system').rglob('*.jar'))
parser_jars = [p for p in jars if Path(p).name.startswith('org.openhab.core.model.persistence-')]
if len(parser_jars) != 1 or Path(parser_jars[0]).name != 'org.openhab.core.model.persistence-5.2.1.jar':
    raise SystemExit('review parser version before qualification')
result = subprocess.run(['java', '-Xmx256m', '--class-path', ':'.join(jars),
                         str(root / 'scripts/HexPersistenceParse.java'),
                         str(root / 'openhab/file-config/persistence/jdbc.persist')],
                        capture_output=True, text=True, timeout=45)
expected = [
    'strategy_tokens=[everyChange, restoreOnStartup]',
    'selector_type=AllConfig', 'selector_type=ItemExcludeConfig',
    'strategy_tokens=[forecast, everyChange]', 'selector_type=GroupConfig',
    'strategy_tokens=[restoreOnStartup]', 'selector_type=ItemConfig', 'syntax_errors=0']
actual = [line for line in result.stdout.splitlines()
          if line.startswith(('strategy_tokens=', 'selector_type=', 'syntax_errors='))]
if result.returncode or actual != expected:
    raise SystemExit('offline parser qualification failed; inspect parser/dependencies')
print('OpenHAB 5.2.1 offline syntax, selector types and strategy tokens match')
print('Runtime strategy resolution and provider transfer remain unverified')
