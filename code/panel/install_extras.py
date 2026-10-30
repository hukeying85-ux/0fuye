"""One-shot, resumable optional software installer. No credentials or system edits."""
import hashlib, json, os, pathlib, shutil, subprocess, time, urllib.request, zipfile
ROOT = pathlib.Path('E:/0apps/ArenaDesk')
DSH = pathlib.Path('E:/0apps/DSH')
PET = pathlib.Path('E:/0apps/DSHPet')
STATE = ROOT / 'data' / 'install-state.json'
ENV = dict(os.environ)
ENV.update(DSH_HOME=str(DSH / 'data'), npm_config_cache=str(DSH / 'npm-cache'), npm_config_registry='https://registry.npmjs.org')
ENV['PATH'] = 'E:/hermes/node;' + ENV.get('PATH', '')
items = []
def save(name, status, detail, **extra):
    item = dict(name=name, status=status, detail=detail, at=time.strftime('%Y-%m-%d %H:%M:%S'), **extra)
    items.append(item)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(items, ensure_ascii=True, indent=2), encoding='utf-8'); tmp.replace(STATE)
def run(name, args, timeout=600):
    save(name, 'running', 'Installation in progress')
    log = ROOT / 'data' / (name + '.log')
    try:
        with log.open('w', encoding='utf-8') as out:
            r = subprocess.run(args, env=ENV, stdout=out, stderr=subprocess.STDOUT, timeout=timeout, creationflags=0x08000000)
        text = log.read_text(encoding='utf-8', errors='replace')
        save(name, 'installed' if r.returncode == 0 else 'failed', text[-1800:], code=r.returncode)
        return r.returncode == 0
    except Exception as e:
        save(name, 'failed', str(e)); return False

def main():
    DSH.mkdir(parents=True, exist_ok=True); PET.mkdir(parents=True, exist_ok=True)
    save('installer', 'running', 'DSH optional UI tools isolated from git-sync-hub; no AI credentials')
    npm = 'E:/hermes/node/npm.cmd'
    if run('dsh-host', [npm, 'install', '--prefix', str(DSH), '--no-audit', '--no-fund', '@deepseek-ai/dsh@0.2.1-rc.2']):
        cli = ['E:/hermes/node/node.exe', str(DSH/'node_modules/@deepseek-ai/dsh/lib/bin.js')]
        run('dsh-help', cli+['--help'], 30)
        run('dsh-plugin-help', cli+['plugin', '--help'], 30)
        run('dsh-video-skin', cli+['plugin', '--profile', 'web', 'add', 'dsh-video-skin@0.1.5'])
        run('dsh-whale-widget', cli+['plugin', '--profile', 'web', 'add', 'dsh-whale-widget@0.4.2'])
        save('dsh-boot-animation', 'deferred', 'video-skin already includes boot animation; avoid simultaneous fullscreen boot overlays')
        save('dsh-wallpaper-engine', 'deferred', 'npm package unpublished; source installer requires compatibility review and a local wallpaper library')
    # Publisher-provided SHA-256 from GitHub release metadata, checked before extraction.
    url = 'https://github.com/MerZlin/dsh-pet-indesktop/releases/download/v4.4.0/dsh-pet-standalone-webm-portable.zip'
    sha = 'fa049e31f1b0d184f77639a749f239b55b48c64b2ba14b59d08b3897168b55aa'
    archive = PET / 'pet-v4.4.0.zip'
    try:
        save('desktop-pet', 'downloading', 'v4.4.0 non-chat portable release, approximately 349 MB; SHA-256 verification required')
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=60) as src, archive.with_suffix('.part').open('wb') as dst:
                shutil.copyfileobj(src, dst)
            archive.with_suffix('.part').replace(archive)
        h=hashlib.sha256()
        with archive.open('rb') as f:
            for chunk in iter(lambda:f.read(1024*1024), b''): h.update(chunk)
        if h.hexdigest() != sha: raise ValueError('Release SHA256 mismatch; not extracting or executing')
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (PET/name).resolve().is_relative_to(PET.resolve()): raise ValueError('Unsafe archive path')
            z.extractall(PET)
        exes=list(PET.rglob('dsh-pet-standalone-webm.exe'))
        save('desktop-pet', 'installed' if exes else 'needs-check', 'Hash verified; non-chat version; launch separately', exe=str(exes[0]) if exes else '', sha256=sha)
    except Exception as e: save('desktop-pet', 'failed', str(e))
    save('installer', 'finished', 'See individual results; deferred is not installed')
if __name__=='__main__': main()
