from __future__ import annotations

import logging
from typing import Any

from keycloak import KeycloakAdmin as _KCAdmin
from keycloak.exceptions import KeycloakError

logger = logging.getLogger("kc_provision")


class KeycloakAdminError(RuntimeError):
    pass


class KeycloakAdmin:
    """Adapter sottile su **python-keycloak** (API async `a_*`).

    Espone solo le operazioni del provisioning audience con tipi semplici
    (dict con `id`/`name`/`clientId`), così `provision_audience` resta agnostico
    dall'implementazione. `self.kc` è l'handle python-keycloak grezzo: usalo per
    estendere la lib (user, group, role, client generici) in altri progetti.
    """

    def __init__(
        self,
        server_url: str,
        realm: str,
        *,
        admin_user: str,
        admin_password: str,
        admin_realm: str = "master",
        verify_tls: bool = True,
        kc: Any | None = None,
    ) -> None:
        self._realm = realm
        # python-keycloak vuole il server_url con trailing slash.
        self.kc = kc or _KCAdmin(
            server_url=server_url.rstrip("/") + "/",
            username=admin_user,
            password=admin_password,
            realm_name=realm,
            user_realm_name=admin_realm,
            client_id="admin-cli",
            verify=verify_tls,
        )

    async def aclose(self) -> None:
        conn = getattr(self.kc, "connection", None)
        aclose = getattr(conn, "aclose", None)
        if aclose is not None:
            await aclose()

    # --- auth -----------------------------------------------------------

    async def login(self) -> None:
        try:
            await self.kc.connection.a_get_token()
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"admin login fallito: {exc} (controlla user/password/realm admin)"
            ) from exc

    # --- clients --------------------------------------------------------

    async def get_client(self, client_id: str) -> dict[str, Any] | None:
        try:
            uuid = await self.kc.a_get_client_id(client_id)
        except KeycloakError as exc:
            raise KeycloakAdminError(str(exc)) from exc
        return {"id": uuid, "clientId": client_id} if uuid else None

    async def create_client(self, client_id: str) -> dict[str, Any]:
        rep = {
            "clientId": client_id,
            "protocol": "openid-connect",
            "enabled": True,
            "publicClient": False,
            "serviceAccountsEnabled": True,
            "standardFlowEnabled": False,
            "directAccessGrantsEnabled": False,
            "implicitFlowEnabled": False,
        }
        try:
            uuid = await self.kc.a_create_client(rep, skip_exists=False)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"create_client '{client_id}' fallito: {exc}"
            ) from exc
        return {"id": uuid, "clientId": client_id}

    async def client_secret(self, client_uuid: str) -> str:
        try:
            data = await self.kc.a_get_client_secrets(client_uuid)
            value = (data or {}).get("value", "")
            if value:
                return value
            data = await self.kc.a_generate_client_secrets(client_uuid)
        except KeycloakError as exc:
            raise KeycloakAdminError(f"client_secret fallito: {exc}") from exc
        return (data or {}).get("value", "")

    async def _require_client(self, client_id: str) -> dict[str, Any]:
        client = await self.get_client(client_id)
        if client is None:
            raise KeycloakAdminError(f"client '{client_id}' non esiste")
        return client

    async def _require_client_role(
        self, client_uuid: str, role_name: str
    ) -> dict[str, Any]:
        try:
            return await self.kc.a_get_client_role(client_uuid, role_name)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"client role '{role_name}' non esiste o non e' leggibile: {exc}"
            ) from exc

    async def _require_user_id(self, username: str) -> str:
        try:
            user_id = await self.kc.a_get_user_id(username)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"user '{username}' non leggibile: {exc}"
            ) from exc
        if not user_id:
            raise KeycloakAdminError(f"user '{username}' non esiste")
        return user_id

    async def _require_group(self, group_path: str) -> dict[str, Any]:
        path = group_path if group_path.startswith("/") else f"/{group_path}"
        try:
            group = await self.kc.a_get_group_by_path(path)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"group '{path}' non esiste o non e' leggibile: {exc}"
            ) from exc
        if not group or not group.get("id"):
            raise KeycloakAdminError(f"group '{path}' non esiste")
        return group

    @staticmethod
    def _page_query(first: int | None, max_: int | None) -> dict[str, int]:
        query: dict[str, int] = {}
        if first is not None:
            query["first"] = first
        if max_ is not None:
            query["max"] = max_
        return query

    # --- client users/groups via client roles --------------------------

    async def list_client_users(
        self,
        client_id: str,
        role_name: str,
        *,
        first: int | None = None,
        max: int | None = None,
    ) -> list[dict[str, Any]]:
        """Ritorna gli user assegnati a `role_name` del client."""
        client = await self._require_client(client_id)
        try:
            return await self.kc.a_get_client_role_members(
                client["id"], role_name, **self._page_query(first, max)
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"list_client_users '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def add_client_user(
        self, client_id: str, username: str, role_name: str
    ) -> None:
        """Abilita uno user al client assegnandogli un client role."""
        client = await self._require_client(client_id)
        role = await self._require_client_role(client["id"], role_name)
        user_id = await self._require_user_id(username)
        try:
            await self.kc.a_assign_client_role(user_id, client["id"], [role])
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"add_client_user '{username}' -> '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def remove_client_user(
        self, client_id: str, username: str, role_name: str
    ) -> None:
        """Disabilita uno user dal client rimuovendo il client role."""
        client = await self._require_client(client_id)
        role = await self._require_client_role(client["id"], role_name)
        user_id = await self._require_user_id(username)
        try:
            await self.kc.a_delete_client_roles_of_user(
                user_id, client["id"], [role]
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"remove_client_user '{username}' -> '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def list_client_groups(
        self,
        client_id: str,
        role_name: str,
        *,
        first: int | None = None,
        max: int | None = None,
    ) -> list[dict[str, Any]]:
        """Ritorna i gruppi assegnati a `role_name` del client."""
        client = await self._require_client(client_id)
        try:
            return await self.kc.a_get_client_role_groups(
                client["id"], role_name, **self._page_query(first, max)
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"list_client_groups '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def add_client_group(
        self, client_id: str, group_path: str, role_name: str
    ) -> None:
        """Abilita un gruppo al client assegnandogli un client role."""
        client = await self._require_client(client_id)
        role = await self._require_client_role(client["id"], role_name)
        group = await self._require_group(group_path)
        try:
            await self.kc.a_assign_group_client_roles(
                group["id"], client["id"], [role]
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"add_client_group '{group_path}' -> '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def remove_client_group(
        self, client_id: str, group_path: str, role_name: str
    ) -> None:
        """Disabilita un gruppo dal client rimuovendo il client role."""
        client = await self._require_client(client_id)
        role = await self._require_client_role(client["id"], role_name)
        group = await self._require_group(group_path)
        try:
            await self.kc.a_delete_group_client_roles(
                group["id"], client["id"], [role]
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"remove_client_group '{group_path}' -> '{client_id}/{role_name}' fallito: {exc}"
            ) from exc

    async def enable_user_in_group(
        self, username: str, group_path: str
    ) -> None:
        """Abilita uno user nel gruppo aggiungendo la membership."""
        user_id = await self._require_user_id(username)
        group = await self._require_group(group_path)
        try:
            await self.kc.a_group_user_add(user_id, group["id"])
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"enable_user_in_group '{username}' -> '{group_path}' fallito: {exc}"
            ) from exc

    async def disable_user_in_group(
        self, username: str, group_path: str
    ) -> None:
        """Disabilita uno user nel gruppo rimuovendo la membership."""
        user_id = await self._require_user_id(username)
        group = await self._require_group(group_path)
        try:
            await self.kc.a_group_user_remove(user_id, group["id"])
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"disable_user_in_group '{username}' -> '{group_path}' fallito: {exc}"
            ) from exc

    # --- client scopes --------------------------------------------------

    async def get_client_scope(self, name: str) -> dict[str, Any] | None:
        try:
            scopes = await self.kc.a_get_client_scopes()
        except KeycloakError as exc:
            raise KeycloakAdminError(str(exc)) from exc
        for scope in scopes or []:
            if scope.get("name") == name:
                return scope
        return None

    async def create_client_scope(self, name: str) -> dict[str, Any]:
        rep = {
            "name": name,
            "protocol": "openid-connect",
            "attributes": {
                "include.in.token.scope": "true",
                "display.on.consent.screen": "false",
            },
        }
        try:
            uuid = await self.kc.a_create_client_scope(rep, skip_exists=False)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"create_client_scope '{name}' fallito: {exc}"
            ) from exc
        return {"id": uuid, "name": name}

    async def list_scope_mappers(
        self, scope_uuid: str
    ) -> list[dict[str, Any]]:
        try:
            return await self.kc.a_get_mappers_from_client_scope(scope_uuid)
        except KeycloakError as exc:
            raise KeycloakAdminError(str(exc)) from exc

    async def ensure_audience_mapper(
        self, scope_uuid: str, mapper_name: str, audience_value: str
    ) -> bool:
        """Crea il mapper audience se assente. Ritorna True se creato."""
        for mapper in await self.list_scope_mappers(scope_uuid):
            if mapper.get("name") == mapper_name:
                return False
        rep = {
            "name": mapper_name,
            "protocol": "openid-connect",
            "protocolMapper": "oidc-audience-mapper",
            "config": {
                "included.custom.audience": audience_value,
                "id.token.claim": "false",
                "access.token.claim": "true",
            },
        }
        try:
            await self.kc.a_add_mapper_to_client_scope(scope_uuid, rep)
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"create audience mapper fallito: {exc}"
            ) from exc
        return True

    async def assign_default_scope(
        self, client_uuid: str, scope_uuid: str
    ) -> None:
        payload = {
            "realm": self._realm,
            "client": client_uuid,
            "clientScopeId": scope_uuid,
        }
        try:
            await self.kc.a_add_client_default_client_scope(
                client_uuid, scope_uuid, payload
            )
        except KeycloakError as exc:
            raise KeycloakAdminError(
                f"assign_default_scope fallito: {exc}"
            ) from exc
