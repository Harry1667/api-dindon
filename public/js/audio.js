// Web Audio 音效模組
let _audioCtx = null;

function getAudio() {
    if (!_audioCtx) {
        try {
            _audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        } catch (e) { return null; }
    }
    if (_audioCtx.state === 'suspended') _audioCtx.resume();
    return _audioCtx;
}

function _beep(freq, dur, type = 'sine', vol = 0.15, delay = 0) {
    const ctx = getAudio();
    if (!ctx) return;
    const t0 = ctx.currentTime + delay;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, t0);
    gain.gain.linearRampToValueAtTime(vol, t0 + 0.005);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t0);
    osc.stop(t0 + dur + 0.02);
}

export function playTap()      { _beep(1800, 0.04, 'square',   0.06); }
export function playSend()     { _beep(880,  0.08, 'sine',     0.10); }
export function playDing()     { _beep(1320, 0.25, 'triangle', 0.18); }
export function playDingDong() {
    _beep(1320, 0.22, 'triangle', 0.22, 0);
    _beep(990,  0.32, 'triangle', 0.22, 0.18);
}
