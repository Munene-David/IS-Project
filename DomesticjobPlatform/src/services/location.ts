/**
 * One-shot device location capture — used ONLY at check-in / finish events.
 * The app never tracks location in the background.
 *
 * Thin wrapper around expo-location (bundled in Expo Go, works on web via
 * the browser Geolocation API too).
 */
import * as Location from 'expo-location';

import { LocationSnapshot } from './api';

/** Ask for (or check) foreground location permission. */
export async function requestLocationPermission(): Promise<boolean> {
  try {
    const { status } = await Location.requestForegroundPermissionsAsync();
    return status === 'granted';
  } catch {
    return false;
  }
}

/**
 * Capture a single high-accuracy position snapshot.
 * Throws when the position cannot be read (permission off, GPS off…).
 */
export async function getCurrentLocationSnapshot(): Promise<LocationSnapshot> {
  const pos = await Location.getCurrentPositionAsync({
    accuracy: Location.Accuracy.High,
  });
  // Android reports mocked/simulated GPS fixes on the location object.
  const mocked = (pos as { mocked?: boolean }).mocked === true;
  return {
    lat: pos.coords.latitude,
    lng: pos.coords.longitude,
    accuracy_m: pos.coords.accuracy ?? null,
    device_time: new Date(pos.timestamp).toISOString(),
    mock_location: mocked,
  };
}
