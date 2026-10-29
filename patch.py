from pathlib import Path
p=Path('/mnt/data/dispatched_history_update/app.py')
s=p.read_text()
needle='\ndef page_cancelled_orders():\n'
new='''
def page_dispatched_details(view='party'):
    """Show saved dispatch transactions by party or agent, with PDF export."""
    title = 'Party Wise Dispatched History' if view == 'party' else 'Agent Wise Dispatched History'
    st.title(title)
    base = q("""SELECT p.party_name AS "Party Name",COALESCE(a.agent_name,'—') AS "Agent Name",
        o.order_no AS "Order No.",o.order_date AS "Order Date",d.dispatch_date AS "Dispatch Date",
        i.particulars AS "SKU Code",d.dispatched_size AS "Size",d.qty AS "Dispatched Qty",
        d.invoice_number AS "Invoice No.",d.details AS "Dispatch Details"
        FROM order_dispatches d
        JOIN order_item_sizes s ON s.id=d.order_size_id
        JOIN order_items i ON i.id=s.order_item_id
        JOIN orders o ON o.id=i.order_id
        JOIN parties p ON p.id=o.party_id
        LEFT JOIN agents a ON a.id=p.agent_id
        ORDER BY d.dispatch_date DESC,o.order_no DESC,p.party_name,i.particulars,d.dispatched_size""")
    if base.empty:
        st.info('હજુ સુધી કોઈ dispatched history ઉપલબ્ધ નથી.')
        return
    for col in ('Order Date','Dispatch Date'):
        base[col] = pd.to_datetime(base[col], errors='coerce').dt.strftime('%d-%m-%Y').fillna('')
    if view == 'party':
        parties = sorted(base['Party Name'].dropna().astype(str).unique().tolist())
        chosen = st.selectbox('Select Party', parties, key='dispatched_history_party')
        shown = base[base['Party Name'] == chosen].copy()
        filename = 'shubhvastra_party_dispatched_history.pdf'
    else:
        agents = sorted(base.loc[base['Agent Name'] != '—', 'Agent Name'].dropna().astype(str).unique().tolist())
        if not agents:
            st.info('Dispatched history માટે કોઈ Agent જોડાયેલો નથી.')
            return
        chosen = st.selectbox('Select Agent', agents, key='dispatched_history_agent')
        shown = base[base['Agent Name'] == chosen].copy()
        filename = 'shubhvastra_agent_dispatched_history.pdf'
        party_options = ['All Parties'] + sorted(shown['Party Name'].dropna().astype(str).unique().tolist())
        chosen_party = st.selectbox('Select Party', party_options, key='dispatched_history_agent_party')
        if chosen_party != 'All Parties':
            shown = shown[shown['Party Name'] == chosen_party].copy()
            filename = 'shubhvastra_agent_party_dispatched_history.pdf'
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption(f"Dispatched pieces: {int(pd.to_numeric(shown['Dispatched Qty'], errors='coerce').fillna(0).sum())}")
    if shown.empty:
        st.info('પસંદ કરેલા filter માટે dispatched history મળી નથી.')
    st.download_button('Download PDF', pending_report_pdf_bytes(title, shown), file_name=filename,
                       mime='application/pdf', key=f'{view}_dispatched_history_pdf', use_container_width=True)


def page_cancelled_orders():
'''
if needle not in s: raise SystemExit('insert point missing')
s=s.replace(needle,new,1)
old='''if role_name == "admin":
    menu=["Dashboard","Party Master","Agent Master","Item Master","New Order","Pending to Dispatched","Order Reports","Utilities"]
elif role_name == "member":
    menu=["Dashboard","Party Master","Agent Master","Item Master","New Order","Pending to Dispatched","Order Reports","Utilities"]
else:
    menu=["Dashboard","Pending to Dispatched","Order Reports","Utilities"]
'''
newmenu='''if role_name == "admin":
    menu=["Dashboard","Party Master","Agent Master","New Order","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
elif role_name == "member":
    menu=["Dashboard","Party Master","Agent Master","New Order","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
else:
    menu=["Dashboard","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
'''
if old not in s: raise SystemExit('menu block missing')
s=s.replace(old,newmenu,1)
old='''    if page == "Utilities":
        util_options = ["Order History / Order List", "Cancelled Orders"] + (["Admin Panel / Backup & Restore"] if is_admin() else [])
        util_choice = st.selectbox("Utilities", util_options, key="utilities_submenu")
    else:
        util_choice = ""
'''
newutil='''    if page == "Utilities":
        util_options = ["Order History / Order List", "Cancelled Orders"]
        if role_name in ("admin", "member"):
            util_options.insert(0, "Item Master")
        if is_admin():
            util_options.append("Admin Panel / Backup & Restore")
        util_choice = st.selectbox("Utilities", util_options, key="utilities_submenu")
    elif page == "Dispatched Details":
        dispatched_options = ["Party Wise Dispatched History", "Agent Wise Dispatched History"]
        dispatched_choice = st.selectbox("Dispatched Details", dispatched_options, key="dispatched_details_submenu")
    else:
        util_choice = ""
        dispatched_choice = ""
'''
if old not in s: raise SystemExit('utilities block missing')
s=s.replace(old,newutil,1)
old='''elif page=="Item Master": page_sku()
elif page=="New Order":
'''
new='''elif page=="New Order":
'''
if old not in s: raise SystemExit('item routing missing')
s=s.replace(old,new,1)
old='''elif page=="Utilities" and util_choice == "Order History / Order List": page_orders()
elif page=="Utilities" and util_choice == "Cancelled Orders": page_cancelled_orders()
'''
new='''elif page=="Utilities" and util_choice == "Item Master" and role_name in ("admin", "member"): page_sku()
elif page=="Utilities" and util_choice == "Order History / Order List": page_orders()
elif page=="Utilities" and util_choice == "Cancelled Orders": page_cancelled_orders()
elif page=="Dispatched Details": page_dispatched_details("party" if dispatched_choice == "Party Wise Dispatched History" else "agent")
'''
if old not in s: raise SystemExit('utilities routing missing')
s=s.replace(old,new,1)
p.write_text(s)
