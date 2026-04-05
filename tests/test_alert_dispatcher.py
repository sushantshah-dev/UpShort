import unittest
from unittest.mock import patch
from urllib.error import URLError

from app.alert_dispatcher import build_discord_payload, create_alert_dispatcher_app


class AlertDispatcherTestCase(unittest.TestCase):
    def test_build_discord_payload_includes_alert_details(self):
        payload = {
            "status": "firing",
            "alerts": [
                {
                    "status": "firing",
                    "labels": {
                        "alertname": "HostLoadAboveNinetyPercent",
                        "severity": "warning",
                        "instance": "node-exporter:9100",
                        "job": "node-exporter",
                    },
                    "annotations": {
                        "summary": "Host load is above 90%",
                        "description": "Load has stayed above 90% for 2 minutes.",
                    },
                    "startsAt": "2026-04-05T10:00:00Z",
                    "generatorURL": "http://prometheus:9090/graph",
                }
            ],
        }

        discord_payload = build_discord_payload(payload)

        self.assertEqual(
            discord_payload["content"], "FIRING: 1 alert(s) from Alertmanager"
        )
        self.assertEqual(
            discord_payload["embeds"][0]["title"],
            "[FIRING] HostLoadAboveNinetyPercent",
        )
        self.assertEqual(
            discord_payload["embeds"][0]["description"],
            "Load has stayed above 90% for 2 minutes.",
        )

    def test_webhook_returns_503_when_discord_webhook_missing(self):
        app = create_alert_dispatcher_app()
        client = app.test_client()

        with patch("app.alert_dispatcher.os.environ", {}):
            response = client.post("/alertmanager", json={"alerts": []})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "DISCORD_WEBHOOK_URL is not configured.",
        )

    def test_webhook_forwards_alerts_to_discord(self):
        app = create_alert_dispatcher_app()
        client = app.test_client()

        with patch(
            "app.alert_dispatcher.os.environ",
            {"DISCORD_WEBHOOK_URL": "https://discord.example/webhook"},
        ):
            with patch("app.alert_dispatcher.send_discord_notification") as send_mock:
                response = client.post(
                    "/alertmanager",
                    json={"status": "resolved", "alerts": []},
                )

        self.assertEqual(response.status_code, 202)
        send_mock.assert_called_once()

    def test_webhook_returns_502_when_discord_delivery_fails(self):
        app = create_alert_dispatcher_app()
        client = app.test_client()

        with patch(
            "app.alert_dispatcher.os.environ",
            {"DISCORD_WEBHOOK_URL": "https://discord.example/webhook"},
        ):
            with patch(
                "app.alert_dispatcher.send_discord_notification",
                side_effect=URLError("boom"),
            ):
                response = client.post("/alertmanager", json={"alerts": []})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.get_json()["error"],
            "Failed to deliver Discord notification.",
        )
