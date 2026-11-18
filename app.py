"""
MƏRHƏLƏ 4 — İNTERFEYS (app.py)
Streamlit söhbət interfeysi (Azərbaycan dilində). İşə salmaq: streamlit run app.py
"""
import json
import anthropic
import streamlit as st
from agent import run_agent
from tools import new_db

st.set_page_config(page_title="Oxu Planı Agenti", page_icon="📚")
st.title("📚 Oxu Planı Agenti")
st.caption("Fənlərini və imtahan tarixlərini yaz, sənin üçün gündəlik oxu planı qurum.")

# ---------------- Yaddaş (hər istifadəçi üçün ayrıca)
if "messages" not in st.session_state:
    st.session_state.messages = []   # AI-ya gedən tam tarixçə (alət nəticələri daxil)
    st.session_state.chat = []       # ekranda göstərilən söhbət
    st.session_state.db = new_db()   # imtahanlar

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# ---------------- Sol panel
with st.sidebar:
    st.header("🗓️ İmtahanlarım")
    exams = sorted(st.session_state.db["exams"], key=lambda e: (e["tarix"], e["saat"]))
    if exams:
        st.dataframe([{"№": e["id"], "Fənn": e["fenn"], "Tarix": e["tarix"], "Saat": e["saat"]}
                      for e in exams], hide_index=True, use_container_width=True)
    else:
        st.info("Hələ imtahan yoxdur.")
    if st.session_state.db["export_text"]:
        st.download_button("⬇️ Planı yüklə (oxu_plani.txt)", st.session_state.db["export_text"],
                           file_name="oxu_plani.txt", mime="text/plain")
    if st.button("🔄 Söhbəti sıfırla"):
        st.session_state.clear()
        st.rerun()
    st.divider()
    st.markdown("**Nümunələr:**\n- Fizika imtahanım 25 dekabr 10:00-dadır\n"
                "- Neçə gün qalıb?\n- Gündə 6 saatlıq plan qur\n- Planı fayl kimi ver")


def show_tool(name, inp, out, container):
    icon = "✅" if out.get("ok") else "⚠️"
    with container.expander(f"🔧 {name} çağırıldı {icon}"):
        st.markdown("**Giriş:**")
        st.code(json.dumps(inp, ensure_ascii=False, indent=2), language="json")
        st.markdown("**Nəticə:**")
        st.code(json.dumps(out, ensure_ascii=False, indent=2), language="json")


# ---------------- Əvvəlki söhbəti göstər
for m in st.session_state.chat:
    with st.chat_message(m["role"]):
        for t in m.get("tools", []):
            show_tool(*t, st)
        st.markdown(m["content"])

# ---------------- Yeni mesaj
if user_text := st.chat_input("Mesajını yaz..."):
    st.session_state.chat.append({"role": "user", "content": user_text})
    st.session_state.messages.append({"role": "user", "content": user_text})
    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        calls = []
        def on_tool(name, inp, out):
            calls.append((name, inp, out))
            show_tool(name, inp, out, st)
        with st.spinner("Düşünürəm..."):
            try:
                answer = run_agent(client, st.session_state.messages, st.session_state.db, on_tool)
            except anthropic.APIError as e:
                answer = f"⚠️ API xətası: {e}"
                st.session_state.messages.pop()   # uğursuz mesajı tarixçədən çıxar
        st.markdown(answer)
    st.session_state.chat.append({"role": "assistant", "content": answer, "tools": calls})
    st.rerun()   # sol paneldəki cədvəl yenilənsin
