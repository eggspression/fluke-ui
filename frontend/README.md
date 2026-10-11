# FLUKE UI frontend

This Angular 22 app is the small browser flow for the local university MVP. It
uses the backend API for all experiment, run, result, and log data. It does not
load FLUKE or read run files directly.

## Start locally

1. Follow [backend setup](../backend/README.md): start PostgreSQL, apply the
   migration, and create a user with `fluke-admin`. In `backend/.env`, set
   `FLUKE_DEVELOPMENT_ORIGINS=["http://localhost:4200"]` and restart the API.
2. Keep the API at `http://127.0.0.1:8000` and `fluke-worker` running in separate
   terminals. Start both from `backend/` with the same `FLUKE_ARTIFACTS_DIR`.
3. From `frontend/`, run:

   ```sh
   npm ci
   npm start
   ```

4. Open <http://localhost:4200/>. Sign in, create a FedAvg or FedProx experiment,
   edit it before its first run, launch, then follow status, recent logs, accuracy
   by round, and history. The first FLUKE run may download MNIST.

The token exists only in memory. Logging out or reloading the page requires a
new login; there is no server logout or refresh-token route. A protected API
`401` also clears the token. A completed or failed run stops polling.

## Check the frontend

```sh
npm test -- --watch=false
npm run build
```

The tests cover authentication, bearer headers, form payloads and validation
messages, completed accuracy, failed-run display, and polling stop. The backend
enforces ownership: another user's experiment, run, or log ID returns `404`.
Run the full two-user, two-algorithm demonstration during MVP-06.
