#!/usr/bin/env python3
"""Собирает озвучку для on-ona.html и встраивает её в файл игры.

Запуск: python on-ona-voice.py <папка для кэша>
Нужны пакеты: edge-tts soundfile numpy lameenc

Местоимение и слово озвучиваются отдельно и склеиваются с паузой PAUSE.
Сервис игнорирует знаки ударения, поэтому ударное окончание женских глаголов собрано
из звука: в «ушла» слог «ла» ударный от природы, его «а» делаем длиннее, громче и выше.
В «убежала» и «уехала» конечное «ла» почти не слышно, его заменяем этим же слогом.
"""
import asyncio, base64, json, os, re, sys
import edge_tts, lameenc, numpy as np, soundfile as sf

GAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'on-ona.html')
VOICE, RATE = 'ru-RU-SvetlanaNeural', '-10%'
SR = 24000

PAUSE = 0.6            # секунд между местоимением и словом
STRESS_WORDS = {'ушла', 'убежала', 'уехала'}
STRESS_LONGER = 1.6    # во сколько раз длиннее ударная «а»
STRESS_LOUDER = 2.2    # во сколько раз громче (2.2 — это примерно +7 дБ)
STRESS_HIGHER = 1.25   # во сколько раз выше тон


async def fetch(text, cache):
    path = os.path.join(cache, re.sub(r'\W', '_', text) + '.mp3')
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    for _ in range(4):
        try:
            await edge_tts.Communicate(text, VOICE, rate=RATE).save(path)
            if os.path.getsize(path) > 0:
                return path
        except Exception:
            pass
        await asyncio.sleep(3)
    raise RuntimeError(f'нет звука для {text!r}')


def load_trimmed(path):
    a, sr = sf.read(path)
    assert sr == SR, sr
    w = int(.005 * sr)
    env = np.array([np.sqrt(np.mean(a[i:i + w] ** 2)) for i in range(0, len(a) - w, w)])
    on = np.where(env > .004)[0]
    a = a[max(0, on[0] * w - int(.01 * sr)):min(len(a), (on[-1] + 1) * w + int(.03 * sr))]
    return fade(a, .005, .02)


def fade(a, t_in, t_out):
    a = a.copy()
    n, m = int(t_in * SR), int(t_out * SR)
    a[:n] *= np.linspace(0, 1, n)
    a[-m:] *= np.linspace(1, 0, m)
    return a


def frames(a):
    """Покадровый анализ: громкость, доля полосы 500–1300 Гц (гласные) и доля низких частот (л)."""
    w, hop = int(.02 * SR), int(.005 * SR)
    freqs = np.fft.rfftfreq(w, 1 / SR)
    band, low = (freqs > 500) & (freqs < 1300), freqs < 450
    win = np.hanning(w)
    starts = np.arange(0, len(a) - w, hop)
    power = [np.abs(np.fft.rfft(a[s:s + w] * win)) ** 2 for s in starts]
    rms = np.array([np.sqrt(np.mean(a[s:s + w] ** 2)) for s in starts])
    ratio = np.array([p[band].sum() / max(p.sum(), 1e-12) for p in power])
    lows = np.array([p[low].sum() / max(p.sum(), 1e-12) for p in power])
    return starts + w // 2, rms, ratio, lows


def last_vowel_frames(rms, ratio):
    """Кадры последнего ясного гласного: идём от него назад, пока доля полосы высокая."""
    strong = np.where((ratio > .3) & (rms > rms.max() * .15))[0]
    end = i = strong[-1]
    while i > 0 and ratio[i - 1] > .3:
        i -= 1
    return i, end


def wsola(x, factor):
    """Растягивает звук по времени, не меняя тон."""
    win_n, hop_out = int(.03 * SR), int(.0075 * SR)
    hop_in, search = hop_out / factor, int(.006 * SR)
    win = np.hanning(win_n)
    out = np.zeros(int(len(x) * factor) + win_n * 2)
    norm = np.zeros_like(out)
    pos, prev = 0, 0
    frame = 0
    while True:
        target = int(frame * hop_in)
        if target + win_n + search >= len(x):
            break
        if frame == 0:
            pos = 0
        else:
            ref = x[prev + hop_out:prev + hop_out + win_n]
            lo = max(0, target - search)
            cand = range(lo, target + search)
            pos = max(cand, key=lambda p: float(np.dot(x[p:p + win_n], ref)) if len(ref) == win_n else 0)
        o = frame * hop_out
        out[o:o + win_n] += x[pos:pos + win_n] * win
        norm[o:o + win_n] += win
        prev, frame = pos, frame + 1
    n = (frame - 1) * hop_out + win_n
    return out[:n] / np.maximum(norm[:n], 1e-3)


def crossfade(head, tail, t=.015):
    n = int(t * SR)
    joint = head[-n:] * np.linspace(1, 0, n) + tail[:n] * np.linspace(0, 1, n)
    return np.concatenate([head[:-n], joint, tail[n:]])


def stressed_ushla(a):
    """Усиливает ударную «а» в слове «ушла». Возвращает слово и начало слога «ла»."""
    pos, rms, ratio, lows = frames(a)
    first, _ = last_vowel_frames(rms, ratio)
    start = pos[first]
    assert .05 < (len(a) - start) / SR < .4, (len(a) - start) / SR
    i = first
    while i > 0 and lows[i - 1] > .3:    # назад по «л» до глухой «ш»
        i -= 1
    syllable = pos[i]
    assert .03 < (start - syllable) / SR < .2, (start - syllable) / SR

    # растягиваем с запасом и читаем быстрее: длина как задумано, тон выше
    vowel = a[start:]
    long = wsola(vowel, STRESS_LONGER * STRESS_HIGHER)
    t = np.arange(int(len(long) / STRESS_HIGHER))
    ramp = np.minimum(t / (.04 * SR), 1)           # тон поднимается плавно, без скачка
    p = np.cumsum(1 + (STRESS_HIGHER - 1) * ramp)
    shifted = np.interp(p * (len(long) - 1) / p[-1], np.arange(len(long)), long)
    gain = 1 + (STRESS_LOUDER - 1) * np.minimum(t / (.03 * SR), 1)
    shifted = fade(shifted * gain, 0, .05)
    return crossfade(a[:start], shifted, .01), syllable


def with_stressed_la(word, ending):
    """Заменяет безударное «-ла» на конце глагола ударным слогом из «ушла»."""
    pos, rms, ratio, _ = frames(word)
    _, end = last_vowel_frames(rms, ratio)
    cut = pos[end]
    assert .08 < (len(word) - cut) / SR < .3, (len(word) - cut) / SR
    return crossfade(word[:cut], ending)


def to_mp3(a):
    a = a / max(np.abs(a).max() / .95, 1)
    e = lameenc.Encoder()
    e.set_bit_rate(64); e.set_in_sample_rate(SR); e.set_channels(1); e.set_quality(2)
    return bytes(e.encode((a * 32767).astype(np.int16).tobytes()) + e.flush())


async def main(cache):
    os.makedirs(cache, exist_ok=True)
    html = open(GAME, encoding='utf-8').read()
    phrases = sorted(set(re.findall(r"say: '([^']+)'", html)))
    ushla, syllable = stressed_ushla(load_trimmed(await fetch('ушла.', cache)))
    stressed_la = ushla[syllable:]
    data = {}
    for phrase in phrases:
        first, word = phrase.split(' ', 1)
        a = load_trimmed(await fetch(first + '...', cache))
        b = load_trimmed(await fetch(word + '.', cache))
        if word == 'ушла':
            b = ushla
        elif word in STRESS_WORDS:
            b = with_stressed_la(b, stressed_la)
        pcm = np.concatenate([a, np.zeros(int(PAUSE * SR)), b, np.zeros(int(.15 * SR))])
        data[phrase] = base64.b64encode(to_mp3(pcm)).decode()
        print(f'{phrase:16s} {len(pcm) / SR:.2f} с')
    html, n = re.subn(r'(<script id="voiceData" type="application/json">).*?(</script>)',
                      lambda m: m.group(1) + json.dumps(data, ensure_ascii=False) + m.group(2),
                      html, flags=re.S)
    assert n == 1
    open(GAME, 'w', encoding='utf-8').write(html)


asyncio.run(main(sys.argv[1]))
