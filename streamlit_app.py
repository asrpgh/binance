# ---------- 2. Persistent Login Logic (Fixed) ----------
def check_login():
    # 1. Immediate bypass if already logged in this session
    if st.session_state.get("authenticated"):
        return True

    # 2. Fetch from Local Storage
    stored_password = streamlit_js_eval(js_expressions="localStorage.getItem('p2p_app_pwd')", key="ls_reader")
    
    # 3. Validation Logic
    if stored_password == APP_PASSWORD:
        st.session_state["authenticated"] = True
        st.rerun()
        return True

    # 4. Show Login UI
    # We show this if stored_password is '' (empty), different from APP_PASSWORD, 
    # or if it's the second run and it's still None.
    st.title("🔒 Acceso Restringido")
    
    # Optional: status indicator while JS loads
    if stored_password is None:
        st.caption("Verificando persistencia...")

    pwd_input = st.text_input("Introduce la contraseña maestra:", type="password")
    
    if st.button("Ingresar"):
        if pwd_input == APP_PASSWORD:
            # Set in LocalStorage
            streamlit_js_eval(
                js_expressions=f"localStorage.setItem('p2p_app_pwd', '{pwd_input}')", 
                key="ls_writer"
            )
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Contraseña incorrecta.")
    
    return False
