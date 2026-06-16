import pytest
from keycloak.exceptions import KeycloakAuthenticationError

from kc_provision import KeycloakAdmin
from kc_provision import KeycloakAdminError


class FakeConnection:
    def __init__(self, token_error=False):
        self.token_error = token_error

    async def a_get_token(self):
        if self.token_error:
            raise KeycloakAuthenticationError("bad creds")
        return {"access_token": "t"}

    async def aclose(self):
        pass


class FakeKC:
    """Handle python-keycloak finto: solo i metodi a_* usati dall'adapter."""

    def __init__(self, clients=None, token_error=False):
        self.connection = FakeConnection(token_error=token_error)
        self._clients = dict(clients or {})  # clientId -> uuid
        self._secrets = {}  # uuid -> secret
        self._scopes = {}  # name -> uuid
        self._mappers = {}  # scope_uuid -> [mapper]
        self._roles = {}
        self._users = {}
        self._groups = {}
        self._user_client_roles = {}
        self._group_client_roles = {}
        self._group_memberships = set()
        self.created_clients = []
        self.assignments = []

        for client_uuid in self._clients.values():
            self.add_role(client_uuid, "access")

    def add_user(self, username):
        user = {"id": f"user-{username}", "username": username, "enabled": True}
        self._users[username] = user
        return user

    def add_group(self, path):
        group_path = path if path.startswith("/") else f"/{path}"
        group = {"id": f"group-{group_path.strip('/')}", "path": group_path}
        self._groups[group_path] = group
        return group

    def add_role(self, client_uuid, role_name):
        role = {
            "id": f"role-{client_uuid}-{role_name}",
            "name": role_name,
            "clientRole": True,
        }
        self._roles[(client_uuid, role_name)] = role
        return role

    async def a_get_client_id(self, client_id):
        return self._clients.get(client_id)

    async def a_create_client(self, payload, skip_exists=False):
        cid = payload["clientId"]
        uuid = f"uuid-{cid}"
        self._clients[cid] = uuid
        self.add_role(uuid, "access")
        self.created_clients.append(cid)
        return uuid

    async def a_get_client_secrets(self, client_uuid):
        return {"value": self._secrets.get(client_uuid, "")}

    async def a_generate_client_secrets(self, client_uuid):
        self._secrets[client_uuid] = "gen-secret"
        return {"value": "gen-secret"}

    async def a_get_client_scopes(self):
        return [{"id": v, "name": k} for k, v in self._scopes.items()]

    async def a_create_client_scope(self, payload, skip_exists=False):
        name = payload["name"]
        uuid = f"scope-{name}"
        self._scopes[name] = uuid
        self._mappers[uuid] = []
        return uuid

    async def a_get_mappers_from_client_scope(self, scope_uuid):
        return self._mappers.get(scope_uuid, [])

    async def a_add_mapper_to_client_scope(self, scope_uuid, payload):
        self._mappers.setdefault(scope_uuid, []).append(payload)
        return b""

    async def a_add_client_default_client_scope(
        self, client_uuid, scope_uuid, payload
    ):
        self.assignments.append((client_uuid, scope_uuid))
        return {}

    async def a_get_client_role(self, client_uuid, role_name):
        return self._roles[(client_uuid, role_name)]

    async def a_get_client_role_members(self, client_uuid, role_name, **query):
        role = self._roles[(client_uuid, role_name)]
        users = []
        for (user_id, assigned_client_uuid), roles in self._user_client_roles.items():
            if assigned_client_uuid != client_uuid:
                continue
            if role["id"] not in {r["id"] for r in roles}:
                continue
            users.extend(u for u in self._users.values() if u["id"] == user_id)
        return users

    async def a_assign_client_role(self, user_id, client_uuid, roles):
        key = (user_id, client_uuid)
        assigned = self._user_client_roles.setdefault(key, [])
        for role in roles:
            if role["id"] not in {r["id"] for r in assigned}:
                assigned.append(role)
        return {}

    async def a_delete_client_roles_of_user(self, user_id, client_uuid, roles):
        key = (user_id, client_uuid)
        remove_ids = {r["id"] for r in roles}
        self._user_client_roles[key] = [
            role
            for role in self._user_client_roles.get(key, [])
            if role["id"] not in remove_ids
        ]
        return {}

    async def a_get_client_role_groups(self, client_uuid, role_name, **query):
        role = self._roles[(client_uuid, role_name)]
        groups = []
        for (group_id, assigned_client_uuid), roles in self._group_client_roles.items():
            if assigned_client_uuid != client_uuid:
                continue
            if role["id"] not in {r["id"] for r in roles}:
                continue
            groups.extend(g for g in self._groups.values() if g["id"] == group_id)
        return groups

    async def a_assign_group_client_roles(self, group_id, client_uuid, roles):
        key = (group_id, client_uuid)
        assigned = self._group_client_roles.setdefault(key, [])
        for role in roles:
            if role["id"] not in {r["id"] for r in assigned}:
                assigned.append(role)
        return {}

    async def a_delete_group_client_roles(self, group_id, client_uuid, roles):
        key = (group_id, client_uuid)
        remove_ids = {r["id"] for r in roles}
        self._group_client_roles[key] = [
            role
            for role in self._group_client_roles.get(key, [])
            if role["id"] not in remove_ids
        ]
        return {}

    async def a_get_user_id(self, username):
        user = self._users.get(username)
        return user["id"] if user else None

    async def a_get_group_by_path(self, group_path):
        return self._groups[group_path]

    async def a_group_user_add(self, user_id, group_id):
        self._group_memberships.add((user_id, group_id))
        return {}

    async def a_group_user_remove(self, user_id, group_id):
        self._group_memberships.discard((user_id, group_id))
        return {}


def _admin(fake):
    return KeycloakAdmin(
        "https://kc",
        "demo",
        admin_user="admin",
        admin_password="pw",
        kc=fake,
    )


async def test_login_failure_raises_wrapped():
    admin = _admin(FakeKC(token_error=True))
    with pytest.raises(KeycloakAdminError, match="admin login"):
        await admin.login()


async def test_get_client_maps_uuid():
    admin = _admin(FakeKC(clients={"nob-app": "uuid-nob"}))
    assert await admin.get_client("missing") is None
    rep = await admin.get_client("nob-app")
    assert rep == {"id": "uuid-nob", "clientId": "nob-app"}


async def test_create_client_and_generate_secret():
    fake = FakeKC()
    admin = _admin(fake)
    created = await admin.create_client("service-scheduler")
    assert created["id"] == "uuid-service-scheduler"
    assert "service-scheduler" in fake.created_clients
    # secret assente -> generato
    assert await admin.client_secret(created["id"]) == "gen-secret"


async def test_scope_and_audience_mapper_idempotent():
    fake = FakeKC()
    admin = _admin(fake)
    assert await admin.get_client_scope("aud") is None
    scope = await admin.create_client_scope("aud")
    assert await admin.ensure_audience_mapper(
        scope["id"], "audience-app-scheduler", "app-scheduler"
    ) is True
    assert await admin.ensure_audience_mapper(
        scope["id"], "audience-app-scheduler", "app-scheduler"
    ) is False
    mappers = await admin.list_scope_mappers(scope["id"])
    assert mappers[0]["config"]["included.custom.audience"] == "app-scheduler"
    assert mappers[0]["config"]["access.token.claim"] == "true"


async def test_assign_default_scope():
    fake = FakeKC(clients={"nob-app": "uuid-nob"})
    admin = _admin(fake)
    await admin.assign_default_scope("uuid-nob", "scope-aud")
    assert ("uuid-nob", "scope-aud") in fake.assignments


async def test_client_users_can_be_listed_added_and_removed():
    fake = FakeKC(clients={"nob-app": "uuid-nob"})
    fake.add_user("mario")
    admin = _admin(fake)

    assert await admin.list_client_users("nob-app", "access") == []
    await admin.add_client_user("nob-app", "mario", "access")

    users = await admin.list_client_users("nob-app", "access")
    assert users == [{"id": "user-mario", "username": "mario", "enabled": True}]

    await admin.remove_client_user("nob-app", "mario", "access")
    assert await admin.list_client_users("nob-app", "access") == []


async def test_client_groups_can_be_listed_added_and_removed():
    fake = FakeKC(clients={"nob-app": "uuid-nob"})
    fake.add_group("/operatori")
    admin = _admin(fake)

    assert await admin.list_client_groups("nob-app", "access") == []
    await admin.add_client_group("nob-app", "/operatori", "access")

    groups = await admin.list_client_groups("nob-app", "access")
    assert groups == [{"id": "group-operatori", "path": "/operatori"}]

    await admin.remove_client_group("nob-app", "operatori", "access")
    assert await admin.list_client_groups("nob-app", "access") == []


async def test_user_can_be_enabled_and_disabled_in_group():
    fake = FakeKC()
    user = fake.add_user("mario")
    group = fake.add_group("/operatori")
    admin = _admin(fake)

    await admin.enable_user_in_group("mario", "/operatori")
    assert (user["id"], group["id"]) in fake._group_memberships

    await admin.disable_user_in_group("mario", "operatori")
    assert (user["id"], group["id"]) not in fake._group_memberships
