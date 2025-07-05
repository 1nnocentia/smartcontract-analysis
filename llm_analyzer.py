
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
You are a world-class smart contract auditor with deep expertise in DeFi, tokenomics, and EVM security. You will be provided with a complete JSON object containing a smart contract's metadata and its full Abstract Syntax Tree (AST).

YOUR TASK:
Perform a deep, contextual analysis to find risks that are often missed by automated static analysis tools. Use the provided AST to understand the contract's structure, control flow, and function relationships. DO NOT analyze the raw source code, focus your analysis on the provided knowledge base (AST and metadata).

FOCUS AREAS:
1.  **Business Logic Flaws:** Are there exploitable paths that contradict the contract's intent? (e.g., incorrect state management, flawed operational sequences).
2.  **Economic & Tokenomic Risks:**
    - Analyze minting/burning functions. Is there sufficient control to prevent infinite inflation or deflation?
    - Examine transfer/fee mechanisms. Is there potential for manipulation (e.g., reentrancy, fee evasion)?
    - Can critical parameters (like `_taxReceiver`) be set to malicious addresses?
3.  **Centralization Risks:**
    - Analyze the usage of access control modifiers like `onlyOwner`. How critical are the protected functions?
    - Does any single address hold excessive power that could harm users?
4.  **Gas Efficiency and Best Practices:**
    - Are there any glaringly inefficient code patterns or data structures visible from the AST?
    - Does the contract adhere to modern security standards (e.g., checks-effects-interactions)?

KNOWLEDGE BASE (METADATA AND AST):
```json
{knowledge_base_str}
```

REQUIRED OUTPUT FORMAT:
Your entire response MUST be a single, valid JSON object and nothing else. Adhere strictly to this structure:
{{
  "executive_summary": "A 2-3 sentence executive summary of the contract's overall security posture based on your findings.",
  "overall_risk_grading": "A single holistic risk rating: 'Critical', 'High', 'Medium', or 'Low'.",
  "findings": [
    {{
      "severity": "The severity of the finding: 'Critical', 'High', 'Medium', 'Low', or 'Informational'.",
      "category": "The category of the finding: 'Logic Flaw', 'Economic Risk', 'Centralization', 'Gas Optimization', or 'Best Practice'.",
      "description": "A detailed explanation of the risk or suggestion. Be specific and reference contract elements if possible.",
      "confidence": "A float between 0.0 and 1.0 representing your confidence in this finding."
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
