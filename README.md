# kc-provision

Reusable, service-agnostic **Keycloak provisioning** for any service/project.

Backend: **[python-keycloak](https://github.com/marcospereirampj/python-keycloak)**
(async `a_*` API), not hand-rolled REST. This keeps it easy to extend for
generic users, groups, roles, and clients.

- `KeycloakAdmin`: thin adapter over python-keycloak (`admin-cli` password grant
  login). It exposes the audience flow operations with simple types, plus
  `self.kc`, the raw python-keycloak handle for any other Admin API operation
  (users/groups/clients/roles) in downstream projects.
- `provision_audience(admin, AudienceProvisionSpec)`: idempotent flow that
  creates an **M2M service client** plus an **audience client scope** with
  `oidc-audience-mapper`, then assigns it to the service and the **consumer
  client**.
- `patch_dotenv` / `read_dotenv_keys` / `is_configured`: idempotent `.env` file
  patching helpers (key upsert, preserving the rest of the file).

There is no dependency on the calling service: environment variable names,
defaults, prompts, and wrappers stay in the caller, for example
`services/calendar_scheduler/.../kc_setup.py`.

## Extending Generic Users, Groups, And Clients

Use `admin.kc` (python-keycloak) directly, for example:

```python
from kc_provision import KeycloakAdmin
admin = KeycloakAdmin(server, realm, admin_user=u, admin_password=p)
await admin.login()
await admin.kc.a_create_group({"name": "operatori"})
uid = await admin.kc.a_create_user({"username": "svc", "enabled": True})
```

## Client Users And Groups

Keycloak enables users and groups for a client through **client roles**. The
admin adapter exposes direct helpers for that model:

```python
await admin.add_client_user("nob-app", "mario", "access")
users = await admin.list_client_users("nob-app", "access")
await admin.remove_client_user("nob-app", "mario", "access")

await admin.add_client_group("nob-app", "/operatori", "access")
groups = await admin.list_client_groups("nob-app", "access")
await admin.remove_client_group("nob-app", "/operatori", "access")

await admin.enable_user_in_group("mario", "/operatori")
await admin.disable_user_in_group("mario", "/operatori")
```

Parameter meaning:

- `client_id`: public Keycloak client id, for example `nob-app`, not the internal
  UUID.
- `username`: Keycloak username, for example `mario`, not the internal user UUID.
  The adapter resolves it with `a_get_user_id(username)` before assigning or
  removing client roles.
- `role_name`: Keycloak client role name inside `client_id`, for example
  `access`.
- `group_path`: Keycloak group path, for example `/operatori`. A missing leading
  slash is normalized, so `operatori` and `/operatori` both target the same
  top-level group.

## Why The Audience Scope Goes On Every Consumer

The backend validates any bearer token as a Keycloak JWT. If `aud` validation is
enabled, every client calling it must emit the `aud` claim or it gets a 401
(including user logins). For this reason, the shared scope is assigned to the
service and to every consumer. **Enforcement** (`OZON_TOKEN_AUDIENCE` on the app
side) remains a caller-owned, decoupled choice.

## Tests

```bash
uv run python -m pytest tests/
```
