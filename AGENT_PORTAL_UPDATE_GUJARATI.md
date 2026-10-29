SHUBHVASTRA — Agent Portal Update

1. Agent menu labels updated:
   - My Pending Orders -> My Party Pending Orders
   - My Dispatched Orders -> Total Dispatched Orders
   - My Cancelled Orders -> Total Cancle Orders
2. My Dashboard Party List now includes Party Name, Phone Number, City, State, Address, GST Number, Transport Name and Transport ID.
3. Pending, dispatched and cancelled pages have a party dropdown with an all-parties option first and individual party options below it.
4. All three order views use a consistent size-pivot table: Order No., Order Date, Party Name, SKU Code, M, L, XL, XXL, Qty, Discount, Amount. PDF download uses the same displayed columns.
5. Data is filtered by the logged-in user's assigned agent_id and the selected party ID. Agent portal remains read-only.

Before deploying, download a full database backup. Update code files only; do not delete or replace the live database. Python syntax validation passed; live Streamlit/database testing is still required.
