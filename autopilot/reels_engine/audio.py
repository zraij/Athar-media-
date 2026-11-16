"""python3 audio.py out.wav dur drop_t full_from 'sfx json'  -> music bed + sfx, generated (no external assets)"""
import sys, json, numpy as np, wave
SR=48000
out,dur,drop,full=sys.argv[1],float(sys.argv[2]),float(sys.argv[3]),float(sys.argv[4]); cues=json.loads(sys.argv[5])
N=int(dur*SR); t=np.arange(N)/SR
rng=np.random.default_rng(7)
mus=np.zeros(N); sfx=np.zeros(N)
def add(buf,start,sig,g=1.0):
    i=int(start*SR)
    if i>=N: return
    if i<0: sig=sig[-i:]; i=0
    n=min(len(sig),N-i); buf[i:i+n]+=sig[:n]*g
def kick():
    n=int(.35*SR); tt=np.arange(n)/SR; f=50+90*np.exp(-tt*30); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*np.exp(-tt*9)
def hat():
    n=int(.06*SR); tt=np.arange(n)/SR; x=rng.uniform(-1,1,n); x=np.diff(np.concatenate([[0],x]))
    return x*np.exp(-tt*70)*.5
def clap():
    n=int(.18*SR); tt=np.arange(n)/SR; x=rng.uniform(-1,1,n)
    return x*np.exp(-tt*25)*.6
def bass(f,d):
    n=int(d*SR); tt=np.arange(n)/SR; env=np.minimum(1,tt/.01)*np.exp(-tt*2.5)
    return (np.sin(2*np.pi*f*tt)+.35*np.sin(4*np.pi*f*tt)+.15*np.sign(np.sin(2*np.pi*f*tt)))*env
def pad(fs,d):
    n=int(d*SR); tt=np.arange(n)/SR; env=np.minimum(1,tt/.4)*np.minimum(1,(d-tt)/.4)
    return sum(np.sin(2*np.pi*f*tt+np.sin(2*np.pi*.3*tt))*.3 for f in fs)*env
BPM=120; beat=60/BPM; off=drop%(4*beat)
chords=[(110.0,[220,261.6,329.6]),(87.3,[174.6,220,261.6]),(130.8,[261.6,329.6,392]),(98.0,[196,246.9,293.7])]  # Am F C G
b=off-4*beat; k=0
while b<dur:
    bar=int(round((b-off)/(4*beat)))
    root,fs=chords[bar%4]
    if k%4==0: add(mus,b,pad(fs,4*beat),.35 if b>=full-0.01 else .25)
    add(mus,b,bass(root/2 if k%2 else root/2,beat*.9),.32)
    if b>=full-0.01:
        add(mus,b,kick(),.9)
        if k%4 in (1,3): add(mus,b,clap(),.35)
    add(mus,b+beat/2,hat(),.35)
    b+=beat; k+=1
# drop crash
n=int(1.6*SR); tt=np.arange(n)/SR; add(mus,drop,rng.uniform(-1,1,n)*np.exp(-tt*2.2)*.25)
# fade out
fo=np.clip((dur-t)/1.2,0,1); mus*=fo
# sfx
def whoosh(d=.5):
    n=int(d*SR); x=rng.uniform(-1,1,n); y=np.zeros(n); a=0.0
    for i in range(n):
        p=i/n; kk=.02+.25*np.sin(np.pi*p); a+=kk*(x[i]-a); y[i]=a*np.sin(np.pi*p)**2
    return y*3
def pop(d=.12,f0=900,f1=200):
    n=int(d*SR); tt=np.arange(n)/SR; f=f0*(f1/f0)**(tt/d); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*np.minimum(1,tt/.002)*np.exp(-tt/.03)
def impact(d=.9):
    n=int(d*SR); tt=np.arange(n)/SR; f=110*(40/110)**(tt/d); ph=2*np.pi*np.cumsum(f)/SR
    return np.sin(ph)*np.exp(-tt/.2)
G={'whoosh':(whoosh,.35),'pop':(pop,.4),'impact':(impact,.8)}
for name,ts in cues.items():
    fn,g=G[name]; s=fn()
    for x in ts: add(sfx,x,s,g)
mix=mus*0.55+sfx
mix/=max(1e-9,np.abs(mix).max()/0.89)
st=np.stack([mix,mix],1)
with wave.open(out,'wb') as w:
    w.setnchannels(2);w.setsampwidth(2);w.setframerate(SR);w.writeframes((st*32767).astype('<i2').tobytes())
print('wrote',out)
