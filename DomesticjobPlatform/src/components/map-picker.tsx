/**
 * Cross-platform map picker (iOS & Android).
 * Renders the shared Leaflet / OpenStreetMap page inside a WebView.
 * The web implementation lives in map-picker.web.tsx.
 */
import React, { useCallback, useRef } from 'react';
import { WebView } from 'react-native-webview';
import type { WebViewProps } from 'react-native-webview';

import { MapPickerProps, MapCommand, useMapController } from './map-picker.shared';

/**
 * The imperative handle we use from the WebView. react-native-webview's
 * published types declare the component as a plain FunctionComponent without
 * a ref prop, so the handle is widened locally below — at runtime the
 * component does forward a ref exposing injectJavaScript().
 */
interface WebViewHandle {
  injectJavaScript: (js: string) => void;
}

const WebViewWithHandle = WebView as unknown as React.FC<
  WebViewProps & { ref?: React.Ref<WebViewHandle | null> }
>;

export default function MapPicker(props: MapPickerProps) {
  const webRef = useRef<WebViewHandle>(null);

  const dispatch = useCallback((cmd: MapCommand) => {
    const js =
      cmd.__mapCommand === 'setPin'
        ? `window.__setPin(${cmd.lat}, ${cmd.lng}, true); true;`
        : `window.__setRadius(${cmd.m}); true;`;
    webRef.current?.injectJavaScript(js);
  }, []);

  const { html, handleMessage } = useMapController({ ...props, dispatch });

  return (
    <WebViewWithHandle
      ref={webRef}
      source={{ html }}
      originWhitelist={['*']}
      javaScriptEnabled
      style={{ height: props.height ?? 220, backgroundColor: '#e8ecef' }}
      onMessage={(e) => {
        let msg: unknown = e.nativeEvent.data;
        if (typeof msg === 'string') {
          try {
            msg = JSON.parse(msg);
          } catch {
            return;
          }
        }
        handleMessage(msg);
      }}
    />
  );
}
