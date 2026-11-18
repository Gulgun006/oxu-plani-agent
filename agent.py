"""
MƏRHƏLƏ 3 — AGENT DÖVRÜ (agent.py)
düşün → alət çağır → nəticəni yoxla → (lazımsa yenə alət) → cavab ver
Hansı aləti çağırmaq qərarını Claude özü verir; burada heç bir if/regex yoxdur.
"""
import json
import anthropic
from tools import TOOL_FUNCS, TOOL_SCHEMAS
from prompts import build_system_prompt

MODEL = "claude-haiku-5-5"   # daha güclü variant: "claude-sonnet-5-5"
MAX_ADDIM = 6                # sonsuz dövrün qarşısını alır


def run_agent(client: anthropic.Anthropic, messages: list, db: dict, on_tool=None) -> str:
    """
    messages: bütün söhbət tarixçəsi (YADDAŞ) — yerində yenilənir.
    db: istifadəçinin imtahan məlumatı.
    on_tool(ad, giriş, nəticə): interfeysdə "🔧 ... çağırıldı" göstərmək üçün.
    """
    for _ in range(MAX_ADDIM):
        resp = client.messages.create(
            model=MODEL, max_tokens=1500,
            system=build_system_prompt(),
            tools=TOOL_SCHEMAS,
            messages=messages,
        )
        # Claude-un cavabını (mətn + alət çağırışları) tarixçəyə yaz
        messages.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})

        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")

        # Claude alət(lər) çağırmaq qərarına gəlib → icra et, nəticəni geri qaytar
        results = []
        for b in resp.content:
            if b.type == "tool_use":
                func = TOOL_FUNCS.get(b.name)
                try:
                    out = func(db, **b.input) if func else {"ok": False, "xeta": "Belə alət yoxdur."}
                except Exception as e:
                    out = {"ok": False, "xeta": f"Alət xətası: {e}"}
                if on_tool:
                    on_tool(b.name, b.input, out)
                results.append({"type": "tool_result", "tool_use_id": b.id,
                                "content": json.dumps(out, ensure_ascii=False)})
        messages.append({"role": "user", "content": results})

    return "Bağışlayın, sorğu çox addım tələb etdi. Zəhmət olmasa, daha sadə şəkildə yazın."
