/**
 * Web implementation of the map picker.
 * Renders the shared Leaflet / OpenStreetMap page in an iframe and talks
 * to it with postMessage. The iOS/Android implementation lives in
 * map-picker.tsx.
 */
import React, { useCallback, useEffect, useRef } from 'react';

import { MapPickerProps, MapCommand, useMapController } from './map-picker.shared';

export default function MapPicker(props: MapPickerProps) {
  const iframeRef = useRef<HTMLIFrameElement>(null);

  const dispatch = useCallback((cmd: MapCommand) => {
    iframeRef.current?.contentWindow?.postMessage(cmd, '*');
  }, []);

  const { html, handleMessage } = useMapController({ ...props, dispatch });

  useEffect(() => {
    const onWindowMessage = (ev: MessageEvent) => {
      if (ev.source !== iframeRef.current?.contentWindow) return;
      handleMessage(ev.data);
    };
    window.addEventListener('message', onWindowMessage);
    return () => window.removeEventListener('message', onWindowMessage);
  }, [handleMessage]);

  return (
    <iframe
      ref={iframeRef}
      srcDoc={html}
      title="Map"
      style={{
        width: '100%',
        height: props.height ?? 220,
        border: 'none',
        borderRadius: 8,
        display: 'block',
      }}
    />
  );
}
