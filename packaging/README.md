# KIBO Packaging

Phase 5 packages the React/Electron shell and the Python FastAPI backend as a Windows app.

## Build Backend

From `frontend/`:

```powershell
npm run bundle:python
```

This runs PyInstaller with `packaging/kibo_backend.spec` and creates:

```text
dist/python/python_backend/server.exe
```

The spec excludes optional heavyweight analysis/UI packages such as PySide6,
torch, scipy, pandas, and notebook tooling so the headless server bundle stays
focused on the API process. Install and tune those separately if you later want
offline voice or ML acceleration inside the packaged backend.

## Build Installer

From `frontend/`:

```powershell
npm run dist:win:full
```

This builds the Python backend, builds the Electron app, then runs `electron-builder` for an NSIS installer under `dist/electron/`.

## Runtime Layout

The packaged Electron app expects:

```text
resources/
  app.asar
  assets/
  python_backend/
    server.exe
  config.example.json
```

In dev mode, Electron still runs `python -m src.api.main` from the repo root.
