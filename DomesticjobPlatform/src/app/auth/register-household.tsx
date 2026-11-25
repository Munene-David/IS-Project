import React, { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';

export default function RegisterHouseholdScreen() {
  const router = useRouter();
  const { registerHousehold } = useAuth();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [phoneNumber, setPhoneNumber] = useState('');
  const [address, setAddress] = useState('');

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRegister = async () => {
    if (!username || !email || !password || !phoneNumber || !address) {
      setError('Please fill in all required fields including your address.');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await registerHousehold({
        username: username.trim(),
        email: email.trim(),
        password,
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim(),
        address: address.trim(),
        location_lat: -1.2921,
        location_lng: 36.7856,
      });
      // AuthGate in _layout.tsx handles redirect to home
    } catch (err: any) {
      setError(err.message || 'Registration failed. Please check your details.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      style={styles.container}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <View style={styles.card}>
          <Text style={styles.headerTitle}>Household Owner Registration</Text>
          <Text style={styles.subTitle}>
            Post domestic tasks and hire trusted university students
          </Text>

          {error && <Text style={styles.errorText}>{error}</Text>}

          <View style={styles.formGroup}>
            <Text style={styles.label}>Username *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. sarah_m"
              value={username}
              onChangeText={setUsername}
              autoCapitalize="none"
            />
          </View>

          <View style={styles.row}>
            <View style={[styles.formGroup, styles.half]}>
              <Text style={styles.label}>First Name</Text>
              <TextInput
                style={styles.input}
                placeholder="Sarah"
                value={firstName}
                onChangeText={setFirstName}
              />
            </View>
            <View style={[styles.formGroup, styles.half]}>
              <Text style={styles.label}>Last Name</Text>
              <TextInput
                style={styles.input}
                placeholder="Mwangi"
                value={lastName}
                onChangeText={setLastName}
              />
            </View>
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Email Address *</Text>
            <TextInput
              style={styles.input}
              placeholder="sarah@example.com"
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>M-Pesa Phone Number *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. 254712345678"
              value={phoneNumber}
              onChangeText={setPhoneNumber}
              keyboardType="phone-pad"
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Physical Address / Location *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. Kilimani, Argwings Kodhek Rd"
              value={address}
              onChangeText={setAddress}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Password *</Text>
            <TextInput
              style={styles.input}
              placeholder="••••••••"
              secureTextEntry
              value={password}
              onChangeText={setPassword}
            />
          </View>

          <TouchableOpacity
            style={styles.primaryButton}
            onPress={handleRegister}
            disabled={loading}>
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryButtonText}>Register as Household Owner</Text>
            )}
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.backButton}
            onPress={() => router.replace('/auth/login' as any)}>
            <Text style={styles.backButtonText}>Already have an account? Log In</Text>
          </TouchableOpacity>
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
    maxWidth: 480,
    shadowColor: '#000',
    shadowOpacity: 0.08,
    shadowOffset: { width: 0, height: 4 },
    shadowRadius: 12,
    elevation: 3,
  },
  headerTitle: {
    fontSize: 22,
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
  errorText: {
    color: '#CF222E',
    backgroundColor: '#FFEBE9',
    padding: 10,
    borderRadius: 8,
    fontSize: 13,
    marginBottom: 14,
  },
  formGroup: {
    marginBottom: 14,
  },
  row: {
    flexDirection: 'row',
    gap: 12,
  },
  half: {
    flex: 1,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    color: '#24292F',
    marginBottom: 4,
  },
  input: {
    borderWidth: 1,
    borderColor: '#D0D7DE',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    backgroundColor: '#FAFAFA',
    color: '#1F2328',
  },
  primaryButton: {
    backgroundColor: '#1F883D',
    borderRadius: 8,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 10,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '600',
  },
  backButton: {
    marginTop: 14,
    alignItems: 'center',
    paddingVertical: 6,
  },
  backButtonText: {
    color: '#0969DA',
    fontSize: 13,
    fontWeight: '500',
  },
});
