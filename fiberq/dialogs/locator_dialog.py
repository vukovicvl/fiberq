# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Locator Dialog.

This module contains the dialog for finding addresses on map using OSM Nominatim.

v1.2.2: switched geocoding request from urllib.request.urlopen to QGIS-native
QgsBlockingNetworkRequest to eliminate Bandit B310 warnings on repo scan and
to use QGIS's own proxy/SSL configuration.
"""

import json

from qgis.PyQt.QtWidgets import (  # noqa: F401  (QLabel kept for backward compatibility with external imports)
    QDialog,
    QVBoxLayout,
    QLineEdit,
    QLabel,
    QDialogButtonBox,
    QFormLayout,
    QPushButton,
    QMessageBox,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkRequest
from qgis.core import QgsBlockingNetworkRequest

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


def _http_get_json(url, user_agent, timeout_ms=15000):
    """Perform an HTTPS GET using QGIS's native network stack and return parsed JSON.

    This avoids urllib.request.urlopen entirely, which eliminates Bandit B310
    warnings on the QGIS repository security scan. The URL scheme is still
    validated defensively before the request is issued.

    Args:
        url: Absolute http(s) URL.
        user_agent: User-Agent header value (bytes or str).
        timeout_ms: Network timeout in milliseconds.

    Returns:
        Parsed JSON payload (list or dict).

    Raises:
        ValueError: If the URL scheme is not http or https.
        RuntimeError: If the network request fails.
    """
    # Defensive scheme check (block file://, ftp://, custom schemes, etc.)
    if not (url.startswith("https://") or url.startswith("http://")):
        raise ValueError("Only http/https URLs are allowed")

    request = QNetworkRequest(QUrl(url))
    ua = user_agent.encode("utf-8") if isinstance(user_agent, str) else user_agent
    request.setRawHeader(b"User-Agent", ua)

    blocking = QgsBlockingNetworkRequest()
    try:
        blocking.setTimeout(timeout_ms)
    except Exception:
        # setTimeout was added later; ignore on old QGIS builds
        pass

    err = blocking.get(request, forceRefresh=True)
    if err != QgsBlockingNetworkRequest.NoError:
        raise RuntimeError(blocking.errorMessage() or "Network request failed")

    reply = blocking.reply()
    payload = bytes(reply.content())
    if not payload:
        return []
    return json.loads(payload.decode("utf-8"))


class LocatorDialog(QDialog):
    """Dialog for entering address and positioning on map (OSM Nominatim)."""

    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Locator - Find Address on Map")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.edit_country = QLineEdit()
        self.edit_city = QLineEdit()
        self.edit_municipality = QLineEdit()
        self.edit_street = QLineEdit()
        self.edit_number = QLineEdit()

        form.addRow("Country:", self.edit_country)
        form.addRow("City:", self.edit_city)
        form.addRow("Municipality (optional):", self.edit_municipality)
        form.addRow("Street:", self.edit_street)
        form.addRow("Number:", self.edit_number)
        layout.addLayout(form)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.btn_find = QPushButton("Find on map")
        btns.addButton(self.btn_find, QDialogButtonBox.ButtonRole.ActionRole)
        self.btn_find.clicked.connect(self._on_find_clicked)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _on_find_clicked(self):
        """Handle find button click - geocode the address."""
        # Build query
        s = self.edit_street.text().strip()
        n = self.edit_number.text().strip()
        parts = []
        if s:
            parts.append(s + (f" {n}" if n else ""))

        m = self.edit_municipality.text().strip()
        if m:
            parts.append(m)

        c = self.edit_city.text().strip()
        if c:
            parts.append(c)

        co = self.edit_country.text().strip()
        if co:
            parts.append(co)

        if not parts:
            QMessageBox.warning(
                self,
                "Locator",
                "Please enter at least City and Country (Street/Number recommended).",
            )
            return

        query = ", ".join(parts)

        # Geocode via OSM Nominatim using QGIS's native network stack.
        try:
            from urllib.parse import quote
            url = (
                "https://nominatim.openstreetmap.org/search?format=json&limit=1&q="
                + quote(query)  # noqa: W503
            )
            data = _http_get_json(
                url,
                user_agent="FiberQ/1.0 (contact: vukovicvl@fiberq.net)",
                timeout_ms=15000,
            )

            if not data:
                QMessageBox.information(
                    self, "Locator", f"No location found for: {query}"
                )
                return

            lat = float(data[0].get("lat"))
            lon = float(data[0].get("lon"))
            self.core._center_and_mark_wgs84(lon, lat, label=query)
            self.accept()
        except Exception as e:
            logger.warning(f"Geocoding failed: {e}")
            QMessageBox.critical(self, "Error", f"Error during geocoding: {e}")


__all__ = ['LocatorDialog']
