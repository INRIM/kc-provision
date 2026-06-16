# kc-provision

Provisioning **keycloak agnostico**, riusabile da qualsiasi servizio/progetto.

Backend: **[python-keycloak](https://github.com/marcospereirampj/python-keycloak)**
(API async `a_*`), non REST hand-rolled — così è facile estenderlo a user, group,
role e client generici.

- `KeycloakAdmin` — adapter sottile su python-keycloak (login `admin-cli` password
  grant). Espone le operazioni del flusso audience con tipi semplici **e**
  `self.kc`, l'handle python-keycloak grezzo per qualsiasi altra operazione
  Admin API (user/group/client/role) negli altri progetti.
- `provision_audience(admin, AudienceProvisionSpec)` — flusso idempotente:
  crea un **service client M2M** + un **client-scope audience** (con
  `oidc-audience-mapper`) e lo assegna a service + **consumer client**.
- `patch_dotenv` / `read_dotenv_keys` / `is_configured` — patch idempotente di
  file `.env` (upsert per chiave, preserva il resto).

Nessuna dipendenza dal servizio chiamante: nomi env, default, prompt e wrapper
stanno nel caller (es. `services/calendar_scheduler/.../kc_setup.py`).

## Estendere (user/group/client generici)

Usa `admin.kc` (python-keycloak) direttamente, es:

```python
from kc_provision import KeycloakAdmin
admin = KeycloakAdmin(server, realm, admin_user=u, admin_password=p)
await admin.login()
await admin.kc.a_create_group({"name": "operatori"})
uid = await admin.kc.a_create_user({"username": "svc", "enabled": True})
```

## User e gruppi nel client

In Keycloak user e gruppi sono abilitati a un client tramite **client role**.
L'adapter admin espone helper diretti per questo modello:

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

Significato dei parametri:

- `client_id`: client id pubblico Keycloak, per esempio `nob-app`, non UUID
  interno.
- `username`: username Keycloak, per esempio `mario`, non UUID interno dello
  user. L'adapter lo risolve con `a_get_user_id(username)` prima di assegnare o
  rimuovere client role.
- `role_name`: nome del client role Keycloak dentro `client_id`, per esempio
  `access`.
- `group_path`: path del gruppo Keycloak, per esempio `/operatori`. Lo slash
  iniziale mancante viene normalizzato, quindi `operatori` e `/operatori`
  indicano lo stesso gruppo top-level.

## Perche' l'audience scope va su TUTTI i consumer

Il backend verifica QUALSIASI bearer come JWT keycloak. Se si abilita la verifica
`aud`, ogni client che lo chiama deve emettere l'`aud` o va in 401 (login utenti
compresi). Per questo lo scope condiviso si assegna a service + tutti i consumer.
L'**enforcement** (`OZON_TOKEN_AUDIENCE` lato app) resta una scelta del caller,
disaccoppiata.

## Test

```bash
uv run python -m pytest tests/
```
