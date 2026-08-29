#!/usr/bin/env python3
"""Aggregate security-scan reports into a single `vulnerabilities.md`.

Reads the report directory produced by the security-scan workflow:
  - gitleaks.json        (secrets; may be SARIF or the gitleaks-cli JSON)
  - pip-audit.json       (Python dependency vulnerabilities)
  - npm-audit.json       (JS dependency vulnerabilities)
  - trivy-image.json     (Docker image vulns + embedded secrets)

Usage: python aggregate_vulns.py <reports-dir> > vulnerabilities.md
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Always emit UTF-8 regardless of runner locale.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")


def load(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing/corrupt report should not fail the scan
        return None


def extract_gitleaks(data) -> list[dict]:
    findings = []
    if data is None:
        return findings
    # SARIF layout (gitleaks-action v3) -> runs[].tool.driver.rules + results[]
    if isinstance(data, dict) and data.get("version") and "runs" in data:
        rule_map = {}
        for run in data.get("runs", []):
            for rule in run.get("tool", {}).get("driver", {}).get("rules", []):
                rule_map[rule.get("id")] = rule.get("shortDescription", {}).get("text", rule.get("id"))
            for res in run.get("results", []):
                loc = (res.get("locations") or [{}])[0].get("physicalLocation", {})
                findings.append({
                    "kind": "secret",
                    "id": res.get("ruleId"),
                    "title": f"Secret: {rule_map.get(res.get('ruleId'), res.get('ruleId'))}",
                    "path": loc.get("artifactLocation", {}).get("uri"),
                    "line": (loc.get("region") or {}).get("startLine"),
                    "detail": (res.get("message") or {}).get("text", ""),
                })
    # gitleaks-cli json: [ {RuleID, File, StartLine, Secret, Match, Description} ]
    elif isinstance(data, list):
        for r in data:
            findings.append({
                "kind": "secret",
                "id": r.get("RuleID"),
                "title": f"Secret: {r.get('Description') or r.get('RuleID')}",
                "path": r.get("File"),
                "line": r.get("StartLine"),
                "detail": (r.get("Secret") or "")[:40],
            })
    return findings


def extract_pip(data) -> list[dict]:
    findings = []
    if data is None:
        return findings
    deps = data.get("dependencies", []) if isinstance(data, dict) else []
    for d in deps:
        for v in d.get("vulns", []):
            findings.append({
                "kind": "dependency",
                "ecosystem": "pip",
                "id": v.get("id"),
                "title": v.get("description", v.get("id", "vulnerability")),
                "path": "backend/requirements.txt",
                "line": None,
                "detail": f"{d.get('name')} {d.get('version', '')} -> {v.get('fix_versions', [])}",
            })
    return findings


def extract_npm(data) -> list[dict]:
    findings = []
    if data is None:
        return findings
    if data.get("vulnerabilities"):
        for name, v in data["vulnerabilities"].items():
            severity = v.get("severity", "info")
            for via in v.get("via", []):
                if isinstance(via, dict):
                    findings.append({
                        "kind": "dependency",
                        "ecosystem": "npm",
                        "id": via.get("title", name),
                        "title": via.get("title", name),
                        "path": "web/package-lock.json",
                        "line": None,
                        "detail": f"{name} ({v.get('range', '')}) [{severity}] fix: {via.get('fixAvailable', 'n/a')}",
                    })
    return findings


def extract_trivy(data) -> list[dict]:
    findings = []
    if data is None:
        return findings
    for res in data.get("Results", []):
        target = res.get("Target", "")
        klass = res.get("Class", "")
        # container-package / library vulnerabilities
        for v in res.get("Vulnerabilities", []):
            findings.append({
                "kind": "image",
                "ecosystem": f"oryx/{klass or v.get('PkgName')}",
                "id": v.get("VulnerabilityID"),
                "title": f"{v.get('VulnerabilityID')}: {v.get('Title', '')}".strip()[:200],
                "path": target,
                "line": None,
                "detail": (f"{v.get('PkgName')} {v.get('InstalledVersion')} -> "
                           f"{v.get('FixedVersion') or 'not fixed'} [severity: {v.get('Severity')}]"),
            })
        # embedded secrets found in the image filesystem
        for s in res.get("Secrets", []):
            findings.append({
                "kind": "image-secret",
                "ecosystem": "trivy-secret",
                "id": s.get("RuleID"),
                "title": f"Image secret: {s.get('Title') or s.get('RuleID')}",
                "path": target,
                "line": s.get("StartLine"),
                "detail": (s.get("Match") or "")[:60],
            })
    return findings


SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def severity_of(f: dict) -> int:
    sev = (f.get("detail") or "").lower() + " " + (f.get("title") or "").lower()
    for k in ("critical", "high", "medium", "low"):
        if k in sev:
            return SEVERITY_ORDER[k]
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: aggregate_vulns.py <reports-dir>", file=sys.stderr)
        return 2
    rd = Path(sys.argv[1])
    out = sys.stdout

    findings = []
    findings += extract_gitleaks(load(rd / "gitleaks.json"))
    findings += extract_pip(load(rd / "pip-audit.json"))
    findings += extract_npm(load(rd / "npm-audit.json"))
    findings += extract_trivy(load(rd / "trivy-image.json"))

    findings.sort(key=lambda f: (-severity_of(f), f.get("kind", ""), f.get("path", "")))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    counts = {}
    for f in findings:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1

    print("# Vulnerability scan report", file=out)
    print("", file=out)
    print(f"_Generated {now}_  ", file=out)
    print(file=out)
    print(f"**Total findings: {len(findings)}**", file=out)
    if counts:
        detail = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
        print(f"_Breakdown — {detail}_", file=out)
    print(file=out)

    if not findings:
        print("No vulnerabilities or leaked secrets found. \N{white heavy check mark}", file=out)
        return 0

    by_kind = {}
    for f in findings:
        by_kind.setdefault(f["kind"], []).append(f)

    header = {
        "secret": "Secrets in repository",
        "image-secret": "Secrets in image",
        "dependency": "Dependency vulnerabilities",
        "image": "Docker image vulnerabilities",
    }

    for kind, rows in by_kind.items():
        print(f"## {header.get(kind, kind)} ({len(rows)})", file=out)
        print(file=out)
        print("| Severity | ID | Package / Path | Detail |", file=out)
        print("| --- | --- | --- | --- |", file=out)
        sev = {
            "secret": "critical", "image-secret": "critical",
            "dependency": "high", "image": "high",
        }
        for f in rows:
            pkg = f.get("path") or (f.get("ecosystem") or "")
            print(f"| {sev.get(kind,'')} | {f.get('id','')} | `{pkg}` | {f.get('detail','').replace('|','\\|')} |", file=out)
        print(file=out)

    print("", file=out)
    print("_Run the `Security scan` workflow to regenerate. Reports are also uploaded as artifacts._", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
