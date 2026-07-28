# Extra trusted CAs for the local image

Drop your organization's root/intermediate certificates here as `*.crt` files
(PEM encoded, one certificate per file) before `docker compose up --build`.

They are copied to `/usr/local/share/ca-certificates/repave/` and registered with
`update-ca-certificates`, so **curl**, **pip**/**uv**, **ansible-galaxy**, and **git**
inside the image all trust them. This is the supported way to build behind a TLS
inspecting proxy.

Certificates placed here are ignored by git (`.gitignore`) — never commit an
internal CA. If you truly cannot obtain the CA, see the `REPAVE_TLS_INSECURE`
escape hatch in [../README.md](../README.md).

DER-encoded certificates (`.cer`, `.der`) must be converted first:

```bash
openssl x509 -inform der -in corp-root.cer -out corp-root.crt
```
