SHUBHVASTRA — Pending to Dispatch / Agent Wise Pending Report Update

1. Pending to Dispatch Order માં હવે Party auto-select નહીં થાય. પહેલા “Select Party” ખાલી selection દેખાશે; Party પસંદ કર્યા પછી જ તેની pending rows દેખાશે.
2. Pending pieces અંગેનું explanatory caption દૂર કર્યું છે.
3. Agent Wise Pending Report માં પહેલાં Agent પસંદ કરશો. પછી તે Agent ની pending Party list નીચે આવશે.
4. “All [Agent] Parties” પસંદ કરતાં પસંદ કરેલા Agent ની બધી pending parties નો report દેખાશે. કોઈ ચોક્કસ Party પસંદ કરતાં ફક્ત તેની pending orders દેખાશે.
5. અન્ય dispatch/report features અગાઉની ZIP મુજબ જ રાખ્યાં છે.

Deploy કરતા પહેલાં database backup રાખવો. Python syntax check પાસ થયું છે; live Streamlit Cloud end-to-end test કરવાનું બાકી છે.

## Agent Role / User Access (2026-10-29)
- Added Agent role to Admin Panel / User Access.
- Agent account is linked to one Agent Master record and username follows selected agent name.
- Agent login sees only its own assigned parties and read-only pending, dispatched, cancelled reports with PDF downloads.
- Agent role does not get access to order editing, dispatch updates, master data, Utilities, or other agents' reports.
- See AGENT_ROLE_UPDATE_GUJARATI.md. Back up the database before deploying.
