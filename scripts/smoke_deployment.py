"""Exercise the actual production HTTP process, restart and restored backup offline.

Run after pnpm build. Uses an isolated database and makes no model requests.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
import urllib.error
from pathlib import Path
from socket import socket


def run(public_demo=False):
    root=Path(__file__).resolve().parent.parent
    if not (root/'dist/index.html').is_file():
        raise SystemExit('Run pnpm build first.')
    with socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port=reservation.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    with tempfile.TemporaryDirectory() as directory:
        work=Path(directory)
        env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'WEB_CONCURRENCY':'1',
             'EDITORIAL_DB_PATH':str(work/'live.sqlite3'),
             'FOUNDRY_BASE_URL':'','FOUNDRY_API_KEY':'','FOUNDRY_MODEL':'',
             'PUBLIC_DEMO_MODE':'1' if public_demo else '0'}
        # Use the real runtime directly on Windows so terminating the subprocess
        # cannot leave a venv redirector's server child running after the test.
        site=Path(sys.prefix)/('Lib/site-packages' if os.name=='nt' else f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')
        env['PYTHONPATH']=os.pathsep.join([str(root),str(site),env.get('PYTHONPATH','')])
        executable=getattr(sys,'_base_executable',sys.executable)
        flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
        process=None
        log=(work/'server.log').open('w',encoding='utf-8')

        def request(path,body=None):
            data=json.dumps(body).encode() if body is not None else None
            req=urllib.request.Request(url+path,data=data,headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=15) as response:
                return response.read(),response.headers

        def start():
            nonlocal process
            process=subprocess.Popen([executable,'-m','backend.serve'],cwd=root,env=env,
                stdout=log,stderr=log,creationflags=flags)
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                if process.poll() is not None:
                    raise RuntimeError('Production process exited unexpectedly.')
                try:
                    payload,_=request('/health/ready')
                    if json.loads(payload)['status']=='ready':
                        return
                except OSError:
                    time.sleep(.1)
            raise RuntimeError('Production process did not become ready.')

        def stop():
            nonlocal process
            if process is not None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                process=None

        try:
            start()
            page,_=request('/')
            asset=re.search(rb'src="([^"]+\.js)"',page).group(1).decode()
            assert request(asset)[0]
            assert json.loads(request('/health/ready')[0])['foundry_configured'] is False
            if public_demo:
                assert json.loads(request('/api/health')[0])['public_demo'] is True
                for path in ['/api/ops','/docs','/redoc','/openapi.json','/api/foundry/probe']:
                    try:
                        request(path,{} if path.endswith('probe') else None)
                        raise AssertionError('Private route was exposed: '+path)
                    except urllib.error.HTTPError as exc:
                        assert exc.code==404
            session='production-restart-smoke'
            clock=4440000
            result=json.loads(request('/api/editorial/generate',{
                'session_id':session,'match_clock_ms':clock,'mode':'player','entity_id':'r-12'})[0])
            draft=result['draft']
            assert draft['source']=='calculated'
            action=dict(session_id=session,match_clock_ms=clock,draft_id=draft['draft_id'],
                title='A useful contribution',body=draft['casual_text'],action='save')
            assert json.loads(request('/api/editorial/action',action)[0])['published'] is None
            stop()
            start()
            state=json.loads(request(f'/api/editorial/state?session_id={session}&match_clock_ms={clock}')[0])
            assert state['drafts'][-1]['title']==action['title']
            action['action']='approve'
            assert json.loads(request('/api/editorial/action',action)[0])['published']['show_headline']
            stop()
            start()
            state=json.loads(request(f'/api/editorial/state?session_id={session}&match_clock_ms={clock}')[0])
            assert state['published']['title']==action['title']
            audit=json.loads(request(f'/api/editorial/audit?session_id={session}')[0])
            assert len(audit['events'])==3
            if not public_demo:
                assert json.loads(request('/api/ops')[0])['requests']
            backup=work/'backup.sqlite3'
            subprocess.run([executable,'-m','scripts.backup_editorial',str(backup)],cwd=root,env=env,
                check=True,timeout=20,stdout=log,stderr=log,creationflags=flags)
            stop()
            env['EDITORIAL_DB_PATH']=str(backup)
            start()
            restored=json.loads(request(f'/api/editorial/state?session_id={session}&match_clock_ms={clock}')[0])
            assert restored['published']['title']==action['title']
            assert len(json.loads(request(f'/api/editorial/audit?session_id={session}')[0])['events'])==3
            print('PASS: built UI/assets, readiness, saved edit restart, approved publication restart, audit, '+
                ('private routes hidden, ' if public_demo else 'metrics, ')+'and backup restore. No model calls.')
        finally:
            stop()
            log.close()


if __name__=='__main__':
    run(public_demo='--public' in sys.argv)
