from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.core.llm_config import Settings


class PulpitoError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobRow:
    job_id: str
    status: str
    description: str
    machine: str
    os_type: str
    os_version: str
    failure_reason: str | None


def parse_run_name(user_input: str) -> str:
    s = user_input.strip()
    if not s:
        raise ValueError("Run name or URL is empty.")
    if s.startswith("http://") or s.startswith("https://"):
        parsed = urlparse(s)
        parts = [p for p in parsed.path.split("/") if p]
        if not parts:
            raise ValueError("URL path is empty; paste a Pulpito run URL.")
        if len(parts) >= 2 and parts[-1].isdigit():
            return parts[-2]
        return parts[0]
    s = s.strip("/")
    if "/" in s:
        parts = [p for p in s.split("/") if p]
        return parts[-1]
    return s


def run_variants_for_archive(run_name: str) -> list[str]:
    seen: list[str] = []
    for candidate in (run_name, run_name.replace(":", "_")):
        if candidate not in seen:
            seen.append(candidate)
    return seen


def fetch_run_jobs(client: httpx.Client, settings: Settings, run_name: str) -> list[JobRow]:
    url = f"{settings.pulpito_base.rstrip('/')}/{run_name}/"
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise PulpitoError(f"Pulpito returned {e.response.status_code} for {url}") from e
    except httpx.RequestError as e:
        raise PulpitoError(f"Failed to reach Pulpito: {e}") from e
    return parse_jobs_table(r.text)


def parse_jobs_table(html: str) -> list[JobRow]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id="run-job-table")
    if not table:
        return []
    tbody = table.find("tbody")
    if not tbody:
        return []
    jobs: list[JobRow] = []
    for tr in tbody.find_all("tr", recursive=False):
        classes = tr.get("class") or []
        if "tablesorter-childRow" in classes:
            continue
        if "job" not in classes:
            continue
        tds = {td.get("data-title"): td for td in tr.find_all("td", recursive=False)}
        status_el = tds.get("Status")
        job_el = tds.get("Job ID")
        if not status_el or not job_el:
            continue
        status = status_el.get_text(strip=True).lower()
        link = job_el.find("a", href=True)
        if not link:
            continue
        job_id = link.get_text(strip=True)
        if not job_id.isdigit():
            continue
        desc_el = tds.get("Description")
        description = desc_el.get_text(strip=True) if desc_el else ""
        machine_el = tds.get("Machine Type") or tds.get("Machine")
        machine = machine_el.get_text(strip=True) if machine_el else ""
        os_type_el = tds.get("OS Type")
        os_type = os_type_el.get_text(strip=True) if os_type_el else ""
        os_ver_el = tds.get("OS Version")
        os_version = os_ver_el.get_text(strip=True) if os_ver_el else ""

        failure: str | None = None
        nxt = tr.find_next_sibling("tr")
        if nxt and "tablesorter-childRow" in (nxt.get("class") or []):
            p = nxt.select_one("p.code-text")
            if p is not None:
                failure = unescape(p.get_text(strip=True))

        jobs.append(
            JobRow(
                job_id=job_id,
                status=status,
                description=description,
                machine=machine,
                os_type=os_type,
                os_version=os_version,
                failure_reason=failure,
            )
        )
    return jobs


def fetch_job_failure_reason(
    client: httpx.Client, settings: Settings, run_name: str, job_id: str
) -> str | None:
    url = f"{settings.pulpito_base.rstrip('/')}/{run_name}/{job_id}/"
    try:
        r = client.get(url, follow_redirects=True)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    soup = BeautifulSoup(r.text, "html.parser")
    for h4 in soup.find_all("h4"):
        text = h4.get_text(strip=True)
        if re.search(r"failure\s*reason", text, re.I):
            nxt = h4.find_next_sibling("p", class_=re.compile(r"code-text"))
            if nxt:
                return unescape(nxt.get_text(strip=True))
    return None


def status_counts(jobs: list[JobRow]) -> dict[str, int]:
    out: dict[str, int] = {}
    for j in jobs:
        out[j.status] = out.get(j.status, 0) + 1
    return out
