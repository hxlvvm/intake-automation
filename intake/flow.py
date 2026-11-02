"""The same steps as n8n/intake_workflow.json, in Python, so the whole flow is tested end to end:

    webhook -> POST /decide -> POST CRM /contacts/upsert -> (if a task) POST CRM /tasks -> respond with the route
"""
import httpx


def run(form: dict, service: httpx.Client, crm: httpx.Client) -> dict:
    d = service.post("/decide", json=form)
    d.raise_for_status()
    d = d.json()
    contact = crm.post("/contacts/upsert", json={**d["crm"]["contact"], "stage": d["crm"]["stage"]})
    contact.raise_for_status()
    contact_id = contact.json()["contact_id"]
    if d["crm"]["task"]:
        crm.post("/tasks", json={"contact_id": contact_id, "text": d["crm"]["task"]}).raise_for_status()
    return {"route": d["route"], "contact_id": contact_id}
