from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field

from .admin import KeycloakAdmin
from .admin import KeycloakAdminError


@dataclass
class AudienceProvisionSpec:
    """Cosa provisionare. Agnostico rispetto al servizio chiamante."""

    service_client_id: str
    audience_scope_name: str
    audience_value: str
    consumer_client_ids: list[str]


@dataclass
class ProvisionResult:
    service_client_id: str
    service_secret: str
    audience_value: str
    audience_scope_name: str
    assigned_clients: list[str] = field(default_factory=list)
    created_service: bool = False
    created_scope: bool = False
    created_mapper: bool = False

    @property
    def service_account_uid(self) -> str:
        return f"service-account-{self.service_client_id}"


async def provision_audience(
    admin: KeycloakAdmin, spec: AudienceProvisionSpec
) -> ProvisionResult:
    """Flusso idempotente: service client M2M + client-scope audience + mapper,
    assegnato a service + consumer. Nessuna IO/prompt (testabile).

    Perche' un audience scope condiviso assegnato a TUTTI i consumer: l'app
    verifica QUALSIASI bearer, quindi ogni client che la chiama deve emettere
    l'`aud` o andra' in 401 quando la verifica e' attiva.
    """
    await admin.login()

    # 1. i consumer client devono preesistere
    consumers = []
    for cid in spec.consumer_client_ids:
        rep = await admin.get_client(cid)
        if not rep:
            raise KeycloakAdminError(
                f"consumer client '{cid}' non esiste nel realm: i client che "
                "chiamano il backend devono preesistere"
            )
        consumers.append((cid, rep))

    # 2. service client (crea se assente) + secret
    service = await admin.get_client(spec.service_client_id)
    created_service = False
    if not service:
        service = await admin.create_client(spec.service_client_id)
        created_service = True
    secret = await admin.client_secret(service["id"])

    # 3. client scope audience condiviso + mapper
    scope = await admin.get_client_scope(spec.audience_scope_name)
    created_scope = False
    if not scope:
        scope = await admin.create_client_scope(spec.audience_scope_name)
        created_scope = True
    mapper_name = f"audience-{spec.audience_value}"
    created_mapper = await admin.ensure_audience_mapper(
        scope["id"], mapper_name, spec.audience_value
    )

    # 4. assegna lo scope (default) a service + tutti i consumer
    assigned: list[str] = []
    for cid, rep in [(spec.service_client_id, service)] + consumers:
        await admin.assign_default_scope(rep["id"], scope["id"])
        assigned.append(cid)

    return ProvisionResult(
        service_client_id=spec.service_client_id,
        service_secret=secret,
        audience_value=spec.audience_value,
        audience_scope_name=spec.audience_scope_name,
        assigned_clients=assigned,
        created_service=created_service,
        created_scope=created_scope,
        created_mapper=created_mapper,
    )
