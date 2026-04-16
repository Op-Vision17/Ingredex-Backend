"""Scan DAO — database queries for scan feature.

The scan feature is stateless (barcode lookups use cache, not DB), so this
module is intentionally minimal. It exists as a placeholder so the feature
follows the standard router → handler → service → dao pattern.
"""
