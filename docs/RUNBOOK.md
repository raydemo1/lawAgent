# LawAgent Runbook

This is the shortest path for another engineer to run the service-mode demo,
check health, and reproduce the main eval.

## 1. Prepare Env

```powershell
Copy-Item .env.example .env
pip install -e ".[service]"
```

Edit `.env` and set:

- `OPENAI_COMPATIBLE_API_KEY`
- `EMBEDDING_API_KEY`
- `ES_URL`, `PG_DSN`, `ES_INDEX`, `PG_TABLE` if not using defaults

## 2. Start Elasticsearch And pgvector

```powershell
docker compose up -d --build
docker compose ps
```

Wait until Elasticsearch and Postgres are healthy.

## 3. Index The Review Corpus

```powershell
python -m law_agent.review index-service --execute
python -m law_agent.review service-doctor
```

`service-doctor` should report:

- `elasticsearch: True`
- `postgres: True`
- non-zero `elasticsearch_docs`
- non-zero `pgvector_rows`

## 4. Start API

```powershell
python -m law_agent.review serve --host 127.0.0.1 --port 8000 --service
```

Health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/health | ConvertTo-Json -Depth 6
```

The response includes LLM configuration status, ES/PG reachability, and indexed
corpus counts.

## 5. Start Frontend

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://127.0.0.1:5173`.

## 6. Run Golden-Set Eval

Quick smoke:

```powershell
python -m law_agent.review eval --suite quick --retrieval-mode service --review-mode llm --max-workers 4 --output artifacts/review_runs/eval_quick_service.json
```

Full proof run:

```powershell
python -m law_agent.review eval --suite full --retrieval-mode service --review-mode llm --max-workers 4 --output artifacts/review_runs/eval_full_service.json
```

Eval summaries include retrieval quality metrics plus:

- `mean_total_latency_ms`
- `mean_retrieval_latency_ms`
- `total_llm_calls`
- `total_retries`

## 7. Stop Local Services

```powershell
docker compose stop
```

Use `docker compose down -v` only when you intentionally want to delete service
data and rebuild indexes from scratch.
