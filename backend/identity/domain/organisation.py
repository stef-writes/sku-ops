"""Organization (tenant) model."""
from kernel.entity import Entity


class Organization(Entity):
    """Organization (tenant) - one per supply yard / business unit."""
    name: str
    slug: str
