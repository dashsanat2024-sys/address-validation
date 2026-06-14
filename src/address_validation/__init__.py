"""UK address validation and normalization pipeline."""

from .pipeline import AddressPipeline, PipelineResult
from .schema import StandardAddress

__all__ = ["AddressPipeline", "PipelineResult", "StandardAddress"]
