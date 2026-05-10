"""Resume parsing service - extracts text from files and calls ResumeAgent."""

import logging
import uuid
from pathlib import Path

from pypdf import PdfReader
from docx import Document as DocxDocument

from app.agents.resume_agent import ResumeAgent
from app.core.config import settings
from app.core.exceptions import ValidationErrorException

logger = logging.getLogger(__name__)

# Supported file extensions
SUPPORTED_EXTENSIONS = {".pdf", ".docx"}


async def parse_resume(file_bytes: bytes, filename: str, position: str) -> tuple[dict, str]:
    """Parse a resume file: extract text, analyze with LLM, return parsed data and file path.

    Returns:
        Tuple of (parsed_data_dict, saved_file_path)
    """
    # Validate file extension
    ext = Path(filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise ValidationErrorException(
            f"不支持的文件格式: {ext}，支持: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    # Extract text from file
    resume_text = await _extract_text(file_bytes, ext)

    # Call resume agent for analysis
    agent = ResumeAgent()
    parsed_data = await agent.analyze(resume_text, position)

    # Save file to disk
    saved_path = await _save_file(file_bytes, ext)

    return parsed_data, saved_path


async def _extract_text(file_bytes: bytes, ext: str) -> str:
    """Extract text content from a resume file."""
    try:
        if ext == ".pdf":
            import io
            reader = PdfReader(io.BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
            return text.strip() or "（PDF内容提取为空）"

        elif ext == ".docx":
            import io
            try:
                doc = DocxDocument(io.BytesIO(file_bytes))
                text = "\n".join(p.text for p in doc.paragraphs)
            except Exception as e:
                # Some docx files have broken image/media references.
                # Fallback: parse as ZIP and extract document.xml text directly.
                logger.warning(f"python-docx 解析失败，尝试直接提取XML: {e}")
                import zipfile
                from xml.etree import ElementTree
                with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
                    xml_bytes = zf.read("word/document.xml")
                root = ElementTree.fromstring(xml_bytes)
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                paragraphs = root.findall(".//w:p", ns)
                lines = []
                for p in paragraphs:
                    texts = p.findall(".//w:t", ns)
                    line = "".join(t.text or "" for t in texts)
                    lines.append(line)
                text = "\n".join(lines)
            return text.strip() or "（DOCX内容提取为空）"

        else:
            raise ValidationErrorException(f"不支持的文件格式: {ext}")

    except Exception as e:
        logger.error(f"文本提取失败: {e}", exc_info=True)
        raise ValidationErrorException(f"无法从文件中提取文本: {str(e)}")


async def _save_file(file_bytes: bytes, ext: str) -> str:
    """Save uploaded file to disk."""
    upload_dir = Path(settings.UPLOAD_DIR) / "resumes"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = upload_dir / filename
    filepath.write_bytes(file_bytes)

    logger.info(f"文件已保存: {filepath}")
    return str(filepath)
