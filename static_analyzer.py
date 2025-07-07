import asyncio
import json
import logging
import docker
from docker.errors import ContainerError, ImageNotFound
from typing import List, Tuple

from config import settings
from models import StaticIssue, StaticAnalysisOutput

"""
Konfigurasi logging untuk mengambil nama argumen dan mengembalikan instance logger
"""
logger = logging.getLogger(__name__)

def get_docker_client():
    """
    Instance Docker client
    """
    try:
        return docker.from_env()
    except Exception as e:
        logger.error(f"Gagal terhubung ke Docker daemon: {e}")
        raise

def run_tool_in_docker(
        client: docker.client.DockerClient,
        image_name: str,
        project_path: str,
        command: List[str],
        timeout: int
    ) -> Tuple[str, str]:
    """
    Menjalankan sebuah tool di dalam container Docker dan mengembalikan output.
    
    :param client: Docker client instance.
    :param image_name: Nama image Docker yang akan digunakan.
    :param project_path: Path ke direktori proyek di host untuk di-mount.
    :param command: Perintah yang akan dijalankan di dalam container.
    :param timeout: Batas waktu eksekusi dalam detik.
    :return: Tuple berisi (stdout, stderr).
    """
    try:
        logger.info(f"Menjalankan container dari image: {image_name}")
        container = client.containers.run(
            image=image_name,
            command=command,
            volumes={project_path: {'bind': '/src', 'mode': 'ro'}},
            working_dir='/src',
            detach=True,
        )

        result = container.wait(timeout=timeout)
        stdout = container.logs(stdout=True, stderr=False).decode("utf-8","ignore")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8","ignore")

        container.remove(force=True)

        if result['StatusCode'] != 0:
            logger.warning(f"Container {image_name} selesai dengan status code non-zero: {result['StatusCode']}")
        
        return stdout, stderr
    
    except ContainerError as e:
        logger.error(f"Error di dalam container {image_name}: {e}")
        return "", str(e)
    except ImageNotFound:
        error_msg = f"Image Docker tidak ditemukan: {image_name}. Pastikan image sudah di-build atau di-pull."
        logger.error(error_msg)
        return "", error_msg
    except Exception as e:
        logger.error(f"Terjadi error tak terduga saat menjalankan container {image_name}: {e}")
        if "container" in locals() and container:
            container.remove(force=True)
        return "", str(e)

def parse_slither_output(stdout: str, stderr: str) -> StaticAnalysisOutput:
    """
    Parsing output dari Slither.
    """
    try:
        data = json.loads(stdout)
        if not data.get("success"):
            error_details = data.get("error", "Unknown Slither error")
            return StaticAnalysisOutput(tool_name="Slither", error=f"{error_details}. STDERR: {stderr}")
        
        issues = [
            StaticIssue(
                check=d.get("check", "N/A"),
                severity=d.get("impact", "Unknown").capitalize(),
                line=d.get("elements", [{}])[0].get("source_mapping", {}).get("lines", [-1])[0],
                message=d.get("description", "").strip()
            ) for d in data.get("results", {}).get("detectors", [])
        ]
        logger.info(f"Slither selesai, menemukan {len(issues)} isu.")
        return StaticAnalysisOutput(tool_name="Slither", issues=issues)
    except json.JSONDecodeError:
        return StaticAnalysisOutput(tool_name="Slither", error=f"Gagal mem-parsing output JSON. STDERR: {stderr}")

def parse_mythril_output(stdout: str, stderr: str) -> StaticAnalysisOutput:
    """
    Parsing output dari Mythril.
    """
    try:
        data = json.loads(stdout)
        if not data.get("success"):
            return StaticAnalysisOutput(tool_name="Mythril", error=f"Mythril melaporkan kegagalan. STDERR: {stderr}")
        
        issues = [
            StaticIssue(
                check=i.get("swc-id", i.get("title", "Mythril Issue").replace(" ", "-").lower()),
                severity=i.get("severity", "Unknown").capitalize(),
                line=i.get("lineno", -1),
                message=i.get("description", "").strip()
            ) for i in data.get("issues", [])
        ]
        logger.info(f"Mythril selesai, menemukan {len(issues)} isu.")
        return StaticAnalysisOutput(tool_name="Mythril", issues=issues)
    except json.JSONDecodeError:
        return StaticAnalysisOutput(tool_name="Mythril", error=f"Gagal mem-parsing output JSON. STDERR: {stderr}")