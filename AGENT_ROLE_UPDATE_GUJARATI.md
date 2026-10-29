SHUBHVASTRA — Agent Role / User Access Update

1. Admin Panel / User Access માં હવે Agent role ઉમેર્યો છે.
2. Role = Agent પસંદ કરતાં Agent Master માંથી Agent પસંદ કરો. Username આપમેળે પસંદ કરેલા Agent ના નામ પ્રમાણે રહેશે; password Admin સેટ કરશે.
3. એક Agent માટે એક active Agent login account જ મંજૂર છે.
4. Agent login કર્યા પછી ફક્ત My Dashboard, My Pending Orders, My Dispatched Orders અને My Cancelled Orders જ જોઈ શકશે.
5. Agent dashboard પર માત્ર તે Agent સાથે parties.agent_id દ્વારા જોડાયેલી Parties દેખાશે. Pending orders, pending pieces, dispatched orders, cancelled orders અને Party List read-only છે.
6. Pending/Dispatched/Cancelled reports માં PDF download વિકલ્પ છે.
7. Agent role ને Party Master, Agent Master, New Order, Dispatch update, Utilities, Admin Panel, અન્ય Agent/Party reports અથવા edit actions ઉપલબ્ધ નથી.
8. Database schema upgrade માં users.agent_id column ઉમેરાય છે; હાલના business records delete/replace થતા નથી.

Update પહેલાં full backup ZIP અને database backup download કરો. GitHub માં code upload કરતી વખતે database file replace/delete ન કરશો. Streamlit Cloud પર deploy કર્યા પછી Admin Panel માં Agent role user બનાવીને અલગ browser/incognito session માં login test કરો.


Login પછી Agent role માં navigation error fix: role-specific menu માં ન હોય તેવો જૂનો page selection હોય તો હવે Agent menu નું પ્રથમ page પસંદ થશે.
