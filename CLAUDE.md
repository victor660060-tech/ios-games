# iOS-игры в одном HTML-файле

Каждая игра — **один самодостаточный `.html` файл** (HTML5 + SVG + JS + CSS внутри).
Файлы публикуются на GitHub (GitHub Pages) и запускаются в Safari на iPhone/iPad.

## Правила

- Никаких внешних зависимостей, сборки, npm, CDN — всё inline. Файл должен работать офлайн.
- Графика — SVG (inline или генерируемый из JS); при необходимости `<canvas>`. Звук — Web Audio API (синтез), без аудиофайлов.
- Одна игра = один файл в корне: `имя-игры.html`. `index.html` — список игр со ссылками.

## Особенности iOS Safari

- `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">`
- Учитывать вырез/home-indicator: `env(safe-area-inset-*)`.
- Высота экрана: `100dvh` (не `100vh`).
- Отключить жесты браузера: `touch-action: none`, `user-select: none`, `-webkit-user-select: none`, `-webkit-touch-callout: none`, `overscroll-behavior: none`; `preventDefault` на `touchmove`.
- Ввод — Pointer Events (`pointerdown/move/up`), тач в первую очередь; мышь/клавиатура как бонус для отладки на ПК.
- Web Audio разблокируется только после жеста пользователя — создавать/`resume()` AudioContext по первому тапу.
- Нет hover, нет правого клика; размер кнопок ≥ 44pt.
- Поддержка «На экран Домой»: `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`, `theme-color`, иконка как data-URI.
- Сохранения — `localStorage` в `try/catch` (в приватном режиме может не работать).
- Пауза при `visibilitychange`; анимация через `requestAnimationFrame` с delta-time.
- Поддержка портретной и альбомной ориентации (или явная подсказка повернуть устройство).

## Проверка

Локально: `python3 -m http.server 8000` и открыть с iPhone по IP компьютера в той же сети
(или в desktop-браузере в режиме эмуляции устройства).
