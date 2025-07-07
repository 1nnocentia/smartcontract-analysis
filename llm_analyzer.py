import json
import httpx
import logging
from typing import Dict, Any

from config import settings
from models import LLMAnalysisResult
from prompts import LLM_KAG_PROMPT_TEMPLATE

# Konfigurasi logging
logger = logging.getLogger(__name__)


def create_kag_prompt(input_data: Dict[str, Any]) -> str:
    """
    Membuat prompt KAG yang canggih untuk LLM, menggunakan seluruh
    JSON input sebagai basis pengetahuan.
    """
    token_address = input_data.get("contract_metadata", {}).get("token_address", "N/A")
    file_path = input_data.get("ast", {}).get("absolutePath", "N/A")
    knowledge_base_str = json.dumps(input_data, indent=2)

    return LLM_KAG_PROMPT_TEMPLATE.format(
        token_address=token_address,
        file_path=file_path,
        knowledge_base_str=knowledge_base_str
    )

async def run_analysis(input_data: Dict[str, Any]) -> LLMAnalysisResult:
    """
    Analisis LLM menggunakan httpx
    """
    logger.info("Memulai analisis kontekstual LLM (KAG)...")
    prompt = create_kag_prompt(input_data)

    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={settings.GEMINI_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "topP": 0.95,
        }
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                json=payload,
                timeout=settings.LLM_TIMEOUT_SECONDS
            )
            response.raise_for_status()

        response_json = response.json()

        if not response_json.get('candidates') or not response_json['candidates'][0].get('content'):
            raise KeyError("Struktur respons LLM tidak valid.")
        
        report_text = response_json['candidates'][0]['content']['parts'][0]['text']
        report_data = json.loads(report_text)

        validated_report = LLMAnalysisResult(**report_data)
        logger.info("Analisis LLM (KAG) berhasil dan output telah divalidasi.")
        return validated_report
    
    except Exception as e:
        error_msg = f"Analisis LLM gagal: {type(e).__name__} - {e}"
        logger.error(error_msg, exc_info=True)
        return LLMAnalysisResult(error=error_msg)