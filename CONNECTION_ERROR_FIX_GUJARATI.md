# PostgreSQL Connection Error — Gujarati Fix

If Streamlit shows `sqlalchemy.exc.OperationalError` during `init_db()`, the app cannot connect to PostgreSQL. This is usually a connection-string/host/password/database/network issue, not the Shubhvastra login password.

1. Open Streamlit Cloud → Manage app → Settings → Secrets.
2. Replace the sample `DATABASE_URL` with the actual connection URI copied from the PostgreSQL provider. Do not leave `USER`, `PASSWORD`, `HOST`, or `DATABASE` as literal placeholder values.
3. Use `postgresql://...` or `postgresql+psycopg://...`. If the database password contains reserved URL characters such as `@`, `#`, `/`, or `:`, URL-encode them.
4. Check that the database exists, the credentials are correct, SSL is configured as required by the provider, and the provider allows connections from Streamlit Cloud.
5. Save Secrets and reboot/redeploy the app.

`SHUBHVASTRA_ADMIN_USER` / `SHUBHVASTRA_ADMIN_PASSWORD` are app-login credentials. They are not the PostgreSQL credentials in `DATABASE_URL`.

Never paste actual credentials into chat or commit them to GitHub. The app now shows safer diagnostic hints while hiding connection secrets.
