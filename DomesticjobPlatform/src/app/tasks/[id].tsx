import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  TextInput,
  Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

interface Bid {
  id: number;
  student_username: string;
  student_verification: string;
  student_rating: number;
  amount: string;
  message: string;
  status: string;
  created_at: string;
}

interface Task {
  id: number;
  title: string;
  description: string;
  category: string;
  posted_price: string;
  recommended_price: string;
  location_address: string;
  location_lat: string;
  location_lng: string;
  status: string;
  household_owner: number;
  household_owner_name: string;
  assigned_student: number | null;
  assigned_student_name: string | null;
  bids: Bid[];
  escrow_status: string | null;
  created_at: string;
}

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    Posted: '#2196F3',
    Bidding: '#FF9800',
    Assigned: '#9C27B0',
    InProgress: '#FFC107',
    Completed: '#4CAF50',
    Cancelled: '#F44336',
    Disputed: '#E91E63',
  };
  return colors[status] || '#757575';
}

function getBidStatusStyle(status: string): object {
  const map: Record<string, object> = {
    Pending: { backgroundColor: '#fff3e0' },
    Accepted: { backgroundColor: '#e8f5e9' },
    Rejected: { backgroundColor: '#ffebee' },
    Withdrawn: { backgroundColor: '#f5f5f5' },
  };
  return map[status] || { backgroundColor: '#f5f5f5' };
}

export default function TaskDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams();
  const { user } = useAuth();
  const goBack = useGoBack();

  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [bidAmount, setBidAmount] = useState('');
  const [bidMessage, setBidMessage] = useState('');
  const [submittingBid, setSubmittingBid] = useState(false);
  const [acceptingBidId, setAcceptingBidId] = useState<number | null>(null);

  // Helper function for cross-platform alerts
  const showAlert = (title: string, message: string) => {
    if (Platform.OS === 'web') {
      window.alert(`${title}\n\n${message}`);
    } else {
      Alert.alert(title, message);
    }
  };

  // Helper function for cross-platform confirmations
  const showConfirm = async (title: string, message: string): Promise<boolean> => {
    if (Platform.OS === 'web') {
      return window.confirm(`${title}\n\n${message}`);
    } else {
      return new Promise((resolve) => {
        Alert.alert(title, message, [
          { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
          { text: 'OK', onPress: () => resolve(true) },
        ]);
      });
    }
  };

  const fetchTaskDetail = async () => {
    try {
      const data = await api.tasks.get(Number(id));
      setTask(data);
      if (data.recommended_price) setBidAmount(data.recommended_price);
    } catch {
      showAlert('Error', 'Failed to load task details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTaskDetail(); }, [id]);

  const handleSubmitBid = async () => {
    if (!bidAmount || parseFloat(bidAmount) <= 0) {
      showAlert('Error', 'Please enter a valid bid amount');
      return;
    }
    setSubmittingBid(true);
    try {
      await api.tasks.submitBid(Number(id), bidAmount, bidMessage);
      showAlert('Success', 'Your bid has been submitted!');
      fetchTaskDetail();
      setBidMessage('');
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to submit bid');
    } finally {
      setSubmittingBid(false);
    }
  };

  const handleAcceptBid = async (bidId: number, studentName: string) => {
    console.log('handleAcceptBid called:', { bidId, studentName });
    
    const confirmed = await showConfirm(
      'Accept Bid',
      `Accept bid from ${studentName}? This will assign them to the task.`
    );

    if (!confirmed) {
      console.log('User cancelled bid acceptance');
      return;
    }

    console.log('User confirmed bid acceptance');
    setAcceptingBidId(bidId);
    try {
      console.log('Calling API to accept bid...');
      await api.tasks.acceptBid(Number(id), bidId);
      console.log('Bid accepted, navigating to payment...');
      // Navigate directly to payment screen
      router.replace(`/payments/initiate?taskId=${id}` as any);
    } catch (error: any) {
      console.error('Error accepting bid:', error);
      showAlert('Error', error.message || 'Failed to accept bid');
    } finally {
      setAcceptingBidId(null);
    }
  };

  if (loading) {
    return (
      <View style={styles.centerContainer}>
        <ActivityIndicator size="large" color="#007bff" />
        <Text style={styles.loadingText}>Loading task details...</Text>
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

  const isOwner = Number(user?.id) === Number(task.household_owner);
  const isStudent = user?.role === 'STUDENT';
  const isAssignedStudent = Number(user?.id) === Number(task.assigned_student);
  const canBid = isStudent && !isOwner && ['Posted', 'Bidding'].includes(task.status);
  const alreadyBid = task.bids.some(b => b.student_username === user?.username);

  const escrowLabel = task.escrow_status === 'Held'
    ? 'Escrow: Funds Secured'
    : `Escrow: ${task.escrow_status}`;

  return (
    <ScrollView style={styles.container}>

      {/* Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={goBack} style={styles.backButton}>
          <Text style={styles.backText}>← Back</Text>
        </TouchableOpacity>
      </View>

      {/* Task Info */}
      <View style={styles.card}>
        <View style={styles.titleRow}>
          <Text style={styles.title}>{task.title}</Text>
          <View style={[styles.statusBadge, { backgroundColor: getStatusColor(task.status) }]}>
            <Text style={styles.statusText}>{task.status}</Text>
          </View>
        </View>

        <Text style={styles.category}>{`📂 ${task.category}`}</Text>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Description</Text>
          <Text style={styles.description}>{task.description}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Location</Text>
          <Text style={styles.infoText}>{`📍 ${task.location_address || 'Not specified'}`}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Posted By</Text>
          <Text style={styles.infoText}>{`👤 ${task.household_owner_name}`}</Text>
        </View>

        <View style={styles.priceRow}>
          <View style={styles.priceItem}>
            <Text style={styles.priceLabel}>Offered Price</Text>
            <Text style={styles.priceAmount}>{`KES ${task.posted_price}`}</Text>
          </View>
          {!!task.recommended_price && (
            <View style={styles.priceItem}>
              <Text style={styles.priceLabel}>Recommended</Text>
              <Text style={styles.recommendedAmount}>{`KES ${task.recommended_price}`}</Text>
            </View>
          )}
        </View>

        {!!task.assigned_student && (
          <View style={[styles.section, styles.assignedSection]}>
            <Text style={styles.sectionTitle}>Assigned To</Text>
            <Text style={styles.assignedText}>{`✅ ${task.assigned_student_name}`}</Text>
            {!!task.escrow_status && (
              <Text style={styles.escrowText}>{`💰 Escrow: ${task.escrow_status}`}</Text>
            )}
          </View>
        )}
      </View>

      {/* Bid Form — students only */}
      {canBid && !alreadyBid && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Submit Your Bid</Text>
          <View style={styles.formGroup}>
            <Text style={styles.label}>Bid Amount (KES)</Text>
            <TextInput
              style={styles.input}
              placeholder="Enter your bid amount"
              keyboardType="numeric"
              value={bidAmount}
              onChangeText={setBidAmount}
            />
          </View>
          <View style={styles.formGroup}>
            <Text style={styles.label}>Message (Optional)</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              placeholder="Why you are a good fit for this task..."
              multiline
              numberOfLines={4}
              value={bidMessage}
              onChangeText={setBidMessage}
            />
          </View>
          <TouchableOpacity
            style={[styles.submitButton, submittingBid && styles.disabledButton]}
            onPress={handleSubmitBid}
            disabled={submittingBid}
          >
            {submittingBid
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.submitButtonText}>Submit Bid</Text>}
          </TouchableOpacity>
        </View>
      )}

      {canBid && alreadyBid && (
        <View style={styles.card}>
          <Text style={styles.alreadyBidText}>You have already submitted a bid for this task</Text>
        </View>
      )}

      {/* Bids list */}
      {task.bids.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{`Bids (${task.bids.length})`}</Text>
          {task.bids.map(bid => (
            <View key={bid.id} style={styles.bidCard}>
              <View style={styles.bidHeader}>
                <View>
                  <Text style={styles.bidStudent}>{`👤 ${bid.student_username}`}</Text>
                  <Text style={styles.bidMeta}>{`⭐ ${bid.student_rating.toFixed(1)} • ${bid.student_verification}`}</Text>
                </View>
                <View style={[styles.bidStatusBadge, getBidStatusStyle(bid.status)]}>
                  <Text style={styles.bidStatusText}>{bid.status}</Text>
                </View>
              </View>
              <Text style={styles.bidAmount}>{`KES ${bid.amount}`}</Text>
              {!!bid.message && <Text style={styles.bidMessage}>{bid.message}</Text>}
              <Text style={styles.bidDate}>{`Submitted: ${new Date(bid.created_at).toLocaleDateString()}`}</Text>
              {isOwner && bid.status === 'Pending' && ['Posted', 'Bidding'].includes(task.status) && (
                <TouchableOpacity
                  style={[styles.acceptButton, acceptingBidId === bid.id && styles.disabledButton]}
                  onPress={() => handleAcceptBid(bid.id, bid.student_username)}
                  disabled={acceptingBidId !== null}
                >
                  {acceptingBidId === bid.id
                    ? <ActivityIndicator color="#fff" size="small" />
                    : <Text style={styles.acceptButtonText}>Accept Bid</Text>}
                </TouchableOpacity>
              )}
            </View>
          ))}
        </View>
      )}

      {task.bids.length === 0 && (
        <View style={styles.card}>
          <Text style={styles.noBidsText}>No bids yet</Text>
        </View>
      )}

      {/* Task Actions — assigned parties only */}
      {!!task.assigned_student && (isOwner || isAssignedStudent) && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Task Actions</Text>

          {isOwner && task.status === 'Assigned' && (!task.escrow_status || task.escrow_status === 'PendingDeposit') && (
            <TouchableOpacity
              style={[styles.actionButton, styles.escrowButton]}
              onPress={() => router.push(`/payments/initiate?taskId=${task.id}` as any)}
            >
              <Text style={styles.actionButtonText}>Deposit to Escrow</Text>
            </TouchableOpacity>
          )}

          {!!task.escrow_status && task.escrow_status !== 'PendingDeposit' && (
            <View style={styles.escrowStatusCard}>
              <Text style={styles.escrowStatusText}>{escrowLabel}</Text>
            </View>
          )}

          <TouchableOpacity
            style={styles.actionButton}
            onPress={() => router.push(`/messages/${task.id}` as any)}
          >
            <Text style={styles.actionButtonText}>Message</Text>
          </TouchableOpacity>

          {isAssignedStudent && task.status === 'Assigned' && task.escrow_status === 'Held' && (
            <TouchableOpacity
              style={[styles.actionButton, styles.completeButton]}
              onPress={async () => {
                const confirmed = await showConfirm('Start Task', 'Confirm you have started working on this task?');
                if (!confirmed) return;

                try {
                  await api.tasks.markComplete(task.id);
                  showAlert('Task Started', 'The household owner will mark it complete when done.');
                  fetchTaskDetail();
                } catch (error: any) {
                  showAlert('Error', error.message || 'Failed to update task');
                }
              }}
            >
              <Text style={styles.actionButtonText}>Start Task</Text>
            </TouchableOpacity>
          )}

          {isOwner && task.status === 'InProgress' && (
            <TouchableOpacity
              style={[styles.actionButton, styles.completeButton]}
              onPress={async () => {
                const confirmed = await showConfirm(
                  'Mark Complete',
                  'Mark this task as completed? Escrow funds will be released to the student.'
                );
                if (!confirmed) return;

                try {
                  await api.tasks.markComplete(task.id);
                  showAlert('Done!', 'Task completed and payment released to the student.');
                  fetchTaskDetail();
                } catch (error: any) {
                  showAlert('Error', error.message || 'Failed to complete task');
                }
              }}
            >
              <Text style={styles.actionButtonText}>Mark as Complete</Text>
            </TouchableOpacity>
          )}

          {task.status === 'Completed' && (
            <TouchableOpacity
              style={[styles.actionButton, styles.ratingButton]}
              onPress={() => {
                const ratedUserId = isOwner ? task.assigned_student : task.household_owner;
                router.push(`/ratings/create?taskId=${task.id}&ratedUserId=${ratedUserId}` as any);
              }}
            >
              <Text style={styles.actionButtonText}>Rate and Review</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      <View style={{ height: 40 }} />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#f5f5f5' },
  centerContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#f5f5f5' },
  loadingText: { marginTop: 10, color: '#666', fontSize: 14 },
  errorText: { color: '#f44336', fontSize: 16 },
  header: { backgroundColor: '#fff', padding: 16, paddingTop: 60, borderBottomWidth: 1, borderBottomColor: '#e0e0e0' },
  backButton: { flexDirection: 'row', alignItems: 'center' },
  backText: { fontSize: 16, color: '#007bff', fontWeight: '600' },
  card: { backgroundColor: '#fff', margin: 16, marginTop: 8, marginBottom: 8, borderRadius: 12, padding: 16, shadowColor: '#000', shadowOpacity: 0.1, shadowOffset: { width: 0, height: 2 }, shadowRadius: 4, elevation: 3 },
  titleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  title: { fontSize: 22, fontWeight: 'bold', color: '#1a1a1a', flex: 1, marginRight: 12 },
  statusBadge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  statusText: { color: '#fff', fontSize: 11, fontWeight: '600' },
  category: { fontSize: 14, color: '#666', marginBottom: 16 },
  section: { marginBottom: 16 },
  sectionTitle: { fontSize: 13, fontWeight: '600', color: '#999', marginBottom: 6, textTransform: 'uppercase' },
  description: { fontSize: 15, color: '#333', lineHeight: 22 },
  infoText: { fontSize: 15, color: '#555' },
  priceRow: { flexDirection: 'row', justifyContent: 'space-between', backgroundColor: '#f8f9fa', padding: 16, borderRadius: 8, marginBottom: 16 },
  priceItem: { alignItems: 'center' },
  priceLabel: { fontSize: 12, color: '#666', marginBottom: 4 },
  priceAmount: { fontSize: 20, fontWeight: 'bold', color: '#28a745' },
  recommendedAmount: { fontSize: 16, fontWeight: '600', color: '#007bff' },
  assignedSection: { backgroundColor: '#f0f8ff', padding: 12, borderRadius: 8 },
  assignedText: { fontSize: 15, color: '#28a745', fontWeight: '600' },
  escrowText: { fontSize: 13, color: '#666', marginTop: 4 },
  cardTitle: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a', marginBottom: 16 },
  formGroup: { marginBottom: 16 },
  label: { fontSize: 14, fontWeight: '600', color: '#333', marginBottom: 6 },
  input: { borderWidth: 1, borderColor: '#d0d0d0', borderRadius: 8, paddingHorizontal: 12, paddingVertical: 10, fontSize: 15, backgroundColor: '#f9f9f9' },
  textArea: { height: 100, textAlignVertical: 'top' },
  submitButton: { backgroundColor: '#007bff', padding: 16, borderRadius: 10, alignItems: 'center' },
  disabledButton: { backgroundColor: '#aaa' },
  submitButtonText: { color: '#fff', fontSize: 16, fontWeight: 'bold' },
  alreadyBidText: { fontSize: 15, color: '#28a745', textAlign: 'center', fontWeight: '600' },
  bidCard: { borderWidth: 1, borderColor: '#e0e0e0', borderRadius: 8, padding: 12, marginBottom: 12 },
  bidHeader: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  bidStudent: { fontSize: 15, fontWeight: '600', color: '#1a1a1a', marginBottom: 2 },
  bidMeta: { fontSize: 12, color: '#666' },
  bidStatusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 8 },
  bidStatusText: { fontSize: 11, fontWeight: '600', color: '#666' },
  bidAmount: { fontSize: 18, fontWeight: 'bold', color: '#28a745', marginBottom: 8 },
  bidMessage: { fontSize: 14, color: '#555', fontStyle: 'italic', marginBottom: 8 },
  bidDate: { fontSize: 12, color: '#999' },
  acceptButton: { backgroundColor: '#28a745', padding: 10, borderRadius: 8, alignItems: 'center', marginTop: 12 },
  acceptButtonText: { color: '#fff', fontSize: 14, fontWeight: '600' },
  noBidsText: { textAlign: 'center', color: '#999', fontSize: 15, fontStyle: 'italic' },
  actionButton: { backgroundColor: '#007bff', padding: 14, borderRadius: 10, alignItems: 'center', marginBottom: 10 },
  actionButtonText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  ratingButton: { backgroundColor: '#FF9800' },
  completeButton: { backgroundColor: '#28a745' },
  escrowButton: { backgroundColor: '#9C27B0' },
  escrowStatusCard: { backgroundColor: '#f0f8ff', padding: 12, borderRadius: 8, marginBottom: 10, alignItems: 'center' },
  escrowStatusText: { fontSize: 14, fontWeight: '600', color: '#007bff' },
});
