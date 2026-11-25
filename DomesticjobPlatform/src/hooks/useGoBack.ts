import { useRouter } from 'expo-router';

/**
 * Safe back navigation — falls back to home if there is no history.
 * Also safe to call during SSR / before navigator mounts.
 */
export function useGoBack(fallback: string = '/') {
  const router = useRouter();

  return () => {
    try {
      if (router.canGoBack()) {
        router.back();
      } else {
        router.replace(fallback as any);
      }
    } catch {
      // navigator not mounted yet — no-op
    }
  };
}
