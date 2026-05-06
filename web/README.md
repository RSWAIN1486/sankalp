# Sankalp WebUI

This is the SvelteKit frontend for Sankalp. During development it runs separately from the
Python backend and uses the backend JSON/SSE APIs through the Vite dev proxy. In installed
app mode, `npm run build` writes `web/build`, and the Python backend serves that static
bundle from the same loopback origin as `/api/*`.

## Development

Run the Sankalp backend first:

```sh
cd /Users/rswai/sankalp
python3 server.py
```

Then run the WebUI dev server:

```sh
cd /Users/rswai/sankalp/web
source ~/.nvm/nvm.sh
nvm use
npm install
npm run dev -- --port 5173
```

If `npm run dev` says Vite requires a newer Node version, your shell is not using the
`web/.nvmrc` runtime yet. Run:

```sh
source ~/.nvm/nvm.sh
nvm use
```

The Vite dev server proxies `/api/*` to `http://127.0.0.1:8765`.
Open `http://127.0.0.1:5173`.

## Installed App Build

```sh
cd /Users/rswai/sankalp/web
source ~/.nvm/nvm.sh
nvm use
npm ci
npm run build
```

After the build, `python3 server.py` serves the WebUI at `http://127.0.0.1:8765`.

## Current Scope

- SvelteKit/TypeScript app shell
- Chat/sidebar/activity/settings components
- Typed API service for the existing JSON and SSE routes
- Dexie/IndexedDB storage for browser-local UI preferences and cached sessions

The backend source of truth is still the existing Python API and JSON session store. SQLite
becomes the source of truth in the next migration phase.
