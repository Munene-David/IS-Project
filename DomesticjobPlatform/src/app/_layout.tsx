import { DarkTheme, DefaultTheme, ThemeProvider } from 'expo-router';
import { Stack, useRouter, useSegments } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect } from 'react';
import { useColorScheme } from 'react-native';

import { AuthProvider, useAuth } from '@/context/AuthContext';

SplashScreen.preventAutoHideAsync();

function AuthGate() {
  const { user, isLoading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (isLoading) return;
    const inAuthGroup = segments[0] === 'auth';
    if (!user && !inAuthGroup) {
      router.replace('/auth/login' as any);
    } else if (user && inAuthGroup) {
      router.replace('/' as any);
    }
  }, [user, isLoading, segments]);

  useEffect(() => {
    if (!isLoading) SplashScreen.hideAsync();
  }, [isLoading]);

  return null;
}

function NavigatorStack() {
  const colorScheme = useColorScheme();
  return (
    <ThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
      <AuthGate />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="index" />
        <Stack.Screen name="auth/login" />
        <Stack.Screen name="auth/register-student" />
        <Stack.Screen name="auth/register-household" />
        <Stack.Screen name="tasks/index" />
        <Stack.Screen name="tasks/[id]" />
        <Stack.Screen name="tasks/create" />
        <Stack.Screen name="messages/[taskId]" />
        <Stack.Screen name="ratings/create" />
        <Stack.Screen name="my-bids" />
        <Stack.Screen name="payments/initiate" />
        <Stack.Screen name="notifications" />
      </Stack>
    </ThemeProvider>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <NavigatorStack />
    </AuthProvider>
  );
}
