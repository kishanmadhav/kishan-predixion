# Assignment 3: Fix and Ship (Part B)

## Run locally
```
python -m pip install -r requirements-dev.txt
python -m pytest -q
docker build -t call-webhook:local .
docker run -p 8000:8000 -e CRM_URL=https://crm.example/schedule -e CRM_API_TOKEN=x call-webhook:local
curl localhost:8000/health
```

## Layout
| Path | What |
|---|---|
| `app/scheduling.py` | `schedule_retry(attempt, now)`: pure function, IST-aware |
| `app/storage.py` | call records + transactional CRM outbox (SQLite) |
| `app/crm.py` | async CRM client (5 s timeout, status checked) + outbox flush |
| `app/main.py` | FastAPI app factory, Pydantic model, `/health`, webhook |
| `app/logging_config.py` | one-line JSON logs |
| `Dockerfile` | multi-stage, slim, non-root uid 10001, HEALTHCHECK |
| `infra/` | Terraform: VPC, ALB, ECS Fargate in private subnets, ECR, Secrets Manager, logs, autoscaling, circuit breaker, GitHub OIDC role |
| `../.github/workflows/assignment3-deploy.yml` | test → terraform validate → build/push → deploy via OIDC |
| `evidence/` | `docker_run.txt`, `terraform_plan.txt`, `terraform_apply.txt`, `live_health.txt` |

## Defects fixed from Part A1
| # | Original | What goes wrong in production | Sev | Fix |
|---|---|---|---|---|
| 1 | `disposition == "NO_ANSWER" or "BUSY"` | Always true, so PTP, dispute and connected calls also get retry calls. A compliance breach. | High | `in {"NO_ANSWER","BUSY"}` |
| 2 | f-string SQL | SQL injection from webhook body | High | Parameterised queries, plus Pydantic pattern validation |
| 3 | No `commit()` | Inserts are never persisted | High | Explicit `BEGIN IMMEDIATE … COMMIT` |
| 4 | `datetime.now()` + comment "IST" | Server clock is UTC on AWS, so the window check is off by 5h30 and borrowers get called at night | High | `zoneinfo("Asia/Kolkata")`, aware datetimes only |
| 5 | `hour > 19` / `replace(hour=9)` | 19:xx is allowed; times before 08:00 (e.g. 03:00) aren't caught; a time after midnight skips a whole day; minutes are kept (09:47) | High | Window `08:00 ≤ t < 19:00`; before → 08:00 same day; after → 08:00 next day |
| 6 | `attempt > len(...)` | `RETRY_GAPS_MIN[3]` raises `IndexError` → 500 | Medium | `>=`, returns None |
| 7 | `history=[]` default | Shared mutable list grows forever (memory leak, cross-request state) | Medium | Removed |
| 8 | `timeout=None` | One hung CRM request blocks the worker forever | High | 5 s timeout |
| 9 | Bare `except` + `time.sleep` inside `async def` | Swallows every error (including the `datetime` JSON `TypeError`), blocks the event loop for up to 5 s per call, and silently drops the retry after 5 tries | High | Transactional outbox: the retry is stored with the call and delivered asynchronously; failures stay PENDING and are swept every 15 s |
| 10 | `datetime` in `json=` | `TypeError` on every call, hidden by #9, so the CRM never gets a retry | High | `.isoformat()` |
| 11 | Module-level `sqlite3.connect` | Shared across threads → `ProgrammingError`; on Fargate the file is lost on restart and each task has its own DB | High | Per-operation connections. **Production should use RDS Postgres** (see below) |
| 12 | `body["account_id"]` | `KeyError` → 500, and the platform retries forever | Medium | Pydantic model → 422 |
| 13 | No idempotency | Webhook redelivery creates duplicate rows and duplicate retries | High | `call_id` is the primary key; a redelivery returns `duplicate` |
| 14 | `CRM_URL` may be `None` | Fails on the first request instead of at boot | Low | `Settings.from_env()` fails fast |
| 15 | `r.json()` without a status check | A 500 from the CRM is treated as success | Medium | `raise_for_status()` |

## Infrastructure decisions
- **Private subnets + ALB.** Tasks have no public IP. The service SG only accepts 8000 from the ALB SG and only egresses 443. Egress is through one NAT per AZ.
- **Secret.** `aws_secretsmanager_secret` without a version, so the value is set out of band with `put-secret-value` and never stored in Terraform state. It is injected via the container `secrets` block.
- **Roles.**
  - *Execution role* (the ECS agent: pull image, write logs, read the one secret ARN): the managed policy plus a single `secretsmanager:GetSecretValue` on that ARN.
  - *Task role* (the app's own AWS calls): empty, because the app calls no AWS APIs.
- **Autoscaling.** Target tracking on `ALBRequestCountPerTarget` at 6000/min/task (≈100 rps). At the 500 rps peak that is ~5 tasks, with min 2 and max 10.
- **Safe deploys.** Circuit breaker with rollback, min healthy 100%, max 200%, and `wait_for_steady_state`. Terraform ignores `task_definition` and `desired_count`, because CI owns the image and autoscaling owns the count.
- **CI auth.** A GitHub OIDC provider and a role whose trust is limited to `repo:<owner>/<repo>:ref:refs/heads/main`. Permissions: push to one ECR repo, update one service, and `iam:PassRole` only for the two task roles and only to ECS.
- **Region** is enforced as `ap-south-1` by variable validation (PII residency).

## CI/CD setup
1. Create the GitHub repo and set `github_repo` (default `kishan/kishan-predixion`) to match it, then re-apply.
2. In the repo settings, add the variable `AWS_DEPLOY_ROLE_ARN` = `terraform output -raw github_deploy_role_arn`.
3. Push to `main`. The pipeline runs test → terraform validate → build/push `:<sha>` → render task def → deploy and wait for stability.

## Teardown (within 24 h)
```
cd infra
terraform destroy -var image_tag=b64495e
```
`force_delete` on ECR and `recovery_window_in_days = 0` on the secret let destroy clean up fully.

## Trade-offs and what I'd do with another day
- **SQLite on Fargate is ephemeral and per-task.** Fine for proving the deploy; not for production. Next: RDS Postgres (Multi-AZ, ap-south-1, KMS) with the same outbox table, and `SELECT … FOR UPDATE SKIP LOCKED` for the sweeper so several tasks can share it.
- Better still for a CRM that is down for minutes: webhook → SQS (with a DLQ) → worker. The webhook then only enqueues and returns 202.
- HMAC signature verification on the webhook (shared secret in Secrets Manager), plus WAF rate limiting on the ALB.
- HTTPS: a `certificate_arn` variable is supported, but the sandbox runs HTTP only.
- VPC endpoints for ECR, Logs and Secrets Manager to cut NAT cost; a read-only root FS with a tmpfs volume.
- Remote state (S3 + lockfile) and `terraform plan` on PRs.
