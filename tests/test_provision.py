import uuid

import pytest

from kc_provision import AudienceProvisionSpec
from kc_provision import KeycloakAdminError
from kc_provision import provision_audience


class FakeAdmin:
    """In-memory, stessa interfaccia di KeycloakAdmin usata da provision_audience."""

    def __init__(self, existing_clients=()):
        self.clients = {
            c: {"id": uuid.uuid4().hex, "clientId": c} for c in existing_clients
        }
        self.scopes = {}
        self.mappers = {}
        self.assignments = []
        self.created_clients = []
        self.logged_in = False

    async def login(self):
        self.logged_in = True

    async def get_client(self, cid):
        return self.clients.get(cid)

    async def create_client(self, cid):
        self.clients[cid] = {"id": uuid.uuid4().hex, "clientId": cid}
        self.created_clients.append(cid)
        return self.clients[cid]

    async def client_secret(self, uuid_):
        return f"secret-{uuid_[:6]}"

    async def get_client_scope(self, name):
        return self.scopes.get(name)

    async def create_client_scope(self, name):
        self.scopes[name] = {"id": uuid.uuid4().hex, "name": name}
        self.mappers[self.scopes[name]["id"]] = []
        return self.scopes[name]

    async def ensure_audience_mapper(self, scope_uuid, mapper_name, value):
        existing = self.mappers.setdefault(scope_uuid, [])
        if any(m["name"] == mapper_name for m in existing):
            return False
        existing.append({"name": mapper_name, "value": value})
        return True

    async def assign_default_scope(self, client_uuid, scope_uuid):
        self.assignments.append((client_uuid, scope_uuid))


def _spec(**over):
    base = dict(
        service_client_id="service-scheduler",
        audience_scope_name="service-scheduler-audience",
        audience_value="app-scheduler",
        consumer_client_ids=["nob-app", "nob-workers"],
    )
    base.update(over)
    return AudienceProvisionSpec(**base)


async def test_full_flow_creates_and_assigns_to_all():
    admin = FakeAdmin(existing_clients=["nob-app", "nob-workers"])
    result = await provision_audience(admin, _spec())

    assert admin.logged_in is True
    assert result.created_service is True
    assert result.created_scope is True
    assert result.created_mapper is True
    assert result.service_secret.startswith("secret-")
    assert set(result.assigned_clients) == {
        "service-scheduler",
        "nob-app",
        "nob-workers",
    }
    assert len(admin.assignments) == 3
    assert result.service_account_uid == "service-account-service-scheduler"


async def test_aborts_when_consumer_client_missing():
    admin = FakeAdmin(existing_clients=["nob-app"])  # manca nob-workers
    with pytest.raises(KeycloakAdminError, match="nob-workers"):
        await provision_audience(admin, _spec())


async def test_idempotent_second_run_no_recreate():
    admin = FakeAdmin(existing_clients=["nob-app", "nob-workers"])
    await provision_audience(admin, _spec())
    result2 = await provision_audience(admin, _spec())
    assert result2.created_service is False
    assert result2.created_scope is False
    assert result2.created_mapper is False
    assert admin.created_clients == ["service-scheduler"]
