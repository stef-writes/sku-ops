"""Organization (tenant) model."""

from shared.kernel.entity import Entity


class Organization(Entity):
    """Organization (tenant) - one per supply yard / business unit."""

    name: str
    slug: str
