SHUBHVASTRA — Agent Runtime Error Fix

Changes:
1. Agent reports use pivot_table(dropna=True) instead of dropna=False. The latter can produce a large cartesian product with many report index values and can crash the Streamlit process.
2. Agent portal rendering is guarded so a page-level exception is logged rather than taking down the whole UI. The user is directed to Streamlit Cloud Logs for the sanitized cause; credentials are not printed in the UI.

Deploy:
- Back up the configured database first.
- Replace code files from this ZIP in GitHub. Do not delete/replace the live database.
- Reboot Streamlit Cloud.
- Test Agent login and Pending / Dispatched / Cancelled pages.
- If generic “Error running app” persists, open Manage app -> Logs and share the final traceback lines with secrets/passwords removed. The screenshot alone does not contain the original exception.

Validation performed: Python syntax compilation and ZIP integrity only. No live Streamlit Cloud or production database test was possible.
