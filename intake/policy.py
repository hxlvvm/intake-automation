"""The practice's knowledge base: versioned policy documents with effective dates.

Each file in kb/ is Markdown a person can read, with front matter (id, version, effective_from) and one ```json
block the code reads. A decision always uses the version in force on the submission date, and cites it.
"""
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

KB_DIR = Path(__file__).resolve().parent.parent / "kb"


@dataclass(frozen=True)
class Policy:
    id: str
    version: int
    effective_from: date
    rules: dict

    @property
    def cite(self):
        return f"{self.id}@v{self.version}"


def parse(text):
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        raise ValueError("policy file has no front matter")
    meta = dict(line.split(":", 1) for line in m.group(1).splitlines())
    meta = {k.strip(): v.strip() for k, v in meta.items()}
    block = re.search(r"```json\n(.*?)\n```", text, re.S)
    if not block:
        raise ValueError(f"policy {meta.get('id')} has no json block")
    return Policy(meta["id"], int(meta["version"]), date.fromisoformat(meta["effective_from"]), json.loads(block.group(1)))


def load(kb_dir=KB_DIR):
    return [parse(p.read_text()) for p in sorted(Path(kb_dir).glob("*.md"))]


def current(policies, policy_id, on):
    """The version of `policy_id` in force on date `on`."""
    live = [p for p in policies if p.id == policy_id and p.effective_from <= on]
    if not live:
        raise LookupError(f"no version of {policy_id} in force on {on}")
    return max(live, key=lambda p: p.effective_from)
