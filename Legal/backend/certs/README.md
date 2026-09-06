# Extra trusted CA roots

PEM files here are installed into the backend image's system trust store
(`update-ca-certificates`) and picked up by httpx / requests through
`SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE`.

Needed because the corporate network inspects TLS: outbound HTTPS to
`iam-dev.jiofinance.in` / `auth-dev.jiofinance.in` is re-signed by a Netskope
root that the default certifi bundle does not contain, which surfaced as
`[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain`
on startup IAM sync and as a 500 on `POST /api/auth/login`.

- `netskope-root-ca.crt` — Netskope root (`CN=*.sin2.goskope.com`), valid to
  2032-08-23. Exported from the macOS System keychain:

  ```bash
  security find-certificate -a -c "*.sin2.goskope.com" -p \
      /Library/Keychains/System.keychain > backend/certs/netskope-root-ca.crt
  ```

Files must be PEM with a `.crt` extension. Off the corporate network nothing
here is used, so the extra roots are harmless.
