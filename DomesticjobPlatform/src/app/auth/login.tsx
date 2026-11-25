import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';

export default function LoginScreen() {
  const router = useRouter();
  const { login } = useAuth();

  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [selectedRole, setSelectedRole] = useState<'STUDENT' | 'HOUSEHOLD'>('STUDENT');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async () => {
    if (!identifier.trim() || !password.trim()) {
      setError('Please enter your email/username and password');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await login(identifier.trim(), password);
      router.replace('/');
    } catch (err: any) {
      setError(err.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  const fillDemo = (role: 'STUDENT' | 'HOUSEHOLD') => {
    if (role === 'STUDENT') {
      setIdentifier('jane_w');
      setPassword('Jane1234!');
      setSelectedRole('STUDENT');
    } else {
      setIdentifier('sarah_m');
      setPassword('Sarah1234!');
      setSelectedRole('HOUSEHOLD');
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.card}>
          <Text style={styles.headerTitle}>Task Marketplace</Text>
          <Text style={styles.subTitle}>Domestic Job & Escrow Platform</Text>

          <View style={styles.tabRow}>
            <TouchableOpacity style={[styles.tabButton, styles.tabActive]}>
              <Text style={styles.tabTextActive}>Login</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.tabButton}
              onPress={() =>
                selectedRole === 'STUDENT'
                  ? router.push('/auth/register-student' as any)
                  : router.push('/auth/register-household' as any)
              }>
              <Text style={styles.tabText}>Register</Text>
            </TouchableOpacity>
          </View>

          {error && <Text style={styles.errorText}>{error}</Text>}

          <View style={styles.formGroup}>
            <Text style={styles.label}>Email or Username</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. jane_w or sarah@example.com"
              placeholderTextColor="#999"
              autoCapitalize="none"
              value={identifier}
              onChangeText={setIdentifier}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Password</Text>
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              placeholderTextColor="#999"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>I am a:</Text>
            <View style={styles.roleRow}>
              <TouchableOpacity
                style={[
                  styles.roleBadge,
                  selectedRole === 'STUDENT' && styles.roleBadgeActive,
                ]}
                onPress={() => setSelectedRole('STUDENT')}>
                <Text
                  style={[
                    styles.roleBadgeText,
                    selectedRole === 'STUDENT' && styles.roleBadgeTextActive,
                  ]}>
                  University Student
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[
                  styles.roleBadge,
                  selectedRole === 'HOUSEHOLD' && styles.roleBadgeActive,
                ]}
                onPress={() => setSelectedRole('HOUSEHOLD')}>
                <Text
                  style={[
                    styles.roleBadgeText,
                    selectedRole === 'HOUSEHOLD' && styles.roleBadgeTextActive,
                  ]}>
                  Household Owner
                </Text>
              </TouchableOpacity>
            </View>
          </View>

          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleLogin}
            disabled={loading}>
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryButtonText}>Continue</Text>
            )}
          </TouchableOpacity>

          <View style={styles.divider} />

          <Text style={styles.captionText}>
            New user? Register with university ID (Students) or address verification (Household Owners):
          </Text>

          <View style={styles.registerLinks}>
            <TouchableOpacity
              onPress={() => router.push('/auth/register-student' as any)}
              style={styles.linkButton}>
              <Text style={styles.linkButtonText}>+ Register as Student</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => router.push('/auth/register-household' as any)}
              style={styles.linkButton}>
              <Text style={styles.linkButtonText}>+ Register as Household</Text>
            </TouchableOpacity>
          </View>

          <View style={styles.divider} />

          <Text style={styles.demoLabel}>Demo Quick Login:</Text>
          <View style={styles.demoRow}>
            <TouchableOpacity
              style={styles.demoBtn}
              onPress={() => fillDemo('STUDENT')}>
              <Text style={styles.demoBtnText}>Fill Demo Student</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={styles.demoBtn}
              onPress={() => fillDemo('HOUSEHOLD')}>
              <Text style={styles.demoBtnText}>Fill Demo Household</Text>
            </TouchableOpacity>
          </View>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#F5F6F8',
  },
  scroll: {
    padding: 24,
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: '100%',
  },
  card: {
    backgroundColor: '#FFFFFF',
    borderRadius: 16,
    padding: 24,
    width: '100%',
    maxWidth: 440,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    elevation: 3,
  },
  headerTitle: {
    fontSize: 24,
    fontWeight: '700',
    color: '#1A1D20',
    textAlign: 'center',
  },
  subTitle: {
    fontSize: 13,
    color: '#656D76',
    textAlign: 'center',
    marginBottom: 20,
    marginTop: 4,
  },
  tabRow: {
    flexDirection: 'row',
    backgroundColor: '#EFEFEF',
    borderRadius: 8,
    padding: 4,
    marginBottom: 20,
  },
  tabButton: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 6,
  },
  tabActive: {
    backgroundColor: '#FFFFFF',
  },
  tabText: {
    fontSize: 14,
    color: '#656D76',
    fontWeight: '500',
  },
  tabTextActive: {
    fontSize: 14,
    color: '#0969DA',
    fontWeight: '600',
  },
  errorText: {
    color: '#CF222E',
    backgroundColor: '#FFEBE9',
    padding: 10,
    borderRadius: 8,
    fontSize: 13,
    marginBottom: 14,
  },
  formGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#24292F',
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    backgroundColor: '#FAFAFA',
    color: '#1F2328',
  },
  roleRow: {
    flexDirection: 'row',
    gap: 8,
  },
  roleBadge: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
    backgroundColor: '#F6F8FA',
  },
  roleBadgeActive: {
    borderColor: '#0969DA',
    backgroundColor: '#DDF4FF',
  },
  roleBadgeText: {
    fontSize: 13,
    color: '#57606A',
  },
  roleBadgeTextActive: {
    color: '#0969DA',
    fontWeight: '600',
  },
  primaryButton: {
    backgroundColor: '#1F883D',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 8,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '600',
  },
  divider: {
    height: 1,
    backgroundColor: '#E1E4E8',
    marginVertical: 18,
  },
  captionText: {
    fontSize: 12,
    color: '#57606A',
    lineHeight: 16,
    textAlign: 'center',
    marginBottom: 12,
  },
  registerLinks: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    gap: 8,
  },
  linkButton: {
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  linkButtonText: {
    color: '#0969DA',
    fontSize: 13,
    fontWeight: '600',
  },
  demoLabel: {
    fontSize: 12,
    color: '#656D76',
    fontWeight: '600',
    marginBottom: 8,
    textAlign: 'center',
  },
  demoRow: {
    flexDirection: 'row',
    gap: 8,
  },
  demoBtn: {
    flex: 1,
    backgroundColor: '#F6F8FA',
    borderWidth: 1,
    borderColor: '#D0D7DE',
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
  },
  demoBtnText: {
    fontSize: 12,
    color: '#24292F',
  },
});
