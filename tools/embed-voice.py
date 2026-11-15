#!/usr/bin/env python3
"""Озвучивает фразы игры голосом Svetlana и встраивает их в html.

Запуск: python embed-voice.py <игра.html> <папка для кэша>
Нужны пакеты: edge-tts soundfile numpy lameenc

Фразы берутся из объекта `const SAY = { ... };` в коде игры,
звук записывается в <script id="voiceData" type="application/json">.
"""
import asyncio, base64, json, os, re, sys
import edge_tts, lameenc, numpy as np, soundfile as sf

VOICE, RATE = 'ru-RU-SvetlanaNeural', '-10%'
SR = 24000


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
    n, m = int(.005 * SR), int(.02 * SR)
    a[:n] *= np.linspace(0, 1, n)
    a[-m:] *= np.linspace(1, 0, m)
    return a


def to_mp3(a):
    a = a / max(np.abs(a).max() / .95, 1)
    e = lameenc.Encoder()
    e.set_bit_rate(64); e.set_in_sample_rate(SR); e.set_channels(1); e.set_quality(2)
    return bytes(e.encode((a * 32767).astype(np.int16).tobytes()) + e.flush())


async def main(game, cache):
    os.makedirs(cache, exist_ok=True)
    html = open(game, encoding='utf-8').read()
    block = re.search(r'const SAY = \{(.*?)\};', html, re.S).group(1)
    phrases = re.findall(r":\s*'([^']+)'", block)
    data = {}
    for phrase in phrases:
        pcm = np.concatenate([load_trimmed(await fetch(phrase, cache)), np.zeros(int(.15 * SR))])
        data[phrase] = base64.b64encode(to_mp3(pcm)).decode()
        print(f'{phrase:28s} {len(pcm) / SR:.2f} с')
    html, n = re.subn(r'(<script id="voiceData" type="application/json">).*?(</script>)',
                      lambda m: m.group(1) + json.dumps(data, ensure_ascii=False) + m.group(2),
                      html, flags=re.S)
    assert n == 1
    open(game, 'w', encoding='utf-8').write(html)


asyncio.run(main(sys.argv[1], sys.argv[2]))
