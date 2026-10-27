SHUBHVASTRA — Secure Admin Login Update

શું બદલાયું:
- TEST MODE / Login disabled દૂર કર્યું.
- App ખોલતાં પહેલાં username/password login જરૂરી છે.
- કોઈ default admin username/password નથી.
- Database માં active Admin ન હોય ત્યારે Initial Admin Setup દેખાશે. ત્યાં તમારો Main Admin username અને મજબૂત password બનાવો (ઓછામાં ઓછા 10 characters).
- Login screen પર Forgot Password વિકલ્પ નથી.
- Main Admin → Utilities / Admin Panel → User Name & Password માંથી staff/admin accounts બનાવી શકાય છે, username બદલી શકાય છે, password reset કરી શકાય છે અને login access enable/disable કરી શકાય છે.
- Utilities ફક્ત Admin ને દેખાશે.
- Admin logout કરી શકે છે. Staff માટે Utilities/Admin Panel ઉપલબ્ધ નથી.
- Backup & Restore Utilities માં અલગ tab તરીકે જાળવ્યું છે.

Deployment:
1. GitHub repository માં આ ZIP ની project files જૂની files ને replace કરીને upload કરો.
2. app.py અને requirements.txt repository root માં હોવા જોઈએ.
3. Streamlit Cloud → Manage app → Reboot app.
4. જો database માં કોઈ active Admin નથી તો Initial Admin Setup દેખાશે. તમારું username/password સેટ કરો અને પછી login કરો.

મહત્વપૂર્ણ:
- Password hash સ્વરૂપે જ database માં સંગ્રહાય છે.
- Forgot Password નથી. Admin password ભૂલી જાય તો database owner ને secure administrative recovery કરવી પડશે.
- Streamlit Cloud પર permanent/shared business data માટે managed PostgreSQL DATABASE_URL જરૂરી છે.
- App ને public URL પર મૂકતા પહેલાં database backup લો અને HTTPS/provider access controls વાપરો.
