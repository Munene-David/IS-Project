/**
 * Shared types & the Leaflet / OpenStreetMap HTML generator for the map
 * components.  Used by both the native (iOS/Android WebView) and web
 * (iframe) implementations.
 *
 * Free map stack — Leaflet + OpenStreetMap tiles, no API key required.
 *
 * The generated page talks to the host app two ways:
 *   - outgoing: `postMessage` (React Native WebView) or
 *     `parent.postMessage` (web iframe), tagged with `__mapMessage`
 *   - incoming: the host either injects `window.__setPin() / __setRadius()`
 *     directly (native) or posts `{__mapCommand: ...}` objects (web iframe)
 */

import { useCallback, useEffect, useRef, useState } from 'react';

export interface MapPin {
  lat: number;
  lng: number;
}

export interface ExtraMarker {
  lat: number;
  lng: number;
  /** Tooltip text (e.g. "ARRIVAL · 132 m · LOW_ACCURACY"). */
  label: string;
  /** CSS colour for the dot (defaults to a neutral blue). */
  color?: string;
}

export interface MapPickerProps {
  /** Controlled pin position (null = no pin placed yet). */
  pin: MapPin | null;
  /** Fired when the user drags the pin or taps the map. */
  onPinChange?: (pin: MapPin) => void;
  /** Geofence radius (metres) drawn as a circle around the pin. */
  geofenceRadiusM?: number | null;
  /** Read-only map: pin fixed, taps ignored. */
  readOnly?: boolean;
  /** Extra fixed dot markers (e.g. student check-ins in the audit view). */
  markers?: ExtraMarker[];
  /** Map height in px (default 220). */
  height?: number;
}

/** Nairobi CBD — sensible initial view for a Kenyan marketplace. */
export const DEFAULT_CENTER: MapPin = { lat: -1.286389, lng: 36.817223 };

/** Embed a value as a JSON literal inside a <script> tag, safely. */
function jsonForScript(value: unknown): string {
  return JSON.stringify(value).replace(/</g, '\\u003c');
}

/**
 * Build the self-contained Leaflet map page.
 */
export function buildMapHtml(opts: {
  pin: MapPin | null;
  geofenceRadiusM?: number | null;
  readOnly?: boolean;
  markers?: ExtraMarker[];
}): string {
  const data = {
    pin: opts.pin,
    geofenceRadiusM: opts.geofenceRadiusM ?? null,
    readOnly: opts.readOnly ?? false,
    markers: opts.markers ?? [],
    center: DEFAULT_CENTER,
  };

  return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
  html, body { margin: 0; padding: 0; height: 100%; overflow: hidden; }
  #map { height: 100%; width: 100%; background: #e8ecef; }
  .pin-icon { font-size: 30px; line-height: 32px; text-align: center;
              filter: drop-shadow(0 2px 2px rgba(0,0,0,.35)); }
  .leaflet-tooltip { font-size: 11px; }
</style>
</head>
<body>
<div id="map"></div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
(function () {
  var DATA = ${jsonForScript(data)};

  var map = L.map('map', { zoomControl: false });
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
  }).addTo(map);

  var start = DATA.pin ? [DATA.pin.lat, DATA.pin.lng] : [DATA.center.lat, DATA.center.lng];
  map.setView(start, DATA.pin ? 16 : 12);

  function send(msg) {
    msg.__mapMessage = true;
    if (window.ReactNativeWebView && window.ReactNativeWebView.postMessage) {
      window.ReactNativeWebView.postMessage(JSON.stringify(msg));
    } else if (window.parent && window.parent !== window) {
      window.parent.postMessage(msg, '*');
    }
  }

  var marker = null;
  var circle = null;

  function ensureCircle(latlng) {
    if (!circle) {
      circle = L.circle(latlng, {
        radius: DATA.geofenceRadiusM || 0,
        color: '#2563eb', weight: 1.5, fillColor: '#3b82f6', fillOpacity: 0.08
      }).addTo(map);
    }
    return circle;
  }

  function createMarker(latlng) {
    var m = L.marker(latlng, {
      draggable: !DATA.readOnly,
      icon: L.divIcon({
        className: '',
        html: '<div class="pin-icon">📍</div>',
        iconSize: [30, 32],
        iconAnchor: [15, 30]
      })
    }).addTo(map);
    if (!DATA.readOnly) {
      m.on('drag', function () { if (circle) circle.setLatLng(m.getLatLng()); });
      m.on('dragend', function () {
        var p = m.getLatLng();
        send({ type: 'pin', lat: p.lat, lng: p.lng });
      });
    }
    return m;
  }

  if (DATA.pin) {
    marker = createMarker(start);
    if (!DATA.readOnly) {
      map.on('click', function (e) {
        marker.setLatLng(e.latlng);
        if (circle) circle.setLatLng(e.latlng);
        send({ type: 'pin', lat: e.latlng.lat, lng: e.latlng.lng });
      });
    }
  }
  if (DATA.geofenceRadiusM) {
    ensureCircle(start);
  }

  // Extra fixed dot markers (check-in points etc.)
  (DATA.markers || []).forEach(function (mk) {
    var icon = L.divIcon({
      className: '',
      html: '<div style="width:13px;height:13px;border-radius:50%;background:' +
            (mk.color || '#2563eb') +
            ';border:2px solid #fff;box-shadow:0 1px 3px rgba(0,0,0,.45)"></div>',
      iconSize: [13, 13],
      iconAnchor: [7, 7]
    });
    L.marker([mk.lat, mk.lng], { icon: icon })
      .addTo(map)
      .bindTooltip(mk.label, { direction: 'top' });
  });

  // --- Commands from the host app ---------------------------------------
  window.__setPin = function (lat, lng, pan) {
    if (!marker) {
      marker = createMarker([lat, lng]);
      if (!DATA.readOnly) {
        map.on('click', function (e) {
          marker.setLatLng(e.latlng);
          if (circle) circle.setLatLng(e.latlng);
          send({ type: 'pin', lat: e.latlng.lat, lng: e.latlng.lng });
        });
      }
    }
    marker.setLatLng([lat, lng]);
    if (circle) circle.setLatLng([lat, lng]);
    if (pan) map.setView([lat, lng], Math.max(map.getZoom(), 16));
  };

  window.__setRadius = function (m) {
    if (m && marker) { ensureCircle(marker.getLatLng()).setRadius(m); }
    else if (m) { ensureCircle(map.getCenter()).setRadius(m); }
    else if (circle) { map.removeLayer(circle); circle = null; }
  };

  window.addEventListener('message', function (ev) {
    var d = ev.data;
    if (!d || !d.__mapCommand) return;
    if (d.__mapCommand === 'setPin') window.__setPin(d.lat, d.lng, true);
    if (d.__mapCommand === 'setRadius') window.__setRadius(d.m);
  });

  // --- Ready -------------------------------------------------------------
  function resize() { map.invalidateSize(); }
  setTimeout(resize, 200);
  setTimeout(resize, 800);
  send({ type: 'ready' });
})();
</script>
</body>
</html>`;
}

/** Command sent from the host app into the map page. */
export type MapCommand =
  | { __mapCommand: 'setPin'; lat: number; lng: number }
  | { __mapCommand: 'setRadius'; m: number };

/**
 * Controller shared by the native and web map implementations.
 *
 * Owns the page HTML (built once from the initial props, so dragging never
 * reloads the map), pushes later pin/radius changes into the page as
 * commands, and normalises the incoming event stream.
 *
 * `dispatch` is platform-specific: injectJavaScript on native,
 * postMessage into the iframe on web.
 */
export function useMapController(
  props: MapPickerProps & { dispatch: (cmd: MapCommand) => void },
) {
  const { pin, geofenceRadiusM, onPinChange, readOnly, markers, dispatch } = props;

  const readyRef = useRef(false);
  const pendingRef = useRef<MapCommand | null>(null);
  /** Last pin reported by the map itself (drag/tap) — suppresses echo. */
  const lastFromMapRef = useRef<MapPin | null>(null);
  const onPinChangeRef = useRef(onPinChange);
  useEffect(() => { onPinChangeRef.current = onPinChange; }, [onPinChange]);

  const [html, setHtml] = useState(() =>
    buildMapHtml({ pin, geofenceRadiusM, readOnly, markers }),
  );
  const builtPinRef = useRef(pin);

  const send = useCallback(
    (cmd: MapCommand) => {
      if (readyRef.current) dispatch(cmd);
      else pendingRef.current = cmd;
    },
    [dispatch],
  );

  /** Feed a raw event (parsed JSON object) from the map page. */
  const handleMessage = useCallback(
    (msg: unknown) => {
      const m = msg as Record<string, any> | null;
      if (!m || !m.__mapMessage) return;
      if (m.type === 'ready') {
        readyRef.current = true;
        const pending = pendingRef.current;
        pendingRef.current = null;
        if (pending) dispatch(pending);
      } else if (m.type === 'pin') {
        const p = { lat: m.lat as number, lng: m.lng as number };
        lastFromMapRef.current = p;
        onPinChangeRef.current?.(p);
      }
    },
    [dispatch],
  );

  // A pin arriving after the page was built without one (async task data) —
  // rebuild once so the map opens directly centred on the pin.
  useEffect(() => {
    if (builtPinRef.current === null && pin) {
      builtPinRef.current = pin;
      readyRef.current = false;
      lastFromMapRef.current = null;
      setHtml(buildMapHtml({ pin, geofenceRadiusM, readOnly, markers }));
    }
  }, [pin, geofenceRadiusM, readOnly, markers]);

  // External pin updates (search result / current location) → move marker.
  // Skips changes that originated from the map itself (drag / tap).
  useEffect(() => {
    if (!pin) return;
    const last = lastFromMapRef.current;
    if (last && last.lat === pin.lat && last.lng === pin.lng) return;
    send({ __mapCommand: 'setPin', lat: pin.lat, lng: pin.lng });
  }, [pin, send]);

  // Geofence radius updates → redraw circle.
  useEffect(() => {
    if (geofenceRadiusM == null) return;
    send({ __mapCommand: 'setRadius', m: geofenceRadiusM });
  }, [geofenceRadiusM, send]);

  return { html, handleMessage };
}
