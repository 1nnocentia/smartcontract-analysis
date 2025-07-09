"""
File: main.py
File ini adalah file utama untuk menjalankan paralel processing antara analisis statis dan LLM (KAG) dan menyatukan hasill analisa tanpa duplikat.
"""


import uvicorn
import os
import json
import asyncio
import tempfile
import requests
import logging
from fastapi import FastAPI, HTTPException, Body, File, UploadFile, Depends, Form
from pydantic import BaseModel, Field, model_validator
from typing import List, Dict, Any, Optional

import static_analyzer
import llm_analyzer

# konfigurasi logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

from dotenv import load_dotenv
load_dotenv()

class AnalysisMetadata(BaseModel):
    """Metadata tentang kontrak yang dianalisis."""
    file_path: Optional[str] = Field(None, description="Path file dari kontrak yang dianalisis, jika tersedia.")
    token_address: str = Field(..., description="Alamat token kontrak di blockchain.")

class StaticAnalysisInput(BaseModel):
    """
    Endpoint untuk static analysis.
    """
    token_address: Optional[str] = Field(None, description="Alamat token kontrak yang akan dianalisis.")
    solidity_version: str = Field(..., description="Versi Solidity yang digunakan oleh kontrak.")

    @model_validator(mode='before')
    @classmethod
    def check_executive_source(cls, data:Any):
        if not isinstance(data,dict):
            return data
        if not data.get("token_address") and not data.get("source_file"):
            raise ValueError("Harus ada 'token_address' atau 'source_file' yang disediakan untuk analisis static.")
        return data


class AnalysisMetadata(BaseModel):
    """
    Metadata smart contract dianalisis menggunakan KAG.
    """
    token_address: str = Field(..., description="Alamat token kontrak yang dianalisis.")
    fetch_source_code_from_etherscan: str = Field(None, description="Source code kontrak yang diambil dari Etherscan, jika tersedia.")

app = FastAPI(
    title="Hybrid Smart Contract Analyzer",
    description="Menjalankan analisis statis (Slither, Mythril) dan analisis LLM (KAG) secara paralel menggunakan Docker.",
    version="3.1.0"
)

def fetch_source_code_from_etherscan(address: str) -> str:
    """
    Mengambil source code dari Etherscan menggunakan API.
    Membutuhkan ETHERSCAN_API_KEY di environment.
    """
    api_key = os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        logger.error("ETHERSCAN_API_KEY tidak ditemukan di environment variables.")
        raise HTTPException(status_code=500, detail="Server error: ETHERSCAN_API_KEY tidak dikonfigurasi.")

    api_url = f"https://api.etherscan.io/api?module=contract&action=getsourcecode&address={address}&apikey={api_key}"
    
    logger.info(f"Mengambil source code untuk alamat: {address}")
    
    try:
        response = requests.get(api_url, timeout=20)
        response.raise_for_status()
        data = response.json()

        if data['status'] == '1' and data['result'][0]['SourceCode']:
            source_code = data['result'][0]['SourceCode']
            # Etherscan terkadang membungkus source code dalam kurung kurawal ganda
            if source_code.startswith('{{') and source_code.endswith('}}'):
                source_code = source_code[1:-1]
                # Jika source code adalah struktur JSON (untuk multi-file), kita coba parse
                try:
                    source_files = json.loads(source_code)
                    # Gabungkan semua file menjadi satu string kode
                    # Ini adalah penyederhanaan; idealnya, tool harus mendukung multi-file
                    combined_code = ""
                    for file_info in source_files.get('sources', {}).values():
                        combined_code += file_info.get('content', '') + "\n\n"
                    logger.info("Source code multi-file berhasil digabungkan.")
                    return combined_code
                except json.JSONDecodeError:
                    # Jika gagal parse, anggap sebagai satu file
                    pass
            
            logger.info("Source code berhasil diambil dari Etherscan.")
            return source_code
        else:
            error_message = data.get('message', 'Kontrak mungkin tidak terverifikasi atau alamat tidak valid.')
            logger.warning(f"Gagal mengambil source code dari Etherscan: {error_message}")
            raise HTTPException(status_code=404, detail=f"Tidak dapat mengambil source code untuk alamat {address}. Pesan: {error_message}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error saat request ke Etherscan API: {e}")
        raise HTTPException(status_code=503, detail=f"Error saat menghubungi Etherscan API: {e}")

@app.post("/static-analysis", response_model=static_analyzer.StaticAnalysisOutput, summary="Static Analysis")
async def static_analysis(solidity_version: str = Form(..., description="Versi Solidity yang digunakan oleh kontrak."),
                          token_address: Optional[str] = Form(None, description="Alamat token kontrak yang akan dianalisis."),
                          source_file: Optional[str] = Form(None, description="Path file kontrak yang akan dianalisis.")):
    """
    Endpoint untuk menjalankan analisis statis pada smart contract.
    1. Ambil source code dari Etherscan
    2. Menjalankan analisis statis menggunakan Slither & Mythril
    3. Laporan analisis
    """
    if not token_address and not source_file:
        raise HTTPException(status_code=400, detail="Harus ada 'token_address' atau 'source_file' yang disediakan untuk analisis static.")
    if token_address and source_file:
        raise HTTPException(status_code=400, detail="Tidak bisa menggunakan 'token_address' dan 'source_file' bersamaan.")

    source_code = ""
    sol_version = solidity_version.strip("^")

    if source_file:
        logger.info(f"Mengambil source code dari file: {source_file.filename}")
        content_bytes = await source_file.read()
        source_code = content_bytes.decode('utf-8')
    elif token_address:
        logger.info(f"Mengambil source code dari Etherscan untuk alamat: {token_address}")
        source_code = fetch_source_code_from_etherscan(token_address)

    tmp_file_path = ""

    try:
        with tempfile.NamedTemporaryFile(mode='w', suffix=".sol", delete=False, encoding="utf-8") as tmp_file:
            tmp_file.write(source_code)
            tmp_file_path = tmp_file.name
        logger.info(f"Source code disimpan sementara di: {tmp_file_path}")

        static_report = await static_analyzer.run_analysis(tmp_file_path, solidity_version)
        
        if isinstance(static_report, Exception):
            logger.error(f"Analisis static gagal: {static_report}", exc_info=True)
            raise HTTPException(status_code=500, detail=f"Analisis static gagal: {str(static_report)}")
        logger.info("Analisis statis berhasil.")
        return static_report

    finally:
        if tmp_file_path and os.path.exists(tmp_file_path):
            os.remove(tmp_file_path)
            logger.info(f"File sementara {tmp_file_path} telah dihapus.")

@app.post("/llm-analysis", response_model=llm_analyzer.LLMAnalysisResult, summary="LLM Analysis")
async def llm_analysis(full_input_json: Dict[str, Any] = Body(..., description="Input JSON lengkap untuk analisis LLM.")):
    """
    Endpoint untuk LLM analysis dengan KAG
    1. Ambil prompt
    2. Jalankan analisis LLM
    3. Kembalikan hasil analisis
    """
    logger.info("Memulai analisis LLM dengan KAG...")

    if "contract_metadata" not in full_input_json or "token_address" not in full_input_json["contract_metadata"]:
        raise HTTPException(status_code=400, detail="Input JSON harus berisi 'contract_metadata' dengan 'token_address'.")
    
    llm_report = await llm_analyzer.run_analysis(full_input_json)

    if isinstance(llm_report, Exception):
        logger.error(f"Analisis LLM gagal: {llm_report}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analisis LLM gagal: {str(llm_report)}")
    logger.info("Analisis LLM berhasil.")
    return llm_report

@app.get("/", summary="Health Check")
def read_root():
    return {"status": "Analyzer service is running."}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)