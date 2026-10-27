# SHUBHVASTRA Web App — Online Deployment Audit (Gujarati)

## હાલની ZIP વિશે
આ ZIP માં Flask આધારિત શરૂઆતનું Web App છે. `app.py`, `templates/`, `static/`, `wsgi.py` અને `requirements.txt` ઉપલબ્ધ છે. `app.py` અને `wsgi.py` Python syntax compilation પસાર કરે છે. આનો અર્થ એ નથી કે જૂના Desktop Python Software ના બધા Features અથવા Data Migration સંપૂર્ણ રીતે ચકાસાઈ ગયા છે.

## હાલ દેખાતા Modules
- Login, Dashboard
- Party Master, Agent Master, SKU/Item Master
- Order Form, Orders, Order Details/Edit/Delete
- Pending to Dispatched, Dispatch History
- Party/Agent/Order Reports
- Order CSV import/export અને CSV templates
- Staff user management અને password change
- Admin database backup download

## Public Internet પર મૂકતાં પહેલાં જરૂરી કામ
1. `FLASK_SECRET_KEY` માં લાંબી, random અને ખાનગી value સેટ કરવી. હાલ code માં fallback secret છે; તેને production માં રાખવું નહીં.
2. પ્રથમ admin password `ChangeMe123!` તરીકે default છે. Deployment પહેલાં environment variables માં મજબૂત password સેટ કરવો અને login પછી તરત બદલી નાખવો.
3. HTTPS ફરજિયાત રાખવું; secure session-cookie settings, CSRF protection, login rate limiting અને audit log ઉમેરવા/ચકાસવા.
4. Backup route માં database copy process ને production-safe બનાવવી; backup ને web root બહાર રાખવો, restore workflow અને automated off-site backup ઉમેરવા.
5. બધા POST forms, role permissions, order delete, dispatch validation અને CSV import ને staff accounts સાથે test કરવું.
6. Desktop database import/migration પહેલાં original database ની untouched copy રાખવી; migration test copy પર કરવી.
7. SQLite એક નાની single-instance app માટે ચાલે, પરંતુ અનેક staff એકસાથે ભારે writes કરે તો PostgreSQL તરફ migration વિચારવી. એક જ live database માટે દરેક staff અલગ અલગ app copy ચલાવે નહીં.
8. હાલની ZIP માં PDF export, Excel (.xlsx) export, database restore UI અને configurable in-app settings સંપૂર્ણ રીતે દેખાતા નથી. જરૂરી હોય તો તેને અલગથી implement અને test કરવું.

## Hosting માટે ભલામણ
### સરળ શરૂઆત: PythonAnywhere
આ Flask app માટે PythonAnywhere નું Manual Configuration + WSGI deployment સીધું છે. `wsgi.py` માં `from app import app as application` પહેલેથી છે. Database માટે persistent absolute path રાખો અને environment variables host પર જ સેટ કરો. Host ની current plan limits, storage અને backup policy deployment પહેલાં તપાસો.

Official instructions: https://help.pythonanywhere.com/pages/Flask/

### વધુ scale માટે
જો staff concurrency અને future growth વધારે હોય તો managed PostgreSQL સાથેનું hosting વધુ યોગ્ય બની શકે. Render જેવા host પર default filesystem ephemeral હોઈ શકે છે; SQLite વાપરો તો persistent disk જરૂરી છે. Official details: https://render.com/docs/disks

## PythonAnywhere deployment checklist
1. ZIP extract કરીને code તમારા account માં upload કરો.
2. Web tab → Add a new web app → Manual Configuration પસંદ કરો અને compatible Python version પસંદ કરો.
3. Bash console માં virtual environment બનાવો અને project folder માંથી `pip install -r requirements.txt` ચલાવો.
4. Web tab ના WSGI configuration file માં project folder path ઉમેરો અને `from app import app as application` સેટ કરો.
5. Host ના environment variables માં `FLASK_SECRET_KEY`, `SHUBHVASTRA_ADMIN_USER`, `SHUBHVASTRA_ADMIN_PASSWORD`, અને `SHUBHVASTRA_DB` સેટ કરો.
6. `SHUBHVASTRA_DB` માટે persistent writable absolute path વાપરો; code folder ની temporary copy પર આધાર ન રાખો.
7. Web app reload કરો અને HTTPS URL પર login test કરો.
8. પહેલાં dummy data થી Order, edit, dispatch, CSV import/export, backup અને staff permissions test કરો.
9. ત્યાર પછી જ live business data migrate કરો.

## મહત્વની મર્યાદા
આ audit guide છે, production-security certification નથી. હાલની ZIP ને સીધી public internet પર મૂકવી યોગ્ય નથી જ્યાં સુધી ઉપરની security અને functional testing પૂર્ણ ન થાય. Original desktop Python source/database અલગ હોય તો તેને પણ inspect કરીને feature-by-feature comparison અને migration plan બનાવવો જરૂરી છે.
