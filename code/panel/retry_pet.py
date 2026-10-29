"""Resume a truncated GitHub release; size and published SHA are both required."""
import hashlib,json,os,pathlib,re,shutil,time,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
ROOT=pathlib.Path('E:/0apps/DSHPet'); STATE=pathlib.Path('E:/0apps/ArenaDesk/data/install-state.json')
URL='https://github.com/MerZlin/dsh-pet-indesktop/releases/download/v4.4.0/dsh-pet-standalone-webm-portable.zip'
SIZE=348968895; SHA='fa049e31f1b0d184f77639a749f239b55b48c64b2ba14b59d08b3897168b55aa'
def record(status,detail,**extra):
 rows=json.loads(STATE.read_text(encoding='utf-8'));rows.append(dict(name='desktop-pet',status=status,detail=detail,at=time.strftime('%Y-%m-%d %H:%M:%S'),**extra))
 tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(rows,ensure_ascii=True,indent=2),encoding='utf-8');tmp.replace(STATE)
def main():
 archive=ROOT/'pet-v4.4.0.zip'
 try:
  size=archive.stat().st_size if archive.exists() else 0
  if size>SIZE:raise ValueError('File larger than published size')
  parts=ROOT/'download-parts';parts.mkdir(exist_ok=True)
  def fetch(bounds):
   start,end=bounds; dest=parts/str(start); expected=end-start+1
   if dest.exists() and dest.stat().st_size==expected:return dest
   data=b''
   for attempt in range(10):
    offset=start+len(data)
    req=urllib.request.Request(URL,headers={'Range':'bytes=%d-%d'%(offset,end),'User-Agent':'ArenaDesk/1.0'})
    with urllib.request.urlopen(req,timeout=60) as src:
     m=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',src.headers.get('Content-Range',''))
     if src.status!=206 or not m or int(m[1])!=offset or int(m[3])!=SIZE:raise ValueError('Unexpected partial response')
     data+=src.read(expected-len(data))
    if len(data)==expected:dest.write_bytes(data);return dest
   raise ValueError('Partial chunk exhausted retries')
  chunks=[(start,min(start+2*1024*1024-1,SIZE-1)) for start in range(size,SIZE,2*1024*1024)]
  complete=size
  with ThreadPoolExecutor(max_workers=4) as pool:
   jobs={pool.submit(fetch,b):b for b in chunks}
   for job in as_completed(jobs):
    part=job.result();complete+=part.stat().st_size
    record('downloading','Verified ranges downloaded: %d / %d bytes'%(complete,SIZE))
  with archive.open('ab') as dst:
   for start,end in chunks:
    with (parts/str(start)).open('rb') as src:shutil.copyfileobj(src,dst)
  if archive.stat().st_size!=SIZE:raise ValueError('Incomplete release: %d / %d'%(archive.stat().st_size,SIZE))
  h=hashlib.sha256()
  with archive.open('rb') as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
  if h.hexdigest()!=SHA:raise ValueError('SHA256 still mismatched; refusing to run')
  with zipfile.ZipFile(archive) as z:
   for name in z.namelist():
    if not (ROOT/name).resolve().is_relative_to(ROOT.resolve()):raise ValueError('Unsafe archive path')
   z.extractall(ROOT)
  exes=list(ROOT.rglob('dsh-pet-standalone-webm.exe'))
  if not exes:raise ValueError('No expected executable')
  record('installed','Size and SHA-256 verified; non-chat portable version',exe=str(exes[0]),sha256=SHA)
 except Exception as e:record('failed',str(e))
if __name__=='__main__':main()
