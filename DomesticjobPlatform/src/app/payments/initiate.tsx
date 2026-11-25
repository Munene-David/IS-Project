import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  ScrollView,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

export default function InitiatePaymentScreen() {
  const router = useRouter();
  const { taskId } = useLocalSearchParams();
  const { user } = useAuth();
  const goBack = useGoBack();
  
  const [task, setTask] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number || '');
  const [checkoutRequestId, setCheckoutRequestId] = useState<string | null>(null);
  const [paymentStatus, setPaymentStatus] = useState<'idle' | 'pending' | 'checking' | 'success' | 'failed'>('idle');

  useEffect(() => {
    fetchTaskDetails();
  }, [taskId]);

  const fetchTaskDetails = async () => {
    try {
      const data = await api.tasks.get(Number(taskId));
      setTask(data);
    } catch (error: any) {
      Alert.alert('Error', 'Failed to load task details');
    } finally {
      setLoading(false);
    }
  };

  const handleInitiatePayment = async () => {
    if (!phoneNumber.trim()) {
      Alert.alert('Error', 'Please enter your M-Pesa phone number');
      return;
    }

    // Validate phone number format
    const cleanPhone = phoneNumber.replace(/\s+/g, '');
    if (!/^(254|0)[17]\d{8}$/.test(cleanPhone)) {
      Alert.alert('Error', 'Please enter a valid Kenyan phone number (e.g., 0712345678 or 254712345678)');
      return;
    }

    setProcessing(true);
    setPaymentStatus('pending');

    try {
      const response = await api.payments.initiateEscrow(Number(taskId), cleanPhone);
      
      if (response.success) {
        setCheckoutRequestId(response.checkout_request_id);
        
        Alert.alert(
          'Payment Request Sent',
          response.message || 'Please check your phone and enter your M-Pesa PIN to complete the payment.',
          [
            {
              text: 'OK',
              onPress: () => startStatusChecking(response.checkout_request_id),
            },
          ]
        );
      } else {
        setPaymentStatus('failed');
        Alert.alert('Payment Failed', response.error || 'Failed to initiate payment. Please try again.');
      }
    } catch (error: any) {
      setPaymentStatus('failed');
      Alert.alert('Error', error.message || 'Failed to initiate payment');
    } finally {
      setProcessing(false);
    }
  };

  const startStatusChecking = (checkoutId: string) => {
    setPaymentStatus('checking');
    
    // Check status every 3 seconds for up to 1 minute
    let attempts = 0;
    const maxAttempts = 20;
    
    const interval = setInterval(async () => {
      attempts++;
      
      try {
        const statusResponse = await api.payments.checkStatus(checkoutId);
        
        if (statusResponse.status === 'Held') {
          clearInterval(interval);
          setPaymentStatus('success');
          
          Alert.alert(
            'Payment Successful!',
            'Escrow funds have been secured. The student can now begin the task.',
            [
              {
                text: 'OK',
                onPress: () => goBack(),
              },
            ]
          );
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          setPaymentStatus('idle');
          Alert.alert(
            'Status Unknown',
            'Unable to confirm payment status. Please check your task details or try again.',
            [
              {
                text: 'OK',
                onPress: () => goBack(),
              },
            ]
          );
        }
      } catch (error) {
        console.error('Status check failed:', error);
      }
    }, 3000);
  };

  const handleManualCheck = async () => {
    if (!checkoutRequestId) return;

    setPaymentStatus('checking');
    try {
      const statusResponse = await api.payments.checkStatus(checkoutRequestId);
      
      if (statusResponse.status === 'Held') {
        setPaymentStatus('success');
        Alert.alert(
          'Payment Confirmed!',
          'Your payment has been verified.',
          [{ text: 'OK', onPress: () => goBack() }]
        );
      } else {
        setPaymentStatus('idle');
        Alert.alert('Payment Pending', 'Payment has not been confirmed yet. Please ensure you completed the M-Pesa transaction.');
      }
    } catch (error: any) {
      setPaymentStatus('idle');
      Alert.alert('Error', 'Failed to check payment status');
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading...</Text>
      </View>
    );
  }

  if (!task) {
    return (
      <View style={styles.centerContainer}>
        <Text style={styles.errorText}>Task not found</Text>
      </View>
    );
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => goBack()} style={styles.backButton}>
          <Text style={styles.backText}>← Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Deposit to Escrow</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.scrollContent}>
        <View style={styles.card}>
          <Text style={styles.taskTitle}>{task.title}</Text>
          <Text style={styles.taskCategory}>📂 {task.category}</Text>
          
          <View style={styles.amountCard}>
            <Text style={styles.amountLabel}>Amount to Deposit</Text>
            <Text style={styles.amount}>KES {task.posted_price}</Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>💳 M-Pesa Payment</Text>
          <Text style={styles.sectionSubtitle}>
            Enter your M-Pesa registered phone number. You'll receive a prompt on your phone to complete the payment.
          </Text>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Phone Number *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g., 0712345678 or 254712345678"
              keyboardType="phone-pad"
              value={phoneNumber}
              onChangeText={setPhoneNumber}
              editable={paymentStatus === 'idle' || paymentStatus === 'failed'}
            />
          </View>

          {paymentStatus === 'idle' || paymentStatus === 'failed' ? (
            <TouchableOpacity
              style={[styles.payButton, processing && styles.payButtonDisabled]}
              onPress={handleInitiatePayment}
              disabled={processing}
            >
              {processing ? (
                <ActivityIndicator color="#fff" />
              ) : (
                <Text style={styles.payButtonText}>Send Payment Request</Text>
              )}
            </TouchableOpacity>
          ) : null}

          {paymentStatus === 'pending' && (
            <View style={styles.statusCard}>
              <Text style={styles.statusTitle}>📱 Check Your Phone</Text>
              <Text style={styles.statusText}>
                An M-Pesa payment prompt has been sent to {phoneNumber}. Enter your PIN to complete the payment.
              </Text>
            </View>
          )}

          {paymentStatus === 'checking' && (
            <View style={styles.statusCard}>
              <ActivityIndicator size="large" color="#007bff" />
              <Text style={[styles.statusTitle, { marginTop: 12 }]}>Verifying Payment...</Text>
              <Text style={styles.statusText}>
                Please wait while we confirm your payment.
              </Text>
            </View>
          )}

          {paymentStatus === 'success' && (
            <View style={[styles.statusCard, styles.successCard]}>
              <Text style={styles.successIcon}>✅</Text>
              <Text style={styles.successTitle}>Payment Successful!</Text>
              <Text style={styles.statusText}>
                Funds have been secured in escrow. The student will be notified.
              </Text>
            </View>
          )}

          {checkoutRequestId && paymentStatus !== 'success' && (
            <TouchableOpacity
              style={styles.checkButton}
              onPress={handleManualCheck}
              disabled={paymentStatus === 'checking'}
            >
              <Text style={styles.checkButtonText}>Check Payment Status</Text>
            </TouchableOpacity>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.infoTitle}>ℹ️ How Escrow Works</Text>
          <Text style={styles.infoText}>
            1. Your payment is held securely in escrow
          </Text>
          <Text style={styles.infoText}>
            2. The student completes the task
          </Text>
          <Text style={styles.infoText}>
            3. You mark the task as complete
          </Text>
          <Text style={styles.infoText}>
            4. Funds are automatically released to the student
          </Text>
        </View>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
  },
  loadingText: {
    marginTop: 10,
    color: '#666',
    fontSize: 14,
  },
  errorText: {
    color: '#f44336',
    fontSize: 16,
  },
  header: {
    backgroundColor: '#fff',
    padding: 16,
    paddingTop: 60,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#e0e0e0',
  },
  backButton: {
    padding: 4,
  },
  backText: {
    fontSize: 16,
    color: '#007bff',
    fontWeight: '600',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a1a',
  },
  scrollView: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    shadowColor: '#000',
    shadowOpacity: 0.05,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 2,
  },
  taskTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 4,
  },
  taskCategory: {
    fontSize: 14,
    color: '#666',
    marginBottom: 16,
  },
  amountCard: {
    backgroundColor: '#f0f8ff',
    padding: 16,
    borderRadius: 8,
    alignItems: 'center',
  },
  amountLabel: {
    fontSize: 13,
    color: '#666',
    marginBottom: 6,
  },
  amount: {
    fontSize: 28,
    fontWeight: 'bold',
    color: '#007bff',
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 6,
  },
  sectionSubtitle: {
    fontSize: 14,
    color: '#666',
    marginBottom: 16,
    lineHeight: 20,
  },
  formGroup: {
    marginBottom: 16,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  input: {
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
    backgroundColor: '#f9f9f9',
  },
  payButton: {
    backgroundColor: '#28a745',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
  },
  payButtonDisabled: {
    backgroundColor: '#ccc',
  },
  payButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: 'bold',
  },
  statusCard: {
    backgroundColor: '#f8f9fa',
    padding: 20,
    borderRadius: 12,
    alignItems: 'center',
    marginTop: 16,
  },
  successCard: {
    backgroundColor: '#e8f5e9',
  },
  statusTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 8,
  },
  statusText: {
    fontSize: 14,
    color: '#666',
    textAlign: 'center',
    lineHeight: 20,
  },
  successIcon: {
    fontSize: 48,
    marginBottom: 8,
  },
  successTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#28a745',
    marginBottom: 8,
  },
  checkButton: {
    borderWidth: 1,
    borderColor: '#007bff',
    padding: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 12,
  },
  checkButtonText: {
    color: '#007bff',
    fontSize: 15,
    fontWeight: '600',
  },
  infoTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a1a1a',
    marginBottom: 12,
  },
  infoText: {
    fontSize: 14,
    color: '#555',
    marginBottom: 8,
    lineHeight: 20,
  },
});
