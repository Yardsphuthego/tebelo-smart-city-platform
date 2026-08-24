# TEBELO

Production-oriented Django implementation of the TEBELO intelligent city safety and public-service platform. The current release implements the document's core MVP: citizen accounts, GPS incident reporting, secure evidence, routing, status tracking, public-safe maps, Around Me, city alerts, authority queues, analytics, service-desk messaging, administration, auditing, a versioned API and a unified service-delivery engine.

## Architecture

- Django 5.2 LTS and Django REST Framework
- PostgreSQL 17 with PostGIS; incident coordinates receive a generated geography point and GiST index in PostgreSQL
- Server-rendered, accessible responsive citizen and authority interfaces
- Unfold-powered internal operations console with a Formula-inspired, database-backed dashboard
- Private evidence downloads with ownership/organisation checks and SHA-256 integrity records
- Organisation-scoped role access and an explicit incident-transition state machine
- Docker image running as a non-root user, WhiteNoise static assets and Gunicorn

SQLite is supported for local development and tests. PostgreSQL/PostGIS is the production database.

The MapLibre vector style is provider-configurable through `MAP_STYLE_URL`. The default uses OpenFreeMap's Positron style for local evaluation. Configure a contracted or self-managed vector-tile service with appropriate availability and data-processing terms for production.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open `http://127.0.0.1:8000`. Migrations install the Botswana → South-East District → Gaborone location hierarchy and the initial incident taxonomy. Configure real participating organisations and officer memberships in `/admin/` before accepting reports.

## Production deployment

1. Copy `.env.example` to `.env`, generate a long random secret, set the public host and trusted HTTPS origin, and choose a strong database password.
2. Ensure `.env` contains `DATABASE_URL=postgresql://tebelo:<password>@db:5432/tebelo` and `POSTGRES_PASSWORD=<password>` is exported for Compose.
3. Put the service behind a TLS-terminating reverse proxy and configure durable, encrypted backups for the database and media volumes.
4. Run `docker compose up -d --build`.
5. Run `docker compose exec web python manage.py createsuperuser`, then configure authority organisations and memberships.

### Service-delivery engine

Configure routing policies, authority shifts and duty assignments in `/admin/`. The engine creates one operational case for every incident and virtual service request, applies the matching routing/SLA policy, assigns an available duty officer, raises overdue notifications and records authority handoffs in an auditable timeline. The authority workspace is available at `/command/delivery/`.

For the Gaborone rollout, apply the verified baseline authority directory and routing matrix with:

```bash
python manage.py configure_gaborone_authorities
```

This command is idempotent. It marks external agencies as `Authority onboarding`, creates the TEBELO command centre, routes every installed incident and virtual-service type, and adds active super administrators to daily command oversight. Change an agency to `Authority connected` only after its authorised staff, operating agreement and escalation contacts have been confirmed.

To evaluate the complete workflow locally or in an isolated staging environment, load the synthetic Gaborone operating scenario:

```bash
python manage.py populate_gaborone_scenario
```

The command is idempotent and preserves existing accounts. It creates clearly identified scenario residents and authority staff, Gaborone areas, duty coverage, incidents, public alerts, neighbourhood-watch groups, virtual-service conversations, delivery deadlines, handoffs, recommendations and audit activity. Newly created scenario accounts use `TebeloDemo!2026`; override it with `--password`. Do not load synthetic scenario records into a live production database.

The provided Compose deployment starts a single `delivery-engine` service after the web application is healthy. For a non-Compose deployment, run the engine at least once per minute from the production scheduler:

```bash
python manage.py process_delivery_engine
```

Only one scheduler instance should run at a time. The command is safe to repeat: escalation notifications respect each policy's repeat window. Recommendations combine official strategic priorities with current routing gaps, SLA breaches and neighbourhood-watch moderation backlogs. They remain reviewable proposals until an authorised command user accepts or implements them.

Validate production settings with:

```bash
DJANGO_DEBUG=false DJANGO_SECRET_KEY='<50+ random characters>' \
DJANGO_ALLOWED_HOSTS=tebelo.example.bw DJANGO_SECURE_SSL_REDIRECT=true \
python manage.py check --deploy
```

## API

The session-authenticated API is under `/api/v1/`:

- `GET /api/v1/categories/`
- `GET|POST /api/v1/incidents/` (citizens see only their reports; authority users see only their organisations)
- `GET /api/v1/alerts/` (public active alerts)

The interactive public map consumes `/map/incidents.geojson`, which intentionally excludes report descriptions, identities and evidence.

## Operational boundaries

This code does not claim that emergency authorities are integrated. It clearly directs immediate emergencies to `999`. WebRTC video, mobile push providers, automated AI classification and government-system connectors require authorised providers, data-processing agreements and operational procedures; no fake integrations are included. Before public launch, commission penetration testing, privacy/legal review, incident-response exercises, encrypted off-site backups, authority identity/MFA integration and a media object store with malware scanning.

## Quality checks

```bash
python manage.py check
python -m pytest
python -m ruff check .
```
