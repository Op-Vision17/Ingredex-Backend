"""Pydantic schemas for barcode lookup and OCR results."""

from pydantic import BaseModel, Field, field_validator


class BarcodeRequest(BaseModel):
    """Client request to resolve a product by barcode."""

    barcode: str = Field(
        ...,
        min_length=8,
        max_length=14,
        description="Product barcode (e.g. EAN-13 / UPC), 8–14 characters.",
        examples=["012345678905"],
    )

    @field_validator("barcode", mode="before")
    @classmethod
    def strip_barcode(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value


class BarcodeResponse(BaseModel):
    """Resolved product data for a barcode."""

    product_name: str | None = Field(None, description="Commercial product name, if known.")
    ingredients: str | None = Field(
        None,
        description="Ingredient list text as returned by the upstream source.",
    )
    barcode: str = Field(..., description="Barcode that was resolved.")
    source: str = Field(
        ...,
        description="Identifier for the data source (e.g. API name or cache key).",
    )


class OCRResponse(BaseModel):
    """Result of ingredient extraction from a product label image (Groq Vision)."""

    extracted_text: str = Field(..., description="Ingredients list text extracted from the image.")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score in [0, 1].",
    )
