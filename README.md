# Ingredex Backend

FastAPI backend for **Ingredex**: OTP auth, product barcode lookup (Open Food Facts), label OCR (Groq Vision), AI ingredient analysis (CrewAI + Groq), Redis caching, and PostgreSQL persistence.

## Prerequisites

- **Python** 3.11–3.13  
- **[Poetry](https://python-poetry.org/docs/#installation)** for dependencies  
- **PostgreSQL** (async URL with `postgresql+asyncpg://`)  
- **Redis** for caching barcode and analysis results  
- **Groq API key** (`GROQ_API_KEY`) for OCR and CrewAI analysis  
- Optional: **SMTP** for OTP email delivery  

## Setup

1. **Clone / open** this repo and `cd` into `ingredex-backend`.

2. **Environment**
   ```bash
   cp .env.example .env
   ```
   Fill at least: `DATABASE_URL`, `JWT_SECRET_KEY`, `REDIS_URL`, `GROQ_API_KEY`.  
   Optional: `ACCESS_TOKEN_EXPIRE_MINUTES` (default 30), `REFRESH_TOKEN_EXPIRE_DAYS` (default 7).  
   For email OTP: SMTP variables in `.env.example`.

3. **Install dependencies**
   ```bash
   poetry install
   ```

4. **Database migrations**
   ```bash
   poetry run migrate
   ```
   (Applies Alembic to `head`; same as `alembic upgrade head` from project root.)

5. **Redis**  
   Run Redis locally (e.g. Docker) so `REDIS_URL` (default `redis://localhost:6379`) is reachable. The API starts without Redis, but caching and `/health` Redis checks will fail until it is up.

## How to run

| Command | Description |
|--------|-------------|
| `poetry run dev` | Uvicorn on `0.0.0.0:8000` with `--reload` |
| `python run.py` | Same as dev server (from project root) |
| `poetry run uvicorn app.main:app --reload --port 8000` | Manual uvicorn |

**API docs:** [http://localhost:8000/docs](http://localhost:8000/docs) (Swagger)

## API overview

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `GET` | `/` | No | Liveness |
| `GET` | `/health` | No | DB + Redis status |
| `POST` | `/auth/send-otp` | No | Send OTP to email |
| `POST` | `/auth/verify-otp` | No | Exchange OTP for access + refresh tokens |
| `POST` | `/auth/refresh` | No | Rotate refresh token → new access + refresh |
| `POST` | `/auth/logout` | Bearer | Revoke refresh token(s) for this user |
| `GET` | `/auth/me` | Bearer | Current user profile |
| `POST` | `/scan/barcode` | No | Barcode → product (Open Food Facts + cache) |
| `POST` | `/scan/ocr` | No | Image → ingredients text (Groq Vision) |
| `POST` | `/analyze` | Bearer | AI ingredient analysis (cache + optional `ProductScan` row) |
| `GET` | `/history/stats` | Bearer | Scan counts by type |
| `GET` | `/history` | Bearer | List scans |
| `GET` | `/history/{scan_id}` | Bearer | Single scan |
| `DELETE` | `/history/{scan_id}` | Bearer | Delete scan |

## Redis concepts (what we cache and why)

Redis is an **in-memory key-value store** used here as a **cache**, not the system of record.

| Key pattern | TTL | Purpose |
|-------------|-----|---------|
| `barcode:{code}` | 24 h | Open Food Facts responses. Same barcode scanned often → fewer HTTP calls. |
| `analysis:{hash}` | 12 h | CrewAI **AnalysisResult** JSON keyed by a **hash of normalized ingredients**. Identical ingredient sets reuse the same expensive LLM run. |

If Redis is down, the API still runs: barcode/analysis steps skip cache read/write and hit upstream services or recompute. **PostgreSQL** remains the durable store for users, OTPs, refresh tokens, and saved scans.

## Testing requests

See **`test_api.http`** for example calls (REST Client). Set `@token` and `@refreshToken` after **Verify OTP**, and `@scanId` from **List scans** for history routes.

## Project layout (high level)

- `app/main.py` — FastAPI app, CORS, lifespan (DB init + Redis), `/health`, global error handler  
- `app/routers/` — `auth`, `scan`, `analyze`, `history`  
- `app/services/` — OTP, auth, cache, scan, OCR  
- `app/ai/` — CrewAI crew, agents, tasks, preprocessor  
- `alembic/` — migrations  


