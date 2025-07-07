# File untuk mendefinisikan model Pydantic untuk validasi dan struktur

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

# Model Input Request

class ContractMetadataInput(BaseModel):
    """
    Metadata smart contract dalam request body
    """
    token_address: str = Field(..., description="Alamat token kontrak di blockchain.")
    solidity_version: Optional[str] = Field(None, description="Versi Solidity yang digunakan dalam kontrak, jika diketahui.") # atau kalau tidak set default 0.8.24

class ASTInput(BaseModel):
    """
    Model AST dalam request body
    """
    absolutePath: Optional[str] = Field(None, description="Path absolut dari file kontrak, jika tersedia.")
    nodes: List[Dict[str, Any]] = Field(..., description="Daftar node AST yang merepresentasikan struktur kontrak.") # atau langsung bisa nodes: List[Any]

class ContractInput(BaseModel):
    """
    Model input utama untuk request body
    FastAPI validasi otomatis
    """
    contract_metadata: ContractMetadataInput = Field(..., description="Metadata tentang kontrak yang dianalisis.")
    ast: ASTInput = Field(..., description="AST dari kontrak yang dianalisis.")

    # Di buat Dict untuk antisipasi multi-file
    sources: Optional[Dict[str, Dict[str, Any]]] = None
    source_code: Optional[str] = Field(None, description="Source code dari kontrak, jika tersedia.")

# Model Output Response

class AnalysisMetadata(BaseModel):
    """
    Metadata smart contract yang dianalisis dalam response
    """
    file_path: Optional[str] = Field(None, description="Path file utama dari kontrak yang dianalisis.")
    token_address: str = Field(..., description="Alamat token kontrak di blockchain.")

class StaticIssue(BaseModel):
    """
    Model untuk issue yang ditemukan oleh analisis statis
    """
    check: str = Field(..., description="Jenis kerentanan yang terdeteksi.")
    severity: str = Field(..., description="Tingkat keparahan kerentanan (high, medium, low).")
    line: int = Field(..., description="Baris kode tempat kerentanan ditemukan.")
    message: str = Field(..., description="Deskripsi kerentanan yang ditemukan.")

class StaticAnalysisOutput(BaseModel):
    """
    Model output akhir dari analisis statis
    """
    tool_name: str = Field(..., description="Nama alat analisis statis yang digunakan (Slither, Mythril).")
    issues: List[StaticIssue] = Field(..., description="Daftar isu yang ditemukan oleh alat analisis statis.")
    error: Optional[str] = Field(None, description="Pesan error jika terjadi kesalahan selama analisis statis.")

class LLMIssue(BaseModel):
    """
    Model untuk issue yang ditemukan oleh analisis LLM
    """
    severity: str = Field(..., description="Tingkat keparahan kerentanan (high, medium, low).")
    category: str = Field(..., description="Kategori kerentanan yang terdeteksi.")
    description: str = Field(..., description="Deskripsi kerentanan yang ditemukan.")
    confidence: float = Field(..., description="Tingkat kepercayaan LLM terhadap deteksi ini (0-1).")

class LLMAnalysisResult(BaseModel):
    """
    Model output akhir dari analisis LLM
    """
    executive_summary: Optional[str] = Field(None, description="Ringkasan eksekutif dari analisis LLM.")
    overall_risk: Optional[str] = Field(None, description="Penilaian risiko keseluruhan dari kontrak.")
    findings: List[LLMIssue] = Field(..., description="Daftar isu yang ditemukan oleh LLM.")
    error: Optional[str] = Field(None, description="Pesan error jika terjadi kesalahan selama analisis LLM.")

class FinalResponse(BaseModel):
    """
    Model Output kombinasi dari analisis statis dan LLM
    """
    metadata: AnalysisMetadata = Field(..., description="Informasi sumber tentang kontrak yang dianalisis.")
    static_analysis_report: StaticAnalysisOutput = Field(..., description="Hasil dari analisis statis menggunakan Slither dan Mythril.")
    llm_contextual_report: LLMAnalysisResult = Field(..., description="Hasil dari analisis kontekstual oleh LLM dengan Knowledge-Augmented Generation (KAG).")