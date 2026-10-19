"""The retained ML workflow runs one pytest command with real surviving paths."""
from pathlib import Path
import subprocess


def test_retired_paths_do_not_break_the_pytest_shell_continuation(tmp_path):
    root=Path(__file__).resolve().parents[1]
    lines=(root/'.github/workflows/forecast-ml-hardening.yml').read_text().splitlines()
    step=lines.index('      - name: Forecast and thermal ML regression suite')
    start=lines.index('        run: |',step)+1
    script=[]
    for line in lines[start:]:
        if line and not line.startswith('          '):break
        script.append(line[10:] if line else '')
    # Run the actual shell block in an empty directory. This Python stand-in
    # records arguments; it never imports models or contacts household services.
    result=subprocess.run(['/bin/bash','-e','-c',
        'python() { printf "PYTHON_CALL\\n"; printf "%s\\n" "$@"; }\n'+'\n'.join(script)+'\n'],
        cwd=tmp_path,capture_output=True,text=True,timeout=5)
    assert result.returncode==0,result.stderr
    args=result.stdout.splitlines()
    assert args.count('PYTHON_CALL')==1
    assert args[:4]==['PYTHON_CALL','-m','pytest','-q']
    assert len(args)>4
    assert all((root/name).is_file() for name in args[4:]),args[4:]
