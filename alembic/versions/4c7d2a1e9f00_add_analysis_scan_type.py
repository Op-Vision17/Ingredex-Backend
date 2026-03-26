"""Allow scan_type 'analysis' on product_scans.

Revision ID: 4c7d2a1e9f00
Revises: 3b52bbe89d67
Create Date: 2026-03-22

"""

from typing import Sequence, Union

from alembic import op

revision: str = "4c7d2a1e9f00"
down_revision: Union[str, None] = "3b52bbe89d67"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("ck_product_scans_scan_type", "product_scans", type_="check")
    op.create_check_constraint(
        "ck_product_scans_scan_type",
        "product_scans",
        "scan_type IN ('barcode', 'ocr', 'analysis')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_product_scans_scan_type", "product_scans", type_="check")
    op.create_check_constraint(
        "ck_product_scans_scan_type",
        "product_scans",
        "scan_type IN ('barcode', 'ocr')",
    )
