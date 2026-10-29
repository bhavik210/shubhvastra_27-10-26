SHUBHVASTRA — Pending to Dispatched 4 submenu update

1. Pending to Dispatch Order: only parties with remaining pending quantity. One selectable row per pending piece. Tick Dispatch OR Cancel (the opposite checkbox is hidden). No Dispatch Qty input. Save to Dispatched writes one dispatch or cancellation record per selected piece, resets the party selection.
2. Party Wise Pending Report: All Parties and individual party filters. M/L/XL/XXL columns, Qty, Discount, Amount (after percentage discount), Details, DD-MM-YYYY dates, PDF.
3. Agent Wise Pending Report: Agent Master list, including agents with no pending orders; party-wise records and PDF.
4. SKU Wise Pending Report: multiselect only SKUs with pending orders; empty selection shows all pending SKUs. Party Name included and PDF.

A new order_size_cancellations table is created automatically by init_db to record individual cancelled pieces without destroying original ordered quantities. Back up the PostgreSQL database before deploying. Existing data is not bundled. Python syntax checked; production end-to-end testing is not performed.
