SHUBHVASTRA — ROLE PERMISSIONS UPDATE

Admin
- Full access to all available modules and settings.
- Can add/edit parties, agents, SKUs, and orders.
- Only Admin can import/export Parties CSV, export SKU CSV, and access Utilities / Admin Panel.
- Can create/update users and assign Admin, Member, or Staff roles.
- Utilities includes User Name & Password, History Report, and Backup & Restore.

Member
- Dashboard shows full party list and permits party-list CSV download.
- Party Master: add parties only; no edit, import CSV, or export CSV.
- Agent Master: add agents only; no edit.
- Item Master: add new SKUs only; no edit or SKU CSV export. Duplicate SKU numbers are rejected.
- Can create new orders, but cannot edit existing orders or cancel/restore them.
- Utilities / Admin Panel is hidden and inaccessible through normal navigation.

Staff
- Dashboard shows only Party Name, City, Transport Name, Transport ID, and Address.
- No phone number, GST number, agent name, or reference on the dashboard; no party-list CSV download.
- Party Master, Agent Master, Item Master, Order Form, and Utilities are not available.
- Order operations, order details, dispatch, and reports remain available through the navigation.

Security notes
- Login is required; no Forgot Password option is shown.
- Admin controls user creation and password resets.
- Order Form create/edit actions are logged in Utilities > History Report with username, role, action, order number, and timestamp.
- This update passed Python syntax compilation. A full live Streamlit Cloud end-to-end test has not been run; verify role behavior with one test account per role before production use.
