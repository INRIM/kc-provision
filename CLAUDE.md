# CLAUDE.md

Guidance for Claude Code agents working in this repository.

## Project

`kc-provision` is a service-agnostic Keycloak provisioning library. It must not
own caller-specific config, prompts, environment variable names, or defaults.
Calling services wire IO and service defaults around these pure operations.

Requires Python `>=3.14,<4.0`. Dependency management uses `uv`.

## Commands

```bash
uv sync
uv run python -m pytest tests/
uv run python -m pytest tests/test_provision.py::<name>
```

`asyncio_mode = "auto"` is configured in `pyproject.toml`, so async tests do not
need an explicit `@pytest.mark.asyncio`.

## Architecture

- `kc_provision/admin.py`: thin async adapter over `python-keycloak`. It wraps
  `KeycloakError` as `KeycloakAdminError` and returns simple plain dictionaries
  for library-level operations.
- `kc_provision/provision.py`: idempotent audience provisioning flow. It creates
  or reuses the M2M service client, shared audience client scope, audience mapper,
  and assigns the scope to the service plus every consumer client.
- `kc_provision/dotenv_patch.py`: idempotent `.env` patch helpers preserving
  unrelated content.
- `kc_provision/__init__.py`: public exports only.

Keep the package independent from any calling service. Do not introduce service
names, env-var names, prompts, or caller defaults here.

## Keycloak Rules

The shared audience scope must be assigned to every consumer client, not only to
the service client. Backends validate any bearer token as a Keycloak JWT; with
`aud` validation enabled, each caller must emit the audience or it gets a 401.

Users and groups are enabled for a client through client roles:

```python
await admin.add_client_user(client_id, username, role_name)
await admin.remove_client_user(client_id, username, role_name)
await admin.list_client_users(client_id, role_name)

await admin.add_client_group(client_id, group_path, role_name)
await admin.remove_client_group(client_id, group_path, role_name)
await admin.list_client_groups(client_id, role_name)

await admin.enable_user_in_group(username, group_path)
await admin.disable_user_in_group(username, group_path)
```

Parameter meaning:

- `client_id`: public Keycloak client id, not the internal UUID.
- `username`: Keycloak username, not the internal user UUID. The adapter resolves
  it through `a_get_user_id(username)`.
- `role_name`: client role name inside `client_id`.
- `group_path`: Keycloak group path. Missing leading slash is normalized.

## Testing

Run the full test suite after changes:

```bash
uv run python -m pytest tests/
```

Tests use in-memory fakes instead of a live Keycloak. New `KeycloakAdmin` methods
must be covered in `tests/test_admin.py`; new flow behavior should be covered in
`tests/test_provision.py`.

## Engineering Constraints

- Use existing async `python-keycloak` methods; do not hand-roll REST calls when
  the library exposes the operation.
- Keep changes scoped and avoid caller-specific behavior.
- Do not add monkey patches or workaround-style code.
- Do not commit or document secrets.
- Prefer small adapter methods and tests over broad rewrites.
