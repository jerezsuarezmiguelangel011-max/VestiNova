"""Identificación explícita de fixtures históricos, sin cambiar compras de otros módulos."""
DEMO_HISTORY_ORIGIN = "VESTINOVA_CU22_DEMO_V1"
DEMO_CASH_ORIGIN = "VESTINOVA_CU20_CAJA_DEMO"


def purchase_origin(records):
    unique = {record.id: record for record in records}
    demo = sum((record.contexto or {}).get("origen") in {DEMO_HISTORY_ORIGIN, DEMO_CASH_ORIGIN} for record in unique.values())
    return {"demostracion": demo > 0, "compras_demo": demo, "compras_operativas": len(unique)-demo}
