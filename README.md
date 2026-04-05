# InVision Backend API

Бэкенд-сервис для оценки кандидатов по видео и эссе.

## Ключевые реализованные моменты проекта

1. Единый API для двух типов анализа:
- анализ видео через POST /analyze-video;
- анализ эссе через POST /analyze-essay.

2. Полный pipeline обработки видео:
- загрузка файла по URL;
- извлечение аудио через FFmpeg в WAV 16k mono;
- транскрибация в OpenAI Whisper;
- отправка транскрипта в Gemini;
- сохранение результата в Supabase.

3. Полный pipeline обработки эссе:
- загрузка файла по URL;
- поддержка DOCX, TXT, PDF;
- извлечение текста из документа;
- анализ текста в Gemini;
- попытка привести ответ к JSON;
- сохранение результата в Supabase.

4. Интеграция с внешними сервисами:
- Supabase для хранения результатов;
- OpenAI API для speech-to-text;
- Google Gemini для оценочного анализа.

5. Устойчивость обработки:
- повторные попытки скачивания файлов;
- автоматическая очистка временных файлов;
- валидация входных форматов;
- обработка ошибок с HTTP 400/500.

6. Неблокирующая работа FastAPI:
- тяжелые синхронные операции запускаются через threadpool,
  чтобы не блокировать event loop при одновременных запросах.

7. Готовый деплой на Railway:
- Nixpacks-конфиг для установки Python и FFmpeg;
- готовая start-команда для Uvicorn;
- использование системного PORT от Railway.

## Как устроена архитектура

Сервис реализован как монолитный FastAPI backend в одном файле main.py с разделением по ответственности на уровне функций.

1. API слой:
- маршруты и DTO-модели запросов;
- CORS и базовый health endpoint.

2. Processing слой:
- download_file;
- transcribe_video и extract_audio;
- extract_essay_text;
- analyze_leadership.

3. Data слой:
- запись в таблицы video_transcripts и essay_results через Supabase SDK.

4. Infra слой:
- конфиг сборки в nixpacks.toml;
- запуск приложения через Uvicorn.

## Переменные окружения

Обязательные:
- SUPABASE_URL
- SUPABASE_KEY или SUPABASE_SERVICE_ROLE_KEY или SUPABASE_ANON_KEY
- GEMINI_API_KEY
- OPENAI_API_KEY

Опциональные:
- WHISPER_MODEL (по умолчанию whisper-1)
- FFMPEG_PATH (если ffmpeg не доступен в PATH)

Если обязательных переменных нет, сервис завершает запуск с ошибкой.

## Схема данных Supabase

Требуются минимум две таблицы:

1. video_transcripts
- user_id
- video_url
- transcript
- result_llm
- created_at

2. essay_results
- user_id
- result_essay
- created_at

## Локальный запуск

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Railway deployment

1. Подключить репозиторий в Railway.
2. Добавить обязательные env переменные.
3. Запустить deploy.
4. Проверить GET / на статус сервиса.

Файл nixpacks.toml уже содержит:
- установку python311 и ffmpeg;
- установку зависимостей из requirements.txt;
- запуск uvicorn main:app.

