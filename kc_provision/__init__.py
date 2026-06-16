"""kc_provision — provisioning keycloak agnostico (Admin API + patch .env)."""

from .admin import KeycloakAdmin
from .admin import KeycloakAdminError
from .dotenv_patch import is_configured
from .dotenv_patch import patch_dotenv
from .dotenv_patch import read_dotenv_keys
from .provision import AudienceProvisionSpec
from .provision import ProvisionResult
from .provision import provision_audience

__all__ = [
    "KeycloakAdmin",
    "KeycloakAdminError",
    "AudienceProvisionSpec",
    "ProvisionResult",
    "provision_audience",
    "patch_dotenv",
    "read_dotenv_keys",
    "is_configured",
]
