"""Factory for Xero gateway. Returns real adapter when connected, stub otherwise."""
from identity.domain.org_settings import OrgSettings
from adapters.stub_xero import StubXeroAdapter


def get_xero_gateway(settings: OrgSettings):
    """Return XeroAdapter if org has active Xero tokens, otherwise StubXeroAdapter."""
    if settings.xero_access_token and settings.xero_tenant_id:
        try:
            from adapters.xero_adapter import XeroAdapter
            return XeroAdapter()
        except ImportError:
            pass
    return StubXeroAdapter()
