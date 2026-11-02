"""A stand-in CRM with the three calls the workflow makes. It keeps everything in memory and records every call,
so tests (and a person running the n8n workflow by hand) can see exactly what was written.

Run: uvicorn mock_crm.app:app --port 8001
"""
from fastapi import FastAPI

app = FastAPI(title="mock CRM")
contacts, tasks, calls = {}, [], []


@app.post("/contacts/upsert")
def upsert(contact: dict):
    calls.append(("upsert", contact))
    key = next((cid for cid, c in contacts.items()
                if (contact.get("email") and (c.get("email") or "").lower() == contact["email"].lower())
                or (contact.get("phone") and c.get("phone") == contact["phone"])), None)
    created = key is None
    key = key or f"ct_{len(contacts) + 1:04d}"
    contacts[key] = {**contacts.get(key, {}), **contact}
    return {"contact_id": key, "created": created}


@app.post("/tasks")
def task(t: dict):
    calls.append(("task", t))
    tasks.append(t)
    return {"task_id": f"tk_{len(tasks):04d}"}


@app.get("/_calls")
def get_calls():
    return {"contacts": contacts, "tasks": tasks, "calls": calls}


@app.post("/_reset")
def reset():
    contacts.clear(), tasks.clear(), calls.clear()
    return {"ok": True}
