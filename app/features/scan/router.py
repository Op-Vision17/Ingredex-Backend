"""Scan router — endpoint declarations for barcode and OCR."""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile

from app.features.scan.handler import handle_barcode, handle_ocr
from app.features.scan.schemas import BarcodeRequest, BarcodeResponse, OCRResponse

router = APIRouter()


@router.post("/barcode", response_model=BarcodeResponse)
async def scan_barcode(body: BarcodeRequest) -> BarcodeResponse:
    """Look up product data by barcode (Open Food Facts + Redis cache)."""
    return await handle_barcode(body)


@router.post("/ocr", response_model=OCRResponse)
async def scan_ocr(
    file: Annotated[UploadFile, File(..., description="Label image (JPEG, PNG, or WebP)")],
) -> OCRResponse:
    """Extract ingredients text from a product label image using Groq Vision."""
    return await handle_ocr(file)
