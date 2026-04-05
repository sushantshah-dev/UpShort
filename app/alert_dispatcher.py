from __future__ import annotations

import json
import os
from urllib import error, request

from dotenv import load_dotenv
from flask import Flask, jsonify, request as flask_request


def _build_alert_embed(alert: dict) -> dict:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    status = str(alert.get("status", "unknown")).upper()
    severity = labels.get("severity", "unknown")
    alert_name = labels.get("alertname", "UnnamedAlert")
    description = annotations.get("description") or annotations.get("summary") or ""

    fields = []
    for name, value in (
        ("Severity", severity),
        ("Instance", labels.get("instance", "n/a")),
        ("Job", labels.get("job", "n/a")),
        ("Started", alert.get("startsAt", "n/a")),
        ("Ended", alert.get("endsAt", "n/a") if status == "RESOLVED" else "n/a"),
    ):
        fields.append({"name": name, "value": str(value), "inline": True})

    if alert.get("generatorURL"):
        fields.append(
            {
                "name": "Source",
                "value": alert["generatorURL"],
                "inline": False,
            }
        )

    return {
        "title": f"[{status}] {alert_name}",
        "description": description[:4096],
        "color": 15158332 if status == "FIRING" else 3066993,
        "fields": fields[:25],
    }


def build_discord_payload(payload: dict) -> dict:
    alerts = payload.get("alerts", [])
    status = str(payload.get("status", "unknown")).upper()
    content = f"{status}: {len(alerts)} alert(s) from Alertmanager"
    embeds = [_build_alert_embed(alert) for alert in alerts[:10]]
    return {"content": content[:2000], "embeds": embeds}


def send_discord_notification(
    payload: dict, webhook_url: str, timeout: float = 10.0
) -> None:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout):
        return


def create_alert_dispatcher_app() -> Flask:
    load_dotenv()

    app = Flask(__name__)

    @app.post("/alertmanager")
    def alertmanager_webhook():
        payload = flask_request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify({"error": "Expected a JSON object payload."}), 400

        webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
        if not webhook_url:
            return (
                jsonify({"error": "DISCORD_WEBHOOK_URL is not configured."}),
                503,
            )

        discord_payload = build_discord_payload(payload)
        try:
            send_discord_notification(discord_payload, webhook_url)
        except error.URLError as exc:
            return (
                jsonify(
                    {
                        "error": "Failed to deliver Discord notification.",
                        "details": str(exc.reason),
                    }
                ),
                502,
            )

        return jsonify({"status": "sent"}), 202

    return app


def main() -> None:
    app = create_alert_dispatcher_app()
    port = int(os.environ.get("ALERT_DISPATCHER_PORT", "9094"))
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
