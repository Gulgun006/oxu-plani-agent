"""
MƏRHƏLƏ 1 — ALƏTLƏR (tools.py)
Agentin çağıra biləcəyi funksiyalar. Hansını nə vaxt çağırmaq qərarını AI verir.
Guardrail-lar KODDA da var: keçmiş tarix rədd edilir, gündə max 8 saat.
Hər istifadəçinin öz məlumatı `db` lüğətində saxlanılır (st.session_state-dən gəlir).
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Baku")   # server UTC-dədir, ona görə vaxt zonası vacibdir
MAX_SAAT = 8                 # guardrail: gündə ən çox oxu saatı
IMTAHAN_GUNU_MAX = 3         # imtahan günü yalnız qısa təkrar


def now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def new_db() -> dict:
    return {"exams": [], "next_id": 1, "export_text": None}


def _parse(tarix: str, saat: str | None = None) -> datetime:
    return datetime.strptime(f"{tarix} {saat or '09:00'}", "%Y-%m-%d %H:%M")


def _d(tarix: str):
    return datetime.strptime(tarix, "%Y-%m-%d").date()


# ------------------------------------------------------------------ ALƏTLƏR

def add_exam(db, fenn: str, tarix: str, saat: str | None = None) -> dict:
    try:
        dt = _parse(tarix, saat)
    except ValueError:
        return {"ok": False, "xeta": "Tarix/saat formatı yanlışdır (YYYY-MM-DD, HH:MM)."}
    if dt <= now():
        return {"ok": False, "xeta": f"'{fenn}' imtahanının tarixi ({tarix} {saat or ''}) artıq keçib. Əlavə edilmədi."}
    for e in db["exams"]:
        if e["fenn"].lower() == fenn.lower():
            return {"ok": False, "xeta": f"'{fenn}' artıq siyahıdadır (id={e['id']}). Dəyişmək üçün update_exam istifadə et."}
    exam = {"id": db["next_id"], "fenn": fenn, "tarix": tarix, "saat": saat or "09:00"}
    db["exams"].append(exam)
    db["next_id"] += 1
    return {"ok": True, "elave_edildi": exam}


def days_left(db, tarix: str) -> dict:
    try:
        gun = (_d(tarix) - now().date()).days
    except ValueError:
        return {"ok": False, "xeta": "Tarix formatı yanlışdır (YYYY-MM-DD)."}
    return {"ok": True, "tarix": tarix, "gun_qalib": gun, "kecib": gun < 0}


def list_exams(db) -> dict:
    return {"ok": True, "imtahanlar": sorted(db["exams"], key=lambda e: (e["tarix"], e["saat"]))}


def update_exam(db, id: int, fenn: str | None = None, tarix: str | None = None, saat: str | None = None) -> dict:
    for e in db["exams"]:
        if e["id"] == id:
            t, s = tarix or e["tarix"], saat or e["saat"]
            try:
                if _parse(t, s) <= now():
                    return {"ok": False, "xeta": "Yeni tarix keçmişdədir. Dəyişiklik edilmədi."}
            except ValueError:
                return {"ok": False, "xeta": "Tarix/saat formatı yanlışdır."}
            kohne = dict(e)
            e.update(fenn=fenn or e["fenn"], tarix=t, saat=s)
            return {"ok": True, "kohne": kohne, "yeni": dict(e)}
    return {"ok": False, "xeta": f"id={id} olan imtahan tapılmadı."}


def delete_exam(db, id: int) -> dict:
    for e in db["exams"]:
        if e["id"] == id:
            db["exams"].remove(e)
            return {"ok": True, "silindi": e}
    return {"ok": False, "xeta": f"id={id} olan imtahan tapılmadı."}


def make_plan(db, gundelik_saat: int = 6) -> dict:
    """Çəki = 1 / gün_qalıb: yaxın imtahan daha çox saat alır. Gündə max 8 saat."""
    xeberdarliq = None
    if gundelik_saat > MAX_SAAT:
        xeberdarliq = f"Gündə {gundelik_saat} saat sağlam deyil, {MAX_SAAT} saatla məhdudlaşdırıldı."
        gundelik_saat = MAX_SAAT
    if gundelik_saat < 1:
        return {"ok": False, "xeta": "Gündəlik saat ən azı 1 olmalıdır."}

    n = now()
    gelecek = [e for e in db["exams"] if _parse(e["tarix"], e["saat"]) > n]
    if not gelecek:
        return {"ok": False, "xeta": "Plan üçün gələcək tarixli imtahan yoxdur. Əvvəlcə imtahan əlavə et."}

    plan, gun, son = [], n.date(), max(_d(e["tarix"]) for e in gelecek)
    while gun <= son:
        aktiv = [e for e in gelecek if _d(e["tarix"]) >= gun]
        saat_gun = gundelik_saat
        if gun == n.date():                       # bu gün: qalan vaxta görə
            saat_gun = min(saat_gun, max(0, 22 - n.hour))
        if any(_d(e["tarix"]) == gun for e in aktiv):
            saat_gun = min(saat_gun, IMTAHAN_GUNU_MAX)
        ceki = {e["fenn"]: 1 / max((_d(e["tarix"]) - gun).days, 0.5) for e in aktiv}
        cem = sum(ceki.values())
        dersler = [{"fenn": f, "saat": round(saat_gun * c / cem, 1)} for f, c in ceki.items()]
        dersler = [x for x in dersler if x["saat"] >= 0.5]
        plan.append({"tarix": gun.isoformat(), "dersler": dersler,
                     "cem_saat": round(sum(x["saat"] for x in dersler), 1),
                     "imtahan": [e["fenn"] + " " + e["saat"] for e in aktiv if _d(e["tarix"]) == gun]})
        gun += timedelta(days=1)

    res = {"ok": True, "gundelik_saat": gundelik_saat, "plan": plan}
    if xeberdarliq:
        res["xeberdarliq"] = xeberdarliq
    return res


def export_plan(db, gundelik_saat: int = 6) -> dict:
    """BONUS: planı .txt faylı kimi hazırlayır (yükləmə düyməsi interfeysdə çıxır)."""
    p = make_plan(db, gundelik_saat)
    if not p["ok"]:
        return p
    s = ["OXU PLANI", "=" * 30]
    for g in p["plan"]:
        s.append(f"\n{g['tarix']}  (cəmi {g['cem_saat']} saat)")
        s += [f"  • {d['fenn']}: {d['saat']} saat" for d in g["dersler"]]
        s += [f"  🎓 İMTAHAN: {f}" for f in g["imtahan"]]
    db["export_text"] = "\n".join(s)
    return {"ok": True, "fayl": "oxu_plani.txt", "mesaj": "Fayl hazırdır, yükləmə düyməsi sol paneldədir."}


TOOL_FUNCS = {
    "add_exam": add_exam, "days_left": days_left, "list_exams": list_exams,
    "update_exam": update_exam, "delete_exam": delete_exam,
    "make_plan": make_plan, "export_plan": export_plan,
}

# ----------------------------------------------- Alətlərin AI üçün təsviri (sxem)
TOOL_SCHEMAS = [
    {"name": "add_exam",
     "description": "Yeni imtahanı (fənn və tarix) siyahıya əlavə edir. Hər fənn üçün ayrıca çağır. Keçmiş tarixi rədd edir.",
     "input_schema": {"type": "object", "properties": {
         "fenn": {"type": "string", "description": "Fənnin adı"},
         "tarix": {"type": "string", "description": "YYYY-MM-DD"},
         "saat": {"type": "string", "description": "HH:MM (istəyə bağlı)"}},
         "required": ["fenn", "tarix"]}},
    {"name": "days_left",
     "description": "Verilmiş tarixə neçə gün qaldığını hesablayır. Günləri heç vaxt özün hesablama, bunu çağır.",
     "input_schema": {"type": "object", "properties": {
         "tarix": {"type": "string", "description": "YYYY-MM-DD"}}, "required": ["tarix"]}},
    {"name": "list_exams",
     "description": "Daxil edilmiş bütün imtahanları id-ləri ilə qaytarır. Əvvəlki qeydə istinad olunanda əvvəlcə bunu çağır.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "update_exam",
     "description": "Mövcud imtahanın fənnini, tarixini və ya saatını id ilə dəyişir.",
     "input_schema": {"type": "object", "properties": {
         "id": {"type": "integer"}, "fenn": {"type": "string"},
         "tarix": {"type": "string", "description": "YYYY-MM-DD"},
         "saat": {"type": "string", "description": "HH:MM"}}, "required": ["id"]}},
    {"name": "delete_exam",
     "description": "İmtahanı id ilə siyahıdan silir.",
     "input_schema": {"type": "object", "properties": {"id": {"type": "integer"}}, "required": ["id"]}},
    {"name": "make_plan",
     "description": "Bütün gələcək imtahanlara əsasən gündəlik oxu planı qurur. Yaxın imtahana daha çox saat ayırır. Gündə max 8 saat.",
     "input_schema": {"type": "object", "properties": {
         "gundelik_saat": {"type": "integer", "description": "Gündə neçə saat oxumaq (1-8). Bilinmirsə 6."}}}},
    {"name": "export_plan",
     "description": "Planı oxu_plani.txt faylı kimi ixrac edir. İstifadəçi faylı istəyəndə çağır.",
     "input_schema": {"type": "object", "properties": {
         "gundelik_saat": {"type": "integer", "description": "1-8, bilinmirsə 6"}}}},
]
