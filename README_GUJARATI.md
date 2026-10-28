# SHUBHVASTRA — GitHub + Streamlit Cloud (Testing Build)

આ build માં હાલની Streamlit web app નું branded layout અને ઉપલબ્ધ business modules રાખવામાં આવ્યા છે. **તમારી માંગ મુજબ TESTING માટે login/admin password બંધ છે.**

## Package માં શું છે?
- `app.py` — Streamlit app entrypoint
- `requirements.txt` — Python dependencies
- `.streamlit/config.toml` — theme settings
- `.streamlit/secrets.toml.example` — PostgreSQL URL નું example (actual credentials અહીં ન લખવા)
- `migrate_sqlite_to_postgres.py` — જૂના SQLite database ને PostgreSQL માં migrate કરવા
- `static/` — Shubhvastra અને Trishiv logos
- `README_GUJARATI.md` — setup guide

## 1. GitHub માં upload
1. ZIP extract કરો.
2. GitHub માં repository બનાવો (Private રાખવાની ભલામણ).
3. ZIP ના અંદરના project files/folders repository ના **root** માં upload કરો. `app.py` અને `requirements.txt` root માં હોવા જોઈએ.
4. `party_reporting.db`, `shubhvastra_local.db`, `.env`, actual `secrets.toml` અથવા database credentials GitHub પર upload ન કરશો.

## 2. Streamlit Community Cloud માં live કરો
1. `https://streamlit.io/cloud` ખોલીને GitHub સાથે sign in કરો.
2. **Create app / Deploy app** પસંદ કરો.
3. Repository અને branch પસંદ કરો.
4. Main file path `app.py` રાખો.
5. Python version 3.12 પસંદ કરી શકો છો, પછી **Deploy** કરો.

## 3. Login / password
આ testing build માં login page અને admin password જરૂરી નથી. URL ખોલતાં સીધું Dashboard આવશે. **જે કોઈ પાસે URL હશે તે app નો data જોઈ/બદલી શકશે. Public/live business data માટે આ સુરક્ષિત નથી.** Testing પૂરી થાય પછી owner કહે ત્યારે authentication ફરી ચાલુ કરવી.

## 4. Database માટે ખૂબ મહત્વનું
- `DATABASE_URL` ન હોય તો app local `shubhvastra_local.db` બનાવે છે. Local computer પર UI test કરવા માટે યોગ્ય છે.
- Streamlit Cloud પર આ local SQLite database **persistent/shared database તરીકે વિશ્વસનીય નથી**. Restart/redeploy અથવા cloud instance બદલાય તો data ગુમાવવાનો જોખમ છે; અલગ staff માટે એક જ live data પણ ખાતરીપૂર્વક નહીં રહે.
- માત્ર screen/layout testing માટે DATABASE_URL વગર deploy કરી શકો છો. Real order entry / multi-staff testing પહેલાં managed PostgreSQL બનાવો અને Streamlit Cloud → App → Settings → Secrets માં નીચેનું set કરો:

```toml
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE?sslmode=require"
```

`USER`, `PASSWORD`, `HOST`, `DATABASE` ને provider ની actual connection details થી બદલો. Actual URL GitHub પર ન મૂકો. Save કર્યા પછી app reboot કરો.

## 5. જૂનો data migrate કરવો હોય તો
1. હાલના desktop app માંથી બહાર આવી `party_reporting.db` ની backup copy બનાવો.
2. `migrate_sqlite_to_postgres.py` ને local computer પર ચલાવીને database ને PostgreSQL માં migrate કરો; source database file ને GitHub પર upload ન કરશો.
3. પહેલાં test database પર migration કરો અને party/order counts verify કરો.

## હાલના modules
Dashboard, Party Master, Agent Master, Item Master/SKU, Order Form, Orders, Order Details, Pending to Dispatched, Order Reports અને Utilities/Backup.

## નોંધ
આ Streamlit version છે. Branding, module names અને core business flows જાળવ્યા છે, પરંતુ desktop software નો દરેક pixel અને દરેક advanced workflow સંપૂર્ણ સમાન છે એવો દાવો નથી. CSV/PDF, dispatch, reports અને database migration ને sample data વડે ચકાસો. Login disabled હોવાથી આ build માત્ર testing માટે છે.


## Full Backup / Restore (Utilities)
- Utilities / Backup & Restore માં `Download Full Backup ZIP` દ્વારા parties, agents, SKU, orders, order items, dispatch history અને users નો app-level backup લો.
- Restore કરવા માટે આ જ app માંથી બનાવેલી ZIP upload કરો અને data replace confirmation checkbox પસંદ કરો. Restore હાલના records ને uploaded backup ના records થી replace કરે છે.
- Restore પહેલાં હાલનો backup download કરી રાખવો. Backup ZIP માં business data હોઈ શકે છે, તેને સુરક્ષિત રાખો અને GitHub માં upload ન કરો.
- આ restore feature app ના પોતાના backup ZIP માટે છે; arbitrary CSV અથવા જૂની `.db` ફાઇલ સીધી restore કરવા માટે નથી.
