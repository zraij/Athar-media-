"""Athar brand music bed (one track for every reel): warm, modern, uplifting. 96 BPM, D major, 18 s, 48 kHz stereo.
python3 theme_music.py out.wav [duration]
Soft piano arpeggio + warm pad + sub bass, light percussion from bar 2, gentle reverb, fade out.
"""
import sys, numpy as np, wave
SR = 48000
out = sys.argv[1]; DUR = float(sys.argv[2]) if len(sys.argv) > 2 else 18.0
N = int(DUR * SR); rng = np.random.default_rng(11)
L = np.zeros(N); Rt = np.zeros(N)
BPM = 96; beat = 60 / BPM; bar = 4 * beat
def hz(m): return 440 * 2 ** ((m - 69) / 12)
def add(buf, t0, sig, g=1.0):
    i = int(t0 * SR)
    if i >= N: return
    n = min(len(sig), N - i); buf[i:i + n] += sig[:n] * g
def piano(m, d=1.6, vel=1.0):
    n = int(d * SR); t = np.arange(n) / SR; f = hz(m)
    s = sum(a * np.sin(2 * np.pi * f * k * t) * np.exp(-t * (2.2 + k * 1.3)) for k, a in [(1, 1), (2, .45), (3, .22), (4, .12), (5, .06)])
    att = np.minimum(1, t / .004)
    return s * att * vel * .35
def pad(ms, d):
    n = int(d * SR); t = np.arange(n) / SR
    env = np.minimum(1, t / .9) * np.minimum(1, (d - t) / .9)
    s = np.zeros(n)
    for m in ms:
        for det in (-.07, 0, .07):
            ph = 2 * np.pi * hz(m) * (1 + det / 100) * t
            s += (np.sin(ph) + .3 * np.sin(2 * ph) + .12 * np.sin(3 * ph))
    # one-pole low-pass for warmth
    y = np.zeros(n); a = .04; acc = 0.0
    for i in range(0, n):
        acc += a * (s[i] - acc); y[i] = acc
    return y * env * .05
def sub(m, d):
    n = int(d * SR); t = np.arange(n) / SR
    return np.sin(2 * np.pi * hz(m) * t) * np.minimum(1, t / .02) * np.exp(-t * 1.2) * .5
def kick():
    n = int(.4 * SR); t = np.arange(n) / SR; f = 45 + 70 * np.exp(-t * 28)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 7) * .9
def snap():
    n = int(.22 * SR); t = np.arange(n) / SR; x = rng.uniform(-1, 1, n)
    x = np.diff(np.concatenate([[0], x])); return x * np.exp(-t * 26) * .14
def shaker():
    n = int(.08 * SR); t = np.arange(n) / SR; x = rng.uniform(-1, 1, n)
    x = np.diff(np.concatenate([[0], np.diff(np.concatenate([[0], x]))])); return x * np.sin(np.pi * t / .08) * .03
# D major: Dmaj7 - Bm7 - Gmaj7 - A(sus) ; MIDI roots
chords = [(50, [62, 66, 69, 73]), (47, [59, 62, 66, 69]), (43, [55, 59, 62, 66]), (45, [57, 61, 64, 69])]
arp_pat = [0, 2, 1, 3, 2, 1, 3, 2]
t0 = 0.0; b = 0
while t0 < DUR:
    root, notes = chords[b % 4]
    p = pad([n - 12 for n in notes[:3]], bar + .9); add(L, t0, p); add(Rt, t0, p)
    for k, idx in enumerate(arp_pat):
        tt = t0 + k * beat / 2; m = notes[idx] + (12 if k in (3, 7) else 0)
        s = piano(m, 1.4, .9 if k % 2 == 0 else .7); pan = .5 + .25 * np.sin(k)
        add(L, tt, s, 1 - pan * .6); add(Rt, tt, s, .4 + pan * .6)
    if t0 >= bar - .01:
        for q in range(4):
            sb = sub(root - 12, beat * .95); add(L, t0 + q * beat, sb); add(Rt, t0 + q * beat, sb)
            if q in (0, 2): k_ = kick(); add(L, t0 + q * beat, k_, .8); add(Rt, t0 + q * beat, k_, .8)
            if q in (1, 3): sn = snap(); add(L, t0 + q * beat, sn); add(Rt, t0 + q * beat, sn, .8)
        for e in range(8): sh = shaker(); add(L, t0 + e * beat / 2 + beat / 4, sh, .7); add(Rt, t0 + e * beat / 2 + beat / 4, sh)
    t0 += bar; b += 1
# reverb: exponential-decay noise impulse, convolved via FFT
ir_n = int(1.6 * SR); ti = np.arange(ir_n) / SR
def smooth(x, k=24):
    ker = np.ones(k) / k
    for _ in range(3): x = np.convolve(x, ker, mode='same')
    return x
irL = smooth(rng.normal(0, 1, ir_n)) * np.exp(-ti * 3.2); irR = smooth(rng.normal(0, 1, ir_n)) * np.exp(-ti * 3.2)
def conv(x, ir):
    n = len(x) + len(ir); nf = 1 << (n - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, nf) * np.fft.rfft(ir, nf), nf)[:len(x)]
    return y / (np.abs(ir).sum() ** .5 * 6)
L2 = L + conv(L, irL) * .9; R2 = Rt + conv(Rt, irR) * .9
t = np.arange(N) / SR
fade = np.minimum(1, t / .4) * np.clip((DUR - t) / 1.6, 0, 1)
st = np.stack([L2 * fade, R2 * fade], 1)
st /= np.abs(st).max() / .85
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((st * 32767).astype('<i2').tobytes())
print('wrote', out)
