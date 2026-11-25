import React, { useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity,
  ActivityIndicator, Alert, Platform, TextInput,
} from 'react-native';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

const showAlert = (title: string, msg: string) => {
  if (Platform.OS === 'web') window.alert(`${title}\n\n${msg}`);
  else Alert.alert(title, msg);
};

export default function ProfileScreen() {
  const { user, refreshMe } = useAuth();
  const goBack = useGoBack();
  const [loading, setLoading] = useState(false);

  if (!user) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color="#007bff" />
      </View>
    );
  }

  const isStudent = user.role === 'STUDENT';
  const isHousehold = user.role === 'HOUSEHOLD';

  const profile: any = isStudent ? user.student_profile : user.household_profile;
  const verificationStatus = profile?.verification_status ?? 'Pending';
  const verificationColor =
    verificationStatus === 'Verified' ? '#16a34a'
    : verificationStatus === 'Rejected' ? '#dc2626'
    : '#d97706';

  const fullName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backBtn}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>My Profile</Text>
        <View style={{ width: 60 }} />
      </View>

      {/* Avatar + name */}
      <View style={styles.avatarCard}>
        <View style={styles.avatar}>
          <Text style={styles.avatarLetter}>
            {(user.first_name?.[0] || user.username[0]).toUpperCase()}
          </Text>
        </View>
        <Text style={styles.fullName}>{fullName}</Text>
        <Text style={styles.username}>@{user.username}</Text>
        <View style={[styles.roleBadge, { backgroundColor: isStudent ? '#dbeafe' : '#fef3c7' }]}>
          <Text style={[styles.roleText, { color: isStudent ? '#1d4ed8' : '#92400e' }]}>
            {isStudent ? '🎓 University Student' : '🏠 Household Owner'}
          </Text>
        </View>
      </View>

      {/* Account details */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Account Details</Text>

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Email</Text>
          <Text style={styles.rowValue}>{user.email || '—'}</Text>
        </View>
        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Phone</Text>
          <Text style={styles.rowValue}>{user.phone_number || '—'}</Text>
        </View>
        <View style={styles.divider} />

        <View style={styles.row}>
          <Text style={styles.rowLabel}>Verification</Text>
          <Text style={[styles.rowValue, { color: verificationColor, fontWeight: '700' }]}>
            {verificationStatus}
          </Text>
        </View>
      </View>

      {/* Student-specific */}
      {isStudent && user.student_profile && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Student Details</Text>

          <View style={styles.row}>
            <Text style={styles.rowLabel}>University</Text>
            <Text style={styles.rowValue}>{user.student_profile.university_name || '—'}</Text>
          </View>
          <View style={styles.divider} />

          <View style={styles.row}>
            <Text style={styles.rowLabel}>Student ID</Text>
            <Text style={styles.rowValue}>{user.student_profile.university_id || '—'}</Text>
          </View>
          <View style={styles.divider} />

          <View style={styles.row}>
            <Text style={styles.rowLabel}>Available</Text>
            <Text style={[styles.rowValue, {
              color: user.student_profile.availability_status ? '#16a34a' : '#dc2626',
              fontWeight: '600',
            }]}>
              {user.student_profile.availability_status ? 'Yes' : 'No'}
            </Text>
          </View>
        </View>
      )}

      {/* Household-specific */}
      {isHousehold && user.household_profile && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Household Details</Text>

          <View style={styles.row}>
            <Text style={styles.rowLabel}>Address</Text>
            <Text style={styles.rowValue}>{user.household_profile.address || '—'}</Text>
          </View>
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f7fa' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: {
    backgroundColor: '#fff',
    paddingTop: 50,
    paddingHorizontal: 16,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  backBtn: { padding: 4 },
  backText: { color: '#007bff', fontSize: 16, fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: '#1a1a2e' },
  avatarCard: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 8,
    borderRadius: 16,
    padding: 24,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.07,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 6,
    elevation: 3,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#3b82f6',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
  },
  avatarLetter: { fontSize: 36, fontWeight: '800', color: '#fff' },
  fullName: { fontSize: 22, fontWeight: '700', color: '#1a1a2e', marginBottom: 4 },
  username: { fontSize: 15, color: '#6b7280', marginBottom: 12 },
  roleBadge: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
  },
  roleText: { fontSize: 13, fontWeight: '600' },
  card: {
    backgroundColor: '#fff',
    margin: 16,
    marginBottom: 8,
    borderRadius: 14,
    padding: 16,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  cardTitle: { fontSize: 16, fontWeight: '700', color: '#1a1a2e', marginBottom: 14 },
  row: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10 },
  rowLabel: { fontSize: 14, color: '#6b7280', fontWeight: '500' },
  rowValue: { fontSize: 14, color: '#1a1a2e', maxWidth: '60%', textAlign: 'right' },
  divider: { height: 1, backgroundColor: '#f3f4f6' },
});
