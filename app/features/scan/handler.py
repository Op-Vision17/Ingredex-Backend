"""Scan handler — request handling for barcode and OCR endpoints."""

from typing import Annotated

from fastapi import File, HTTPException, UploadFile, status

from app.features.scan.schemas import BarcodeRequest, BarcodeResponse, OCRResponse
from app.features.scan.service import lookup_barcode
from app.shared.services.ocr_service import extract_text_from_image
from app.utils.logger import logger

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = frozenset(
    {
        "image/jpeg",
        "image/jpg",
        "image/png",
        "image/webp",
    }
)
_ALLOWED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png", ".webp"})


async def handle_barcode(body: BarcodeRequest) -> BarcodeResponse:
    """Look up product data by barcode (Open Food Facts + Redis cache)."""
    barcode = body.barcode
    logger.info("POST /scan/barcode barcode={}", barcode)
    result = await lookup_barcode(barcode)
    return BarcodeResponse.model_validate(result)


async def handle_ocr(
    file: Annotated[UploadFile, File(..., description="Label image (JPEG, PNG, or WebP)")],
) -> OCRResponse:
    """Extract ingredients text from a product label image using Groq Vision."""
    filename = file.filename or "upload"
    suffix = ""
    if "." in filename:
        suffix = "." + filename.rsplit(".", 1)[-1].lower()

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    ct_ok = content_type in _ALLOWED_CONTENT_TYPES if content_type else False
    ext_ok = suffix in _ALLOWED_EXTENSIONS if suffix else False
    if not ct_ok and not ext_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Use .jpg, .jpeg, .png, or .webp with a valid image content type.",
        )

    data = await file.read()
    size = len(data)
    logger.info(
        "POST /scan/ocr filename={} content_type={} size_bytes={}",
        filename,
        content_type,
        size,
    )

    if size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file upload",
        )
    if size > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large (max {_MAX_UPLOAD_BYTES // (1024 * 1024)} MB)",
        )

    result = await extract_text_from_image(data)

    if not result.get("found"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No ingredients list found in image. Please take a clearer photo of the ingredients section.",
        )

    ocr = OCRResponse(
        extracted_text=result["extracted_text"],
        confidence=result["confidence"],
    )
    logger.info(
        "POST /scan/ocr success confidence={} text_len={}",
        ocr.confidence,
        len(ocr.extracted_text),
    )
    return ocr
