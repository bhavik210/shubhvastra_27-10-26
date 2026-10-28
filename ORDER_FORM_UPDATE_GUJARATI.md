SHUBHVASTRA — New Order Update

Updates included:
- Navigation label changed to New Order; separate Order List button.
- Current date is the default Order Date; order number is assigned at save time from the last saved number.
- Party selection defaults to Select Party, and phone/city/state/agent display in read-only fields.
- Five item rows appear initially; entering data in the last visible row adds another row automatically, up to 999.
- Size quantities M/L/XL/XXL are manual numeric inputs; Discount and WSP Rate fields have no +/- controls. SKU rate defaults from Item Master.
- Required multiple-select Packaging: Chain Bag, Box Packing, Sherwani Bag Packaging.
- Required single-choice GST: 5% GST or 5-18% GST.
- Additional Order Details text area.
- Save then choose whether to download the A4 PDF; choosing No clears the form for the next order.
- Order List includes order number/date/party/quantity/amount/agent, edit, PDF download and delete confirmation.
- Delete requires password 9414 and is blocked for orders with dispatch records.
- Editing is blocked for dispatched orders; for an editable order, only SKU and size quantities can be changed (rate, discount, party/date and other details are read-only).
- PDF includes party and transport details plus a structured item table.
- Adds gst_type column to existing SQLite/PostgreSQL orders table without replacing existing business records.

Deployment:
1. Back up the current database before deploying.
2. Replace repository files with this ZIP's contents; app.py and requirements.txt must be in repository root.
3. Reboot the Streamlit app.
4. Test with a new order and confirm the existing order history is still present.

Validation: app.py passed Python syntax compilation. A full live Streamlit/PostgreSQL end-to-end test was not run in this build environment.
