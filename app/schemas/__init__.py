"""Pydantic v2 API schemas — re-exports."""

from app.schemas.analysis import (
    Alternative,
    AnalysisResult,
    AnalyzeRequest,
    AnalyzeResponse,
    GoodIngredient,
    IngredientIssue,
)
from app.schemas.auth import (
    LogoutRequest,
    LogoutResponse,
    RefreshTokenRequest,
    RefreshTokenResponse,
    SendOTPRequest,
    SendOTPResponse,
    UserResponse,
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.schemas.scan import BarcodeRequest, BarcodeResponse, OCRResponse

__all__ = [
    "Alternative",
    "AnalysisResult",
    "AnalyzeRequest",
    "AnalyzeResponse",
    "BarcodeRequest",
    "BarcodeResponse",
    "GoodIngredient",
    "IngredientIssue",
    "LogoutRequest",
    "LogoutResponse",
    "OCRResponse",
    "RefreshTokenRequest",
    "RefreshTokenResponse",
    "SendOTPRequest",
    "SendOTPResponse",
    "UserResponse",
    "VerifyOTPRequest",
    "VerifyOTPResponse",
]
