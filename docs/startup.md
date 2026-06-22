# TippeQpongen — developer startup

## Quick start (use the script)

```powershell
.\start-dev.ps1
```

Opens backend (port 8000) and frontend (port 3001) in separate PowerShell windows.

---

## Manual startup

### 1. Backend — FastAPI (port 8000)

```powershell
C:\Users\kimme\anaconda3\python.exe -m uvicorn backend.main:app --reload --port 8000
```

Verify: open http://127.0.0.1:8000/health in a browser. Should return `{"status":"ok",...}`.

### 2. Frontend — Next.js (port 3001)

```powershell
cd frontend
$env:PATH = "$env:PATH;C:\Program Files\nodejs"
npm run dev -- -p 3001
```

Open: http://localhost:3001/coupon

### 3. Data sync (run after backend starts)

```powershell
C:\Users\kimme\anaconda3\python.exe sync.py --status        # check what's in DB
C:\Users\kimme\anaconda3\python.exe sync.py --daily         # full refresh
C:\Users\kimme\anaconda3\python.exe sync.py --validate      # 24 integrity checks
```

---

## Cache reset

If the frontend shows stale UI or crashes after a dependency change:

```powershell
Remove-Item -Recurse -Force frontend\.next
cd frontend && npm run dev -- -p 3001
```

---

## Common errors

| Symptom | Cause | Fix |
|---|---|---|
| `net::ERR_CONNECTION_REFUSED /v1/coupons` | FastAPI not running | Start backend (step 1 above) |
| `net::ERR_CONNECTION_REFUSED /v1/sync/status` | FastAPI not running | Start backend (step 1 above) |
| Frontend shows "Backend kjører ikke" banner | FastAPI not running | Start backend (step 1 above) |
| `ModuleNotFoundError: No module named 'uvicorn'` | Wrong Python | Use `C:\Users\kimme\anaconda3\python.exe` |
| `npm : The term 'npm' is not recognized` | Node not in PATH | `$env:PATH = "$env:PATH;C:\Program Files\nodejs"` |
| Port 8000 already in use | Old uvicorn still running | `Stop-Process -Name python -Force` or close old terminal |
| Port 3001 already in use | Old Next.js still running | Close old terminal or use a different port |
| Next.js render crash / blank page | Stale `.next` cache | Delete `frontend\.next` and restart |
| `NEXT_PUBLIC_API_URL` wrong | Env file missing | Check `frontend/.env.local` contains `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` |

---

## Services overview

| Service | URL | Start command |
|---|---|---|
| FastAPI backend | http://127.0.0.1:8000 | `uvicorn backend.main:app --reload --port 8000` |
| Next.js frontend | http://localhost:3001 | `npm run dev -- -p 3001` (in `frontend/`) |
| Streamlit (backup UI) | http://localhost:8501 | `streamlit run app.py` |
| API docs | http://127.0.0.1:8000/docs | (auto, when backend is running) |
