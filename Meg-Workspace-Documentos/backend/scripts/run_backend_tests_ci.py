"""Bound the PostgreSQL suite without an orphan keeping a tee pipe open."""
import os
import argparse
import signal
import subprocess
import sys
from pathlib import Path


def main():
    if os.getenv('GITHUB_ACTIONS') != 'true' or os.getenv('ENVIRONMENT') != 'staging':
        raise SystemExit('Dedicated CI staging required.')
    parser = argparse.ArgumentParser()
    parser.add_argument('--suite',choices=['all','core','api','procurement'],default='all')
    suite = parser.parse_args().suite
    paths = {'all':['tests'],'core':['tests/unit','tests/operations'],
             'api':['tests/integration'],'procurement':['tests/e2e','tests/procurement',
                 *sorted(str(path) for path in Path('tests').glob('test_*.py'))]}[suite]
    log = Path('backend-integration.log')
    print(f'Running PostgreSQL suite {suite}: {paths}',flush=True)
    with log.open('w') as output:
        process = subprocess.Popen([sys.executable,'-u','-m','pytest',*paths,'-vv','--maxfail=5',
            '--junitxml=backend-integration.xml','--durations=10','-o','faulthandler_timeout=30'],
            stdout=output,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            result = process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid,signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid,signal.SIGKILL)
                process.wait(timeout=5)
            result = 124
    # A regular file cannot keep this reader waiting on an orphan's pipe FD.
    # Preserve the complete file as an artifact and bound console output.
    print(log.read_text()[-200000:],flush=True)
    if result == 124:
        print('Backend suite exceeded five minutes; preserved diagnostic log.',flush=True)
    raise SystemExit(result)


if __name__ == '__main__':
    main()
