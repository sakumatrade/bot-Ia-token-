# Broker Sakuma — Safari Web Extension

Read-only view of status, bots, opportunities and research, talking only
to the Local API. It never handles a private key, seed phrase, or
blockchain RPC — see `tests/structural.test.js`, which enforces that as
regression tests, not just as a promise in this README.

```
Safari Extension -> Local API -> Security -> Risk -> Execution
```

Never `Safari Extension -> Solana directly` (spec section 39).

## Build & test

This is plain TypeScript + the WebExtensions API — no Xcode needed to
write, type-check, or test it (that's only needed for the final
packaging step below):

```
cd extension
npm run build   # tsc -> dist/
npm test        # tsc --noEmit + structural checks (no blockchain SDK
                 # imports, no secret-material references, fetch() only
                 # in apiClient.ts, host_permissions locked to the Local
                 # API origin, manifest_version 3)
```

## Converting to a native Safari extension (requires a Mac + Xcode)

A Safari *Web Extension* is plain web technology (this `manifest.json` +
`dist/*.js` + the HTML/CSS files) wrapped in a thin native macOS/iOS app
shell that Xcode generates. On a Mac, with the extension built
(`npm run build` first):

```
xcrun safari-web-extension-converter /path/to/extension
```

That generates an Xcode project you open and run like any other macOS
app; Safari then offers to enable the extension under
Preferences -> Extensions.

## Configuration

Open the extension's options page (gear icon / "Configurações" in the
popup) and set:
- **Endereço da API Local**: defaults to `http://127.0.0.1:8765`.
- **Chave da API**: the same value as the backend's
  `BROKER_SAKUMA_LOCAL_API__API_KEY`.

This key is a Local API credential, not a blockchain secret — but it's
still sensitive (it can pause the system or read your P&L), so don't
share it. `manifest.json`'s `host_permissions` are locked to the Local
API's own origin, so even if the key leaked to a malicious page, that
page couldn't use it — only this extension's own popup ever attaches it
to a request, and only to `127.0.0.1:8765`/`localhost:8765`.
