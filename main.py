from dotenv import load_dotenv
import os
import uuid
import json
import requests
import subprocess
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from google import genai
from docx import Document

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") 
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "whisper-1")

if not all([SUPABASE_URL, SUPABASE_KEY, GEMINI_API_KEY, OPENAI_API_KEY]):
    raise Exception(
        "Не заданы ENV переменные (нужны SUPABASE_URL, SUPABASE_KEY/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_ANON_KEY, GEMINI_API_KEY, OPENAI_API_KEY)"
    )

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client = genai.Client(api_key=GEMINI_API_KEY)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"status": "ok", "message": "API is running"}

class AnalyzeRequest(BaseModel):
    videoUrl: str
    userId: str

class AnalyzeEssayRequest(BaseModel):
    essayUrl: str
    userId: str

def download_file(url, filename):
    for _ in range(3):
        try:
            response = requests.get(url, stream=True, timeout=30)
            if response.status_code == 200:
                with open(filename, "wb") as f:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            f.write(chunk)
                return
        except:
            continue
    raise Exception("Ошибка скачивания файла")

def extract_audio(video_path, audio_path):
    subprocess.run([
        "ffmpeg", "-i", video_path,
        "-ar", "16000",
        "-ac", "1",
        "-y",
        audio_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def transcribe_video(video_file):
    audio_file = video_file.replace(".mov", ".wav")
    extract_audio(video_file, audio_file)
    
    try:
        with open(audio_file, "rb") as f:
            response = requests.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                data={
                    "model": WHISPER_MODEL,
                    "language": "ru",
                    "response_format": "json"
                },
                files={"file": (os.path.basename(audio_file), f, "audio/wav")},
                timeout=120
            )
        
        if response.status_code >= 400:
            raise RuntimeError(f"Ошибка OpenAI API: {response.status_code} {response.text}")
        
        payload = response.json()
        text = payload.get("text", "").strip()
        if not text:
            raise RuntimeError("OpenAI API вернул пустую транскрипцию")
        return text
    finally:
        if os.path.exists(audio_file):
            os.remove(audio_file)

def analyze_leadership(transcript):
    transcript = transcript[:5000]
    prompt_main = (
        "Ты — эксперт приёмной комиссии InVision U (инновационного университета, поддерживаемого inDrive), специализирующийся на выявлении лидерского потенциала, предпринимательского мышления и способности к росту у кандидатов.\n"
        "\n"
        "Твоя задача — анализировать кандидатов на основе анкеты, эссе, транскрипта интервью или видеопрезентации.\n"
        "\n"
        " ВАЖНО: Ты НЕ принимаешь окончательное решение о зачислении. Ты создаёшь обоснованную рекомендацию и аналитический профиль кандидата для помощи комиссии.\n"
        "\n"
        "Суди строго по фактам, не добавляй субъективных оценок, не смягчай слабые стороны, не добавляй позитивных или обтекаемых формулировок. Говори только по существу, отмечай как сильные, так и слабые стороны кандидата.\n"
        "\n"
        "## ЦЕЛЬ ОЦЕНКИ\n"
        "Выявить кандидатов с высоким потенциалом стать: лидерами, предпринимателями, инициаторами изменений (change-makers), даже если у них слабые формальные достижения, слабая самопрезентация или несовершенное эссе.\n"
        "\n"
        "##  ПРИНЦИПЫ\n"
        "1. Смотри глубже текста — ищи сигналы потенциала, а не только форму.\n"
        "2. Не наказывай за слабый язык или структуру.\n"
        "3. Учитывай контекст (социальный, образовательный, региональный).\n"
        "4. Выявляй 'скрытые таланты'.\n"
        "5. Минимизируй предвзятость (гендер, регион, язык, стиль).\n"
        "6. Учитывай, что текст может быть частично сгенерирован ИИ — ищи подлинные признаки личности.\n"
        "\n"
        "##  КРИТЕРИИ ОЦЕНКИ (0–10)\n"
        "Оцени кандидата по следующим осям:\n"
        "1. Лидерский потенциал: Инициативность, Влияние на других, Примеры действий\n"
        "2. Предпринимательское мышление: Способность видеть возможности, Решение проблем, Самостоятельные проекты\n"
        "3. Мотивация и смысл: Зачем кандидат хочет учиться, Есть ли внутренняя мотивация, Связь с ценностями\n"
        "4. Способность к росту (growth mindset): Отношение к ошибкам, Обучаемость, Гибкость мышления\n"
        "5. Социальное влияние / ценности: Желание приносить пользу, Эмпатия, Вклад в сообщество\n"
        "6. Подлинность (authenticity): Насколько текст 'живой', Есть ли личные истории, Признаки не-ИИ мышления\n"
        "\n"
        "##  СКОРИНГ\n"
        "Для каждого критерия: Дай оценку от 0 до 10 и краткое объяснение (1–2 предложения). Рассчитай общий балл (среднее) и потенциал (High / Medium / Low).\n"
        "\n"
        "##  ВАЖНО: ВЫЯВЛЕНИЕ СКРЫТОГО ПОТЕНЦИАЛА\n"
        "Отдельно ответь: Есть ли признаки 'недооценённого кандидата'? (да/нет) Почему он мог бы быть упущен при классическом отборе?\n"
        "\n"
        "##  РИСКИ\n"
        "Укажи: Есть ли признаки переиспользования шаблонов, AI-сгенерированного текста, 'over-polished' подачи без содержания.\n"
        "\n"
        "##  ФОРМАТ ОТВЕТА (СТРОГО)\n"
        "Ответ должен быть в JSON:\n"
        "{\n  'scores': {\n    'leadership': { 'score': X, 'reason': '' },\n    'entrepreneurship': { 'score': X, 'reason': '' },\n    'motivation': { 'score': X, 'reason': '' },\n    'growth': { 'score': X, 'reason': '' },\n    'social_impact': { 'score': X, 'reason': '' },\n    'authenticity': { 'score': X, 'reason': '' }\n  },\n  'overall_score': X,\n  'potential_level': 'High | Medium | Low',\n  'hidden_gem': {\n    'is_hidden_gem': true/false,\n    'explanation': ''\n  },\n  'risks': {\n    'ai_generated': true/false,\n    'bias_risk': true/false,\n    'other': ''\n  },\n  'final_recommendation': 'Strong Yes | Yes | Maybe | No',\n  'summary': 'Краткий вывод о кандидате (3-4 предложения)'\n}\n"
        f"\n---\n\nАНАЛИЗИРУЙ ЭТОТ ТЕКСТ КАНДИДАТА:\n{transcript}"
    )

    prompt_ai = (
        "Ты — эксперт по анализу текста и выявлению искусственно сгенерированного контента (LLM/AI).\n"
        "\n"
        "Твоя задача — определить, написан ли текст человеком или сгенерирован искусственным интеллектом.\n"
        "\n"
        "Проанализируй текст по следующим критериям:\n"
        "1. Стиль и естественность: Насколько текст звучит “по-человечески”, Есть ли повторяемость или шаблонность\n"
        "2. Логика и структура: Слишком ли идеальная структура (введение → аргументы → вывод), Есть ли неожиданные переходы или наоборот чрезмерная гладкость\n"
        "3. Лексика: Используются ли общие, “универсальные” формулировки, Есть ли клише и типичные AI-фразы\n"
        "4. Конкретика: Есть ли реальные примеры, личный опыт, Или текст обобщённый и абстрактный\n"
        "5. Ошибки: Есть ли мелкие человеческие ошибки, Или текст слишком “идеальный”\n"
        "\n"
        "После анализа:\n"
        "— Дай вероятность (в %) что текст написан ИИ\n"
        "— Дай вероятность (в %) что текст написан человеком\n"
        "— Объясни решение (3–6 пунктов)\n"
        "— Укажи ключевые признаки, которые повлияли на решение\n"
        "— Если возможно, выдели конкретные фрагменты текста, которые выглядят как AI\n"
        "\n"
        "Формат ответа:\n"
        "Вероятность AI: XX%\n"
        "Вероятность человек: XX%\n"
        "Обоснование:\n"
        "1. ...\n2. ...\n3. ...\n"
        "Подозрительные фрагменты:\n* \"...\"\n* \"...\"\n"
        f"\n---\n\nАНАЛИЗИРУЙ ЭТОТ ТЕКСТ:\n{transcript}"
    )

    response_main = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt_main
    )
    text_main = getattr(response_main, "text", None)
    if not text_main:
        try:
            text_main = response_main.candidates[0].content.parts[0].text
        except:
            text_main = "Ошибка анализа"

    response_ai = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt_ai
    )
    text_ai = getattr(response_ai, "text", None)
    if not text_ai:
        try:
            text_ai = response_ai.candidates[0].content.parts[0].text
        except:
            text_ai = "Ошибка AI-анализа"

    return text_main


def clean_llm_json_text(value: str) -> str:
    cleaned = value.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.replace("```json", "", 1)
        cleaned = cleaned.replace("```", "")
    return cleaned.strip()


def extract_essay_text(filename: str, ext: str) -> str:
    if ext == "docx":
        doc = Document(filename)
        return "\n".join([p.text for p in doc.paragraphs]).strip()

    if ext == "txt":
        # Попробовать разные кодировки
        for encoding in ['utf-8', 'cp1252', 'iso-8859-1', 'latin-1']:
            try:
                with open(filename, "r", encoding=encoding) as f:
                    return f.read().strip()
            except (UnicodeDecodeError, LookupError):
                continue
        # Если всё не поработало, читаем с игнорированием ошибок
        with open(filename, "r", encoding='utf-8', errors='ignore') as f:
            return f.read().strip()

    if ext == "pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            raise RuntimeError("PDF для анализа пока не поддерживается в окружении сервера. Установите pypdf или загрузите DOCX/TXT.")

        reader = PdfReader(filename)
        text_parts = []
        for page in reader.pages:
            text_parts.append(page.extract_text() or "")

        text = "\n".join(text_parts).strip()
        if not text:
            raise RuntimeError("Не удалось извлечь текст из PDF.")
        return text

    raise RuntimeError(f"Неподдерживаемый формат эссе: {ext}")


@app.post("/analyze-video")
async def analyze_video(data: AnalyzeRequest):
    url = data.videoUrl
    if 'dropbox.com' in url and 'dl=0' in url:
        url = url.replace('dl=0', 'dl=1')
    user_id = data.userId
    filename = f"{uuid.uuid4()}.mov"
    print(f"[DEBUG] Video URL: {url}")
    try:
        print("[DEBUG] Скачивание файла...")
        await run_in_threadpool(download_file, url, filename)
        print(f"[DEBUG] Файл скачан: {filename}, размер: {os.path.getsize(filename)} байт")
        print("[DEBUG] Транскрибация...")
        transcript = await run_in_threadpool(transcribe_video, filename)
        print(f"[DEBUG] Транскрипция: {transcript[:100]}...")
        print("[DEBUG] Анализ...")
        leadership_result = await run_in_threadpool(analyze_leadership, transcript)
        print(f"[DEBUG] Анализ завершён: {leadership_result[:100]}...")
        print("[DEBUG] Сохраняю в Supabase...")
        supabase.table("video_transcripts").insert({
            "user_id": user_id,
            "video_url": url,
            "transcript": transcript,
            "result_llm": leadership_result
        }).execute()
        print("[DEBUG] Сохранено.")
        os.remove(filename)
        print("[DEBUG] Временный файл удалён.")
        return {
            "status": "ok",
            "transcript": transcript,
            "analysis": leadership_result
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(filename):
            os.remove(filename)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze-essay")
async def analyze_essay(data: AnalyzeEssayRequest):
    url = data.essayUrl
    if 'dropbox.com' in url and 'dl=0' in url:
        url = url.replace('dl=0', 'dl=1')
    user_id = data.userId
    
    # Правильно парсить расширение из URL
    url_path = urlparse(url).path
    ext = os.path.splitext(url_path)[1].lower().lstrip('.')
    if ext not in ["docx", "txt", "pdf"]:
        raise HTTPException(status_code=400, detail=f"Неподдерживаемый формат эссе: {ext or 'unknown'}")
    
    filename = f"{uuid.uuid4()}.{ext}"
    print(f"[DEBUG] Essay URL: {url}, ext: {ext}")
    try:
        print("[DEBUG] Скачивание эссе...")
        await run_in_threadpool(download_file, url, filename)
        print(f"[DEBUG] Эссе скачано: {filename}, размер: {os.path.getsize(filename)} байт")

        essay_text = await run_in_threadpool(extract_essay_text, filename, ext)
        if not essay_text:
            raise RuntimeError("Текст эссе пустой после обработки файла.")

        print(f"[DEBUG] Текст эссе: {essay_text[:100]}...")
        print("[DEBUG] Анализ эссе...")
        essay_result_raw = await run_in_threadpool(analyze_leadership, essay_text)
        cleaned_result = clean_llm_json_text(essay_result_raw)

        try:
            essay_result = json.loads(cleaned_result)
        except Exception:
            essay_result = {"raw": essay_result_raw}

        print(f"[DEBUG] Анализ эссе завершён: {str(essay_result)[:100]}...")
        print("[DEBUG] Сохраняю результат эссе в Supabase...")
        supabase.table("essay_results").insert({
            "user_id": user_id,
            "result_essay": essay_result
        }).execute()
        print("[DEBUG] Сохранено.")
        os.remove(filename)
        print("[DEBUG] Временный файл эссе удалён.")
        return {
            "status": "ok",
            "essay_text": essay_text,
            "analysis": essay_result
        }
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        if os.path.exists(filename):
            os.remove(filename)
        raise HTTPException(status_code=500, detail=str(e))