#!/usr/bin/env python3
"""Copy one stopped recording session off the hat and verify every file by SHA-256.

Usage: download_capture.py [SESSION]
  SESSION  e.g. 19166522959_20260907_122746 (default: newest session)
Env: HAT_PEER (default 192.168.77.2), HAT_STATE (state dir), HAT_OUT (default ./captures),
     HAT_PASSWORD (required; ./hat sets it from .hat/password)
Originals are never modified or deleted.
"""
import hashlib, json, os, shlex, subprocess, sys, time
from pathlib import Path

lib = Path(__file__).resolve().parent
root = lib.parent
state = Path(os.environ.get('HAT_STATE', root / '.hat'))
out_root = Path(os.environ.get('HAT_OUT', root / 'captures'))
peer = os.environ.get('HAT_PEER', '192.168.77.2')
password = os.environ.get('HAT_PASSWORD') or sys.exit('HAT_PASSWORD not set. Run: ./hat password')
session_arg = sys.argv[1] if len(sys.argv) > 1 else ''
state.mkdir(parents=True, exist_ok=True)

env = dict(os.environ, SSH_ASKPASS=str(lib / 'askpass.sh'), SSH_ASKPASS_REQUIRE='force', DISPLAY='hat')
ssh = ['/usr/bin/ssh', '-T', '-o', 'NumberOfPasswordPrompts=1', '-o', 'PreferredAuthentications=password',
       '-o', 'PubkeyAuthentication=no', '-o', 'ConnectTimeout=8', '-o', 'ServerAliveInterval=5',
       '-o', 'ServerAliveCountMax=3', '-o', 'StrictHostKeyChecking=accept-new', '-o', 'LogLevel=ERROR',
       '-o', f'UserKnownHostsFile={state}/known_hosts', f'cat@{peer}']

# Runs on the hat (as root): pick the session, refuse if still recording, hash every file.
manifest_code = r'''import os,glob,re,json,hashlib,subprocess,sys
want=sys.argv[1] if len(sys.argv)>1 else ''
if want:
    if not re.fullmatch(r'[0-9A-Za-z]+_\d{8}_\d{6}',want):raise SystemExit('Bad session name: '+want)
    session=want
    if not glob.glob('/data/'+session+'_*.mp4'):raise SystemExit('No recording named '+session+' in /data.')
else:
    paths=glob.glob('/data/*.mp4')
    if not paths:raise SystemExit('No MP4 recordings found in /data.')
    newest=max(paths,key=os.path.getmtime)
    m=re.fullmatch(r'(.+)_\d{5}\.mp4',os.path.basename(newest))
    if not m:raise SystemExit('Unrecognized recording filename: '+newest)
    session=m.group(1)
ps=subprocess.check_output(['ps','-eo','args']).decode(errors='replace')
if any('gst-launch' in line and '/data/'+session+'_' in line for line in ps.splitlines()):
    raise SystemExit('STILL_RECORDING: session '+session+' is still recording. Flip the hat switch to stop, wait a few seconds, then retry.')
files=sorted(glob.glob('/data/'+session+'_*.mp4'))
for suffix in ('.bin','.txt2'):
    p='/data/'+session+suffix
    if os.path.isfile(p):files.append(p)
out=[]
for p in files:
    if p.endswith('.mp4'):
        probe=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,codec_name,width,height,r_frame_rate','-of','json',p],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if probe.returncode:raise SystemExit('Recording is not finalized or is damaged: '+os.path.basename(p)+'; '+probe.stderr.decode(errors='replace'))
        info=json.loads(probe.stdout)
        local='segment_'+re.search(r'_(\d{5})\.mp4$',p).group(1)+'.mp4'
    else:info={};local='imu.bin' if p.endswith('.bin') else 'frame-timestamps.txt'
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    out.append(dict(remote=p,local=local,size=os.path.getsize(p),sha256=h.hexdigest(),media=info))
print(json.dumps(dict(session=session,files=out)))
'''


def remote(command, stdout, timeout):
    """Run `command` on the hat via sudo, retrying dropped USB/SSH links."""
    for attempt in range(1, 7):
        if attempt > 1 and hasattr(stdout, 'seek'):
            stdout.seek(0); stdout.truncate()
        result = subprocess.run(ssh + ["sudo -S -p '' " + command], input=(password + '\n').encode(), env=env,
                                stdout=stdout, stderr=subprocess.PIPE, timeout=timeout)
        errors = result.stderr.decode(errors='replace')
        if errors.strip():
            sys.stderr.write(errors)
        if result.returncode != 255 or 'Permission denied' in errors or 'IDENTIFICATION HAS CHANGED' in errors:
            return result
        if attempt < 6:
            print(f'SSH connection interrupted; retrying ({attempt}/6)...', flush=True)
            time.sleep(4)
    return result


def main():
    print('Finding and validating the recording...', flush=True)
    cmd = 'python3 -c ' + shlex.quote(manifest_code) + (' ' + shlex.quote(session_arg) if session_arg else '')
    result = remote(cmd, subprocess.PIPE, 180)
    if result.returncode:
        sys.exit('Could not prepare the recording (see message above).')
    manifest = json.loads(result.stdout)
    dest = out_root / manifest['session']
    if (dest / 'manifest.json').exists():
        sys.exit(f'Already downloaded: {dest}  (delete that folder to download again)')
    dest.mkdir(parents=True, exist_ok=True)
    total = sum(f['size'] for f in manifest['files'])
    print(f"Copying {len(manifest['files'])} files ({total/1024/1024:.1f} MiB) from session {manifest['session']}. Originals stay on the hat.", flush=True)
    for entry in manifest['files']:
        print('Copying ' + entry['local'], flush=True)
        tmp = dest / (entry['local'] + '.partial')
        with tmp.open('wb') as f:
            r = remote('cat -- ' + shlex.quote(entry['remote']), f, 1800)
        h = hashlib.sha256()
        with tmp.open('rb') as f:
            for block in iter(lambda: f.read(1024 * 1024), b''):
                h.update(block)
        if r.returncode or tmp.stat().st_size != entry['size'] or h.hexdigest() != entry['sha256']:
            sys.exit('Copy verification failed for ' + entry['local'] + '; partial file kept for diagnosis. Retry the download.')
        tmp.rename(dest / entry['local'])
        print('Verified ' + entry['local'], flush=True)
    # manifest.json is written last: its presence means the download is complete and verified.
    (dest / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('DOWNLOADED ' + str(dest), flush=True)


if __name__ == '__main__':
    main()
