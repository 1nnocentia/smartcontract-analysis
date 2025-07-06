import os
import json
import requests
import asyncio
import logging
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Konfigurasi logging
logger = logging.getLogger(__name__)

# --- Pydantic Models untuk Analisis LLM ---

class LLMIssue(BaseModel):
    """Model untuk satu isu yang ditemukan oleh LLM."""
    severity: str = Field(..., description="Tingkat keparahan: 'Kritis', 'Tinggi', 'Sedang', 'Rendah', atau 'Informasional'.")
    category: str = Field(..., description="Kategori isu, cth: 'Logic Flaw', 'Economic Risk', 'Centralization', 'Gas Optimization'.")
    description: str = Field(..., description="Penjelasan detail mengenai risiko atau saran perbaikan.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Tingkat keyakinan LLM terhadap temuannya (0.0 - 1.0).")

class LLMAnalysisResult(BaseModel):
    """Model untuk output akhir dari analisis LLM."""
    executive_summary: str = Field(..., description="Ringkasan eksekutif 2-3 kalimat tentang postur keamanan kontrak secara keseluruhan.")
    overall_risk_grading: str = Field(..., description="Penilaian risiko holistik dalam satu kata: 'Kritis', 'Tinggi', 'Sedang', atau 'Rendah'.")
    findings: List[LLMIssue] = Field(..., description="Daftar semua temuan dari LLM.")
    error: Optional[str] = None

# --- Core Functions ---

def create_kag_prompt(full_input_json: Dict[str, Any]) -> str:
    """
    Membuat prompt KAG yang canggih untuk LLM, menggunakan seluruh
    JSON input sebagai basis pengetahuan.
    """
    knowledge_base_str = json.dumps(full_input_json, indent=2)

    prompt = f"""
Anda adalah seorang auditor smart contract kelas dunia dengan keahlian mendalam di bidang DeFi, tokenomics, dan keamanan EVM. Anda akan diberikan sebuah objek JSON lengkap yang berisi metadata smart contract beserta Abstract Syntax Tree (AST) lengkapnya.

TUGAS ANDA:
Lakukan analisis kontekstual yang mendalam untuk menemukan risiko yang seringkali terlewat oleh alat analisis statis otomatis. Gunakan AST yang disediakan untuk memahami struktur, alur kontrol, dan hubungan antar fungsi di dalam kontrak. JANGAN menganalisis kode sumber mentah, fokuskan analisis Anda pada basis pengetahuan yang disediakan (AST dan metadata).

AREA FOKUS:
1.  **Business Logic Flaws:** Apakah ada jalur yang dapat dieksploitasi yang bertentangan dengan tujuan kontrak? (misalnya, manajemen state yang salah, urutan operasional yang keliru).
2.  **Economic & Tokenomic Risks:**
    - Analisis fungsi minting/burning. Apakah ada kontrol yang cukup untuk mencegah inflasi atau deflasi tak terbatas?
    - Periksa mekanisme transfer/biaya. Apakah ada potensi manipulasi (misalnya, reentrancy, penghindaran biaya)?
    - Dapatkah parameter kritis (seperti _taxReceiver) diatur ke alamat yang berbahaya?
3.  **Centralization Risks:**
    - Analisis penggunaan modifier kontrol akses seperti onlyOwner. Seberapa kritis fungsi-fungsi yang dilindunginya?
    - Apakah ada satu alamat yang memiliki kekuatan berlebihan yang dapat membahayakan pengguna?
4.  **Gas Efficiency and Best Practices:**
    - Apakah ada pola kode atau struktur data yang sangat tidak efisien yang terlihat dari AST?
    - Apakah kontrak mematuhi standar keamanan modern (misalnya, pola checks-effects-interactions)?

KNOWLEDGE BASE (METADATA AND AST):
```json
{knowledge_base_str}
```

REQUIRED OUTPUT FORMAT:
Seluruh respons Anda HARUS berupa satu objek JSON yang valid dan tidak ada yang lain. Patuhi struktur ini dengan ketat:
{{
  "executive_summary": "Ringkasan eksekutif 2-3 kalimat mengenai postur keamanan kontrak secara keseluruhan berdasarkan temuan Anda.",
  "overall_risk_grading": "Satu peringkat risiko holistik: 'Kritis', 'Tinggi', 'Sedang', atau 'Rendah'.",
  "findings": [
    {{
      "severity": "Tingkat keparahan temuan: 'Kritis', 'Tinggi', 'Sedang', 'Rendah', atau 'Informasional'.",
      "category": "Kategori temuan: 'Logic Flaw', 'Economic Risk', 'Centralization', 'Gas Optimization', or 'Best Practice'.",
      "description": "Penjelasan detail mengenai risiko atau saran. Jelaskan secara spesifik dan sebutkan elemen kontrak jika memungkinkan.",
      "confidence": "Angka desimal antara 0.0 hingga 1.0 yang merepresentasikan tingkat keyakinan Anda terhadap temuan ini."
    }}
  ]
}}
"""
    return prompt

async def run_analysis(full_input_json: Dict[str, Any]) -> LLMAnalysisResult:
    """
    Fungsi utama untuk modul ini. Menjalankan analisis LLM.
    """
    logger.info("Memulai analisis kontekstual LLM (KAG)...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("GEMINI_API_KEY tidak ditemukan di environment variables.")
        return LLMAnalysisResult(executive_summary="", overall_risk_grading="Unknown", findings=[], error="Server error: GEMINI_API_KEY tidak dikonfigurasi.")
    
    api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key={api_key}"
    prompt = create_kag_prompt(full_input_json)

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
            "topP": 0.95,
        }
    }

    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, 
            lambda: requests.post(api_url, json=payload, timeout=120)
        )
        response.raise_for_status()
        
        response_json = response.json()
        
        if not response_json.get('candidates') or not response_json['candidates'][0].get('content'):
            raise KeyError("Struktur respons LLM tidak valid: 'candidates' atau 'content' tidak ada.")

        report_text = response_json['candidates'][0]['content']['parts'][0]['text']
        report_data = json.loads(report_text)
        
        validated_report = LLMAnalysisResult(**report_data)
        logger.info("Analisis LLM (KAG) berhasil dan output telah divalidasi.")
        return validated_report

    except Exception as e:
        error_msg = f"Terjadi error saat analisis LLM: {type(e).__name__} - {e}"
        logger.error(error_msg, exc_info=True)
        return LLMAnalysisResult(executive_summary="", overall_risk_grading="Error", findings=[], error=error_msg)
