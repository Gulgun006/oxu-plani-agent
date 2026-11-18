"""
MƏRHƏLƏ 4 — İNTERFEYS (app.py)
Streamlit söhbət interfeysi (Azərbaycan dilində). İşə salmaq: streamlit run app.py
Müəllim üçün: hazır test düymələri və sistem promptunu canlı redaktə etmək imkanı.
"""
import json
import anthropic
import streamlit as st
import agent as agent_mod
from agent import run_agent
from prompts import SYSTEM_PROMPT, GUNLER
from tools import new_db, now

st.set_page_config(page_title="Oxu Planı Agenti", page_icon="📚")
st.title("📚 Oxu Planı Agenti")
st.caption("Fənlərini və imtahan tarixlərini yaz, sənin üçün gündəlik oxu planı qurum.")

TESTLER = [
    ("1. Adi sorğu", "Koloproktologiya imtahanım 19 noyabr 16:30-dadır"),
    ("2. İki alət ardıcıl", "Cərrahiyyə imtahanım 5 dekabr 10:00-dadır, onu yaz və gündə 6 saatlıq plan qur"),
    ("3. Yaddaş", "Bayaq yazdığım cərrahiyyənin saatını 14:00 et"),
    ("4. Mövzudan kənar", "Mənə şeir yaz"),
    ("5. Qeyri-müəyyən", "Tezliklə imtahanım var"),
    ("6. Keçmiş tarix", "Kimya imtahanım 1 noyabrda idi, əlavə et"),
    ("7. 8 saat limiti", "Gündə 12 saat oxumaq istəyirəm, plan qur"),
    ("8. Fayl ixracı", "Planı fayl kimi ver"),
]

# ---------------- Yaddaş (hər istifadəçi üçün ayrıca)
if "messages" not in st.session_state:
    st.session_state.messages = []   # AI-ya gedən tam tarixçə (alət nəticələri daxil)
    st.session_state.chat = []       # ekranda göstərilən söhbət
    st.session_state.db = new_db()   # imtahanlar
if "sys_prompt" not in st.session_state:
    st.session_state.sys_prompt = SYSTEM_PROMPT

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])


def render_prompt(template: str) -> str:
    """{bugun}, {gun}, {saat} yerinə indiki Bakı vaxtını qoyur."""
    n = now()
    return (template.replace("{bugun}", n.strftime("%Y-%m-%d"))
                    .replace("{gun}", GUNLER[n.weekday()])
                    .replace("{saat}", n.strftime("%H:%M")))


# ---------------- Sol panel
pending = None
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
        for k in ("messages", "chat", "db"):
            st.session_state.pop(k, None)
        st.rerun()

    st.divider()
    st.subheader("🧪 Test ssenariləri")
    st.caption("Düyməyə bas — mesaj agentə avtomatik göndərilir.")
    for ad, mesaj in TESTLER:
        if st.button(ad, help=mesaj, use_container_width=True):
            pending = mesaj

    st.divider()
    with st.expander("⚙️ Sistem promptu (müəllim üçün)"):
        st.caption("Promptu dəyiş və «Tətbiq et» bas. Dəyişiklik yalnız bu sessiyaya təsir edir. "
                   "{bugun}, {gun}, {saat} avtomatik doldurulur.")
        yeni = st.text_area("Sistem promptu", st.session_state.sys_prompt, height=350,
                            label_visibility="collapsed")
        c1, c2 = st.columns(2)
        if c1.button("✅ Tətbiq et", use_container_width=True):
            st.session_state.sys_prompt = yeni
            st.success("Yeni prompt tətbiq edildi.")
        if c2.button("↩️ Defolt", use_container_width=True):
            st.session_state.sys_prompt = SYSTEM_PROMPT
            st.rerun()
    if st.session_state.sys_prompt != SYSTEM_PROMPT:
        st.warning("Dəyişdirilmiş sistem promptu istifadə olunur.")


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

# ---------------- Yeni mesaj (yazılan və ya test düyməsindən gələn)
user_text = st.chat_input("Mesajını yaz...") or pending
if user_text:
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
                # interfeysdəki (və ya defolt) sistem promptunu agentə ötür
                agent_mod.build_system_prompt = lambda: render_prompt(st.session_state.sys_prompt)
                answer = run_agent(client, st.session_state.messages, st.session_state.db, on_tool)
            except anthropic.APIError as e:
                answer = f"⚠️ API xətası: {e}"
                st.session_state.messages.pop()   # uğursuz mesajı tarixçədən çıxar
        st.markdown(answer)
    st.session_state.chat.append({"role": "assistant", "content": answer, "tools": calls})
    st.rerun()   # sol paneldəki cədvəl yenilənsin
