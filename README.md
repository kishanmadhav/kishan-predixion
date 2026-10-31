# kishan-predixion

Part B solutions for the Predixion AI engineering assignments. Each folder has its own `NOTES.md` covering assumptions, trade-offs and next steps.

One-time setup (Python 3.11+):
```
python -m venv .venv && . .venv/bin/activate        # Windows: .venv\Scripts\activate
```

## Assignment 1: Collections Ledger
```
cd assignment1
pip install -r requirements.txt
python -m pytest -q
```

## Assignment 2: Dialer Campaign Analytics
```
cd assignment2
pip install -r requirements.txt
python gen_data.py
python build_notebook.py            # executes analysis.ipynb; memo in memo.md
python -m pytest -q
```

## Assignment 3: Fix and Ship
```
cd assignment3
pip install -r requirements-dev.txt && python -m pytest -q
docker build -t call-webhook . && docker run -p 8000:8000 -e CRM_URL=https://crm.example -e CRM_API_TOKEN=x call-webhook
cd infra && terraform init && terraform plan
```
Deploy evidence is in `assignment3/evidence/`. CI is in `.github/workflows/assignment3-deploy.yml`.

## Assignment 4: Collections Assistant Agent
```
cd assignment4
pip install -r requirements.txt
python -m pytest -q                 # offline
cp .env.example .env                # add ANTHROPIC_API_KEY
python eval.py
```

AI usage is logged in `AI_USAGE.md`.
