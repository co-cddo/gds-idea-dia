"""Output writers — decouple pipeline orchestration from output destination."""

from dia.writers.local import LocalOutputWriter
from dia.writers.memory import InMemoryWriter
from dia.writers.protocol import OutputWriter
from dia.writers.s3 import S3OutputWriter

__all__ = ["InMemoryWriter", "LocalOutputWriter", "OutputWriter", "S3OutputWriter"]
