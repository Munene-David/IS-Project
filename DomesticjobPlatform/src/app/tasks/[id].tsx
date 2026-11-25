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
  Modal,
  Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import {
  api,
  CheckinSummary,
  CheckinPayload,
  GeoConsentInfo,
  LocationSnapshot,
} from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';
import MapPicker from '@/components/map-picker';
import {
  requestLocationPermission,
  getCurrentLocationSnapshot,
} from '@/services/location';
import { syncQueuedCheckins, queueCheckin } from '@/services/checkin-queue';

interface Task {
  id: number;
  title: string;
  description: string;
  category: string;
  posted_price: string;
  recommended_price: string;
  location_address: string;
  location_address_full: string | null;
  location_lat: string;
  location_lng: string;
  location_exact: boolean;
  location_area: string | null;
  location_landmark: string | null;
  geofence_radius_m: number;
  status: string;
  household_owner: number;
  household_owner_name: string;
  assigned_student: number | null;
  assigned_student_name: string | null;
  assigned_student_first_name: string | null;
  task_requests: any[];
  my_request: { id: number; status: string; sent_at: string } | null;
  escrow_status: string | null;
  created_at: string;
  updated_at: string;
  scheduled_date: string | null;
  scheduled_time: string | null;
  broadcast_round: number;
  search_radius_km: string;
  grace_window_deadline: string | null;
  confirmation_deadline: string | null;
  has_completion: boolean;
  completion_timestamps: {
    arrived_at: string | null;
    started_at: string | null;
    finished_at: string | null;
    has_before_photo: boolean;
    has_after_photo: boolean;
  } | null;
  has_dispute: boolean;
  checkin_summary: CheckinSummary | null;
}

const DISPUTE_REASONS = [
  { value: 'not_completed', label: 'Work not completed' },
  { value: 'poor_quality', label: 'Poor quality' },
  { value: 'did_not_show', label: 'Student did not show up' },
  { value: 'damaged_property', label: 'Damaged property' },
  { value: 'other', label: 'Other' },
];

function getStatusColor(status: string): string {
  const colors: Record<string, string> = {
    Posted: '#2196F3',
    Bidding: '#FF9800',
    Broadcasting: '#3b82f6',
    Matched: '#10b981',
    PaymentPending: '#f59e0b',
    Assigned: '#9C27B0',
    InProgress: '#FFC107',
    AwaitingConfirmation: '#f97316',
    Completed: '#4CAF50',
    Cancelled: '#F44336',
    Disputed: '#E91E63',
    Reopened: '#06b6d4',
    NoShow: '#dc2626',
  };
  return colors[status] || '#757575';
}

/** '14:05' from an ISO timestamp (device-locale independent). */
function formatClock(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

/** 'OUT_OF_RANGE' → 'out of range'. */
function prettyResult(result: string): string {
  return result.replace(/_/g, ' ').toLowerCase();
}

export default function TaskDetailScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams();
  const { user } = useAuth();
  const goBack = useGoBack();

  const [task, setTask] = useState<Task | null>(null);
  const [loading, setLoading] = useState(true);
  const [confirmingMatch, setConfirmingMatch] = useState(false);
  const [cancellingMatch, setCancellingMatch] = useState(false);
  const [rebroadcasting, setRebroadcasting] = useState(false);
  const [studentCancelling, setStudentCancelling] = useState(false);
  const [graceTimeLeft, setGraceTimeLeft] = useState<string | null>(null);
  const [confirmTimeLeft, setConfirmTimeLeft] = useState<string | null>(null);
  const [confirmPhone, setConfirmPhone] = useState('');
  const [showPhoneInput, setShowPhoneInput] = useState(false);

  // Start code check-in state
  const [startCode, setStartCode] = useState<string | null>(null);
  const [checkinCode, setCheckinCode] = useState('');
  const [checkingIn, setCheckingIn] = useState(false);

  // Location consent (student must accept before first check-in)
  const [consentInfo, setConsentInfo] = useState<GeoConsentInfo | null>(null);
  const [showConsentModal, setShowConsentModal] = useState(false);
  const [consenting, setConsenting] = useState(false);

  // Dispute form state
  const [showDisputeForm, setShowDisputeForm] = useState(false);
  const [disputeReason, setDisputeReason] = useState('');
  const [disputeDescription, setDisputeDescription] = useState('');
  const [submittingDispute, setSubmittingDispute] = useState(false);

  // Dispute response state (student)
  const [showDisputeResponse, setShowDisputeResponse] = useState(false);
  const [disputeResponseText, setDisputeResponseText] = useState('');
  const [submittingResponse, setSubmittingResponse] = useState(false);

  // Task invitation (student acting on a broadcast request)
  const [actingOnRequest, setActingOnRequest] = useState(false);

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
      // Load start code for household when task is Assigned
      if (data.status === 'Assigned' && Number(user?.id) === Number(data.household_owner)) {
        try {
          const sc = await api.tasks.getStartCode(Number(id));
          setStartCode(sc.start_code);
        } catch {
          // Not yet generated or other issue — ignore
        }
      }
    } catch {
      showAlert('Error', 'Failed to load task details');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchTaskDetail(); }, [id]);

  // Students: load location-consent status and replay any check-ins that
  // were queued while offline (flagged server-side as late syncs).
  useEffect(() => {
    if (user?.role !== 'STUDENT') return;
    (async () => {
      try {
        const info = await api.geo.getConsent();
        setConsentInfo(info);
      } catch {
        // Surfaced at check-in time if still failing.
      }
      try {
        const { synced } = await syncQueuedCheckins();
        if (synced > 0) {
          showAlert(
            'Offline check-ins synced',
            `${synced} saved check-in(s) were submitted and flagged as late syncs.`
          );
          fetchTaskDetail();
        }
      } catch {
        // Sync retries next visit.
      }
    })();
  }, [user?.id, id]);

  // Grace window countdown
  useEffect(() => {
    if (!task?.grace_window_deadline) { setGraceTimeLeft(null); return; }
    const update = () => {
      const deadline = new Date(task.grace_window_deadline!).getTime();
      const now = Date.now();
      const diff = deadline - now;
      if (diff <= 0) { setGraceTimeLeft('Expired'); return; }
      const mins = Math.floor(diff / 60000);
      const secs = Math.floor((diff % 60000) / 1000);
      setGraceTimeLeft(`${mins}:${String(secs).padStart(2, '0')}`);
    };
    update();
    const interval = setInterval(update, 1000);
    return () => clearInterval(interval);
  }, [task?.grace_window_deadline]);

  // Confirmation window countdown
  useEffect(() => {
    if (!task?.confirmation_deadline) { setConfirmTimeLeft(null); return; }
    const update = () => {
      const deadline = new Date(task.confirmation_deadline!).getTime();
      const now = Date.now();
      const diff = deadline - now;
      if (diff <= 0) { setConfirmTimeLeft('Auto-releasing...'); return; }
      const hrs = Math.floor(diff / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      setConfirmTimeLeft(`${hrs}h ${mins}m remaining`);
    };
    update();
    const interval = setInterval(update, 60000);
    return () => clearInterval(interval);
  }, [task?.confirmation_deadline]);

  // Auto-refresh while broadcasting or matched or awaiting confirmation
  useEffect(() => {
    if (!task) return;
    if (['Broadcasting', 'Matched', 'PaymentPending', 'Reopened', 'AwaitingConfirmation'].includes(task.status)) {
      const interval = setInterval(() => fetchTaskDetail(), 8000);
      return () => clearInterval(interval);
    }
  }, [task?.status, task?.id]);

  // --- New handlers ---

  /**
   * Geolocation-verified check-in.
   *
   * Captures ONE location snapshot at this event (never in the background),
   * sends it with the start code and handles every outcome:
   *   VERIFIED / OUT_OF_RANGE / LOW_ACCURACY  → accepted (200)
   *   WRONG_CODE / FLAGGED_MOCK / LOCATION_DENIED → rejected (400)
   * Network failure → queued locally for a late sync.
   */
  const handleCheckin = async (isRetry = false) => {
    if (!task) return;
    if (!isRetry && !checkinCode.trim()) {
      showAlert('Required', 'Please enter the 4-digit start code from the household.');
      return;
    }
    // Consent must be recorded before the first check-in.
    if (consentInfo && !consentInfo.consented) {
      setShowConsentModal(true);
      return;
    }

    setCheckingIn(true);
    const payload: CheckinPayload = {
      start_code: checkinCode.trim(),
      device_info: { platform: Platform.OS },
    };
    try {
      // One-shot location snapshot for this event only.
      try {
        const granted = await requestLocationPermission();
        if (granted) {
          const snapshot = await getCurrentLocationSnapshot();
          payload.lat = snapshot.lat;
          payload.lng = snapshot.lng;
          payload.accuracy_m = snapshot.accuracy_m;
          payload.device_time = snapshot.device_time;
          payload.mock_location = snapshot.mock_location;
        }
        // No permission → submitted without coordinates; the server
        // records LOCATION_DENIED and tells the student what to do.
      } catch {
        // GPS read failed → continue without coordinates.
      }

      const res = await api.tasks.checkin(task.id, payload);
      const data: any = res.data || {};

      if (res.status === 403 && data.code === 'consent_required') {
        setShowConsentModal(true);
        return;
      }

      if (res.ok) {
        if (data.result === 'VERIFIED') {
          showAlert(
            '✅ Checked In',
            'Start code accepted and your location was verified. The task is now in progress!'
          );
        } else {
          const reason =
            data.result === 'OUT_OF_RANGE'
              ? `you appear to be ${Math.round(data.distance_m ?? 0)} m away from the task location`
              : data.result === 'LOW_ACCURACY'
              ? 'your GPS accuracy was too low'
              : 'your location could not be fully verified';
          showAlert(
            '⚠️ Checked In — Location Flagged',
            `Start code accepted and the task has started, but ${reason}.\n\n` +
              'The household has been notified. Move closer to the pin or find a clearer GPS signal, then tap "Retry Check-In" to verify your location.'
          );
        }
        setCheckinCode('');
        fetchTaskDetail();
      } else if (data.result === 'LOCATION_DENIED') {
        if (Platform.OS === 'web') {
          showAlert('Location Required', data.error || 'Allow location access and try again.');
        } else {
          Alert.alert('Location Required', data.error || 'Allow location access and try again.', [
            { text: 'Open Settings', onPress: () => Linking.openSettings() },
            { text: 'Cancel', style: 'cancel' },
          ]);
        }
      } else if (data.result === 'FLAGGED_MOCK') {
        showAlert(
          'Mock Location Detected',
          data.error ||
            'Your device appears to be reporting a simulated location. Disable location-mocking apps and try again.'
        );
      } else {
        showAlert('Invalid Code', data.error || 'Start code is incorrect.');
      }
    } catch (error: any) {
      // Network failure — queue the check-in for a late sync.
      try {
        await queueCheckin(task.id, payload);
        setCheckinCode('');
        showAlert(
          'Saved Offline',
          'No connection right now. Your check-in was saved and will be submitted automatically when you are back online.'
        );
      } catch {
        showAlert('Error', error.message || 'Check-in failed.');
      }
    } finally {
      setCheckingIn(false);
    }
  };

  /** Record location consent, then continue the check-in the student started. */
  const handleAcceptConsent = async () => {
    if (!consentInfo) return;
    setConsenting(true);
    try {
      await api.geo.acceptConsent(consentInfo.version);
      setConsentInfo({ ...consentInfo, consented: true });
      setShowConsentModal(false);
      handleCheckin();
    } catch (error: any) {
      showAlert('Error', error.message || 'Could not record your consent.');
    } finally {
      setConsenting(false);
    }
  };

  const handleStudentMarkDone = async () => {
    const confirmed = await showConfirm(
      'Mark Work as Finished',
      'Confirm you have finished the work? The household will have 48 hours to confirm or raise a dispute. Payment will be released automatically after 48h.'
    );
    if (!confirmed) return;
    try {
      // Optional finish-location snapshot — best effort, never blocks
      // completion (captured once at this event, not in the background).
      let location: LocationSnapshot | undefined;
      try {
        const granted = await requestLocationPermission();
        if (granted) location = await getCurrentLocationSnapshot();
      } catch {
        // Finish without a location snapshot.
      }
      await api.tasks.studentComplete(task!.id, undefined, location);
      showAlert('Done!', 'Work marked as finished. Waiting for household confirmation.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to mark complete');
    }
  };

  const handleHouseholdConfirm = async () => {
    const confirmed = await showConfirm(
      'Confirm Completion',
      'Confirm the work is done satisfactorily? This will release payment to the student.'
    );
    if (!confirmed) return;
    try {
      await api.tasks.confirmCompletion(task!.id);
      showAlert('✅ Payment Released', 'Task confirmed and payment sent to the student.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to confirm');
    }
  };

  const handleRaiseDispute = async () => {
    if (!disputeReason) {
      showAlert('Required', 'Please select a reason.');
      return;
    }
    if (!disputeDescription.trim()) {
      showAlert('Required', 'Please describe the problem.');
      return;
    }
    setSubmittingDispute(true);
    try {
      await api.tasks.raiseDispute(task!.id, { reason: disputeReason, description: disputeDescription });
      showAlert('Dispute Raised', 'An admin has been notified. Payment is frozen pending review.');
      setShowDisputeForm(false);
      setDisputeReason('');
      setDisputeDescription('');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to raise dispute');
    } finally {
      setSubmittingDispute(false);
    }
  };

  const handleDisputeResponse = async () => {
    if (!disputeResponseText.trim()) {
      showAlert('Required', 'Please enter your response.');
      return;
    }
    setSubmittingResponse(true);
    try {
      await api.tasks.disputeResponse(task!.id, disputeResponseText);
      showAlert('Response Submitted', 'Your response has been recorded. Admin will review shortly.');
      setShowDisputeResponse(false);
      setDisputeResponseText('');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to submit response');
    } finally {
      setSubmittingResponse(false);
    }
  };

  const handleDeleteTask = async () => {
    const confirmed = await showConfirm(
      'Delete Task',
      'Delete this task permanently?\n\n• Any pending student requests will be withdrawn.\n• Students will be notified.\n• This cannot be undone.'
    );
    if (!confirmed) return;
    try {
      await api.tasks.delete(task!.id);
      showAlert('Deleted', 'Task has been removed.');
      router.replace('/');
    } catch (error: any) {
      showAlert('Cannot Delete', error.message || 'Failed to delete task');
    }
  };

  // --- Broadcast flow handlers ---

  const hasOpenRequest = !!task?.my_request && ['SENT', 'VIEWED'].includes(task.my_request.status);

  const handleAcceptRequest = async () => {
    if (!task?.my_request) return;
    const confirmed = await showConfirm(
      'Accept Task',
      'Accept this task? The household will be notified and has 10 minutes to confirm payment.'
    );
    if (!confirmed) return;
    setActingOnRequest(true);
    try {
      await api.tasks.acceptRequest(task.my_request.id);
      showAlert('🎉 You Got the Job!', 'The household will confirm payment within 10 minutes.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Could not accept', error.message || 'This task may have already been taken.');
      fetchTaskDetail();
    } finally {
      setActingOnRequest(false);
    }
  };

  const handleIgnoreRequest = async () => {
    if (!task?.my_request) return;
    setActingOnRequest(true);
    try {
      await api.tasks.ignoreRequest(task.my_request.id);
      showAlert('Ignored', 'This task was dismissed from your available tasks.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to ignore');
      fetchTaskDetail();
    } finally {
      setActingOnRequest(false);
    }
  };

  const handleDeclineRequest = async () => {
    if (!task?.my_request) return;
    const confirmed = await showConfirm('Decline Task', 'Decline this task? You will not be asked again.');
    if (!confirmed) return;
    setActingOnRequest(true);
    try {
      await api.tasks.declineRequest(task.my_request.id);
      showAlert('Declined', 'You will no longer receive updates about this task.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to decline');
      fetchTaskDetail();
    } finally {
      setActingOnRequest(false);
    }
  };

  const handleConfirmMatch = async () => {
    if (!confirmPhone || !confirmPhone.trim()) {
      setShowPhoneInput(true);
      return;
    }
    setConfirmingMatch(true);
    try {
      await api.tasks.confirmMatch(task!.id, confirmPhone.trim());
      showAlert('✅ Payment Sent', 'M-Pesa STK push sent to your phone. Enter your PIN to complete payment.');
      setShowPhoneInput(false);
      setConfirmPhone('');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Payment Failed', error.message || 'Failed to initiate payment');
    } finally {
      setConfirmingMatch(false);
    }
  };

  const handleCancelMatch = async () => {
    const confirmed = await showConfirm(
      'Cancel Match',
      'Cancel this match? The task will be re-broadcast to other students.'
    );
    if (!confirmed) return;
    setCancellingMatch(true);
    try {
      await api.tasks.cancelMatch(task!.id);
      showAlert('Match Cancelled', 'The task has been re-broadcast to other students.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to cancel match');
    } finally {
      setCancellingMatch(false);
    }
  };

  const handleRebroadcast = async () => {
    setRebroadcasting(true);
    try {
      await api.tasks.rebroadcast(task!.id);
      showAlert('Re-broadcasting', 'Your task is being sent to eligible students again.');
      fetchTaskDetail();
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to re-broadcast');
    } finally {
      setRebroadcasting(false);
    }
  };

  const handleStudentCancel = async () => {
    const confirmed = await showConfirm(
      'Cancel Task',
      'Are you sure you want to cancel? This will lower your reliability score and the task will be re-assigned to another student.'
    );
    if (!confirmed) return;
    setStudentCancelling(true);
    try {
      await api.tasks.studentCancel(task!.id);
      showAlert('Cancelled', 'The task has been cancelled. We are finding a replacement.');
      router.replace('/');
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to cancel');
    } finally {
      setStudentCancelling(false);
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

  const escrowLabel = task.escrow_status === 'Held'
    ? 'Escrow: Funds Secured'
    : `Escrow: ${task.escrow_status}`;

  // Coordinates for the (privacy-filtered) map — the API already serves
  // exact values only to the owner / paid student / admin.
  const mapPin =
    task.location_lat && task.location_lng
      ? (() => {
          const lat = parseFloat(task.location_lat);
          const lng = parseFloat(task.location_lng);
          return Number.isNaN(lat) || Number.isNaN(lng) ? null : { lat, lng };
        })()
      : null;

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
          {task.location_exact ? (
            <>
              <Text style={styles.infoText}>{`📍 ${task.location_address_full || task.location_address}`}</Text>
              {!!task.location_landmark && (
                <Text style={styles.infoText}>{`🗺️ ${task.location_landmark}`}</Text>
              )}
              <Text style={styles.infoText}>{`◯ Check-in radius: ${task.geofence_radius_m} m`}</Text>
              {!!mapPin && (
                <View style={styles.mapFrame}>
                  <MapPicker
                    pin={mapPin}
                    geofenceRadiusM={task.geofence_radius_m}
                    readOnly
                    height={180}
                  />
                </View>
              )}
            </>
          ) : (
            <>
              <Text style={styles.infoText}>{`📍 Approximate area: ${task.location_area || task.location_address}`}</Text>
              <Text style={styles.locationNote}>
                The exact location is shared once the task is accepted and payment is held.
              </Text>
              {!!mapPin && (
                <View style={styles.mapFrame}>
                  <MapPicker pin={mapPin} readOnly height={180} />
                </View>
              )}
            </>
          )}
        </View>

        {task.scheduled_date && (
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Scheduled</Text>
            <Text style={styles.infoText}>
              {`📅 ${task.scheduled_date}${task.scheduled_time ? `  ${task.scheduled_time.slice(0, 5)}` : ''}`}
            </Text>
          </View>
        )}

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
            <Text style={styles.assignedText}>{`✅ ${task.assigned_student_first_name || task.assigned_student_name}`}</Text>
            {!!task.escrow_status && (
              <Text style={styles.escrowText}>{`💰 Escrow: ${task.escrow_status}`}</Text>
            )}
          </View>
        )}
      </View>

      {/* === Broadcast flow: Student invitation (accept / ignore / decline) === */}
      {isStudent && hasOpenRequest && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📣 This Task Was Sent to You</Text>
          <Text style={styles.matchedInfo}>
            You were selected for this task based on your profile and location.
            {"\n"}The first student to accept gets the job.
          </Text>
          <TouchableOpacity
            style={[styles.actionButton, styles.confirmButton, actingOnRequest && styles.disabledButton]}
            onPress={handleAcceptRequest}
            disabled={actingOnRequest}
          >
            {actingOnRequest
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.actionButtonText}>Accept Task</Text>}
          </TouchableOpacity>
          <View style={{ flexDirection: 'row', gap: 10 }}>
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#f0f0f0', marginBottom: 0 }, actingOnRequest && styles.disabledButton]}
              onPress={handleIgnoreRequest}
              disabled={actingOnRequest}
            >
              <Text style={[styles.actionButtonText, { color: '#666' }]}>Ignore</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, styles.cancelMatchButton, { marginBottom: 0 }, actingOnRequest && styles.disabledButton]}
              onPress={handleDeclineRequest}
              disabled={actingOnRequest}
            >
              <Text style={styles.cancelMatchText}>Decline</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* === Broadcast flow: Household matched section === */}
      {isOwner && task.status === 'Matched' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🎯 Student Matched — Action Required</Text>
          <Text style={styles.matchedInfo}>
            {task.assigned_student_first_name || task.assigned_student_name} accepted your task!
            {'\n'}You have 10 minutes to confirm and pay.
          </Text>
          {graceTimeLeft && (
            <View style={[styles.graceBadge, graceTimeLeft === 'Expired' ? styles.graceExpired : null]}>
              <Text style={styles.graceText}>⏱ Grace window: {graceTimeLeft}</Text>
            </View>
          )}

          {showPhoneInput ? (
            <View style={styles.phoneInputBox}>
              <Text style={styles.label}>M-Pesa Phone Number</Text>
              <TextInput
                style={styles.input}
                placeholder="254712345678"
                keyboardType="phone-pad"
                value={confirmPhone}
                onChangeText={setConfirmPhone}
              />
              <TouchableOpacity
                style={[styles.actionButton, styles.confirmButton, confirmingMatch && styles.disabledButton]}
                onPress={handleConfirmMatch}
                disabled={confirmingMatch}
              >
                {confirmingMatch
                  ? <ActivityIndicator color="#fff" />
                  : <Text style={styles.actionButtonText}>Confirm & Pay</Text>}
              </TouchableOpacity>
            </View>
          ) : (
            <View style={{ gap: 10 }}>
              <TouchableOpacity
                style={[styles.actionButton, styles.confirmButton]}
                onPress={() => setShowPhoneInput(true)}
              >
                <Text style={styles.actionButtonText}>Confirm & Pay (M-Pesa)</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.cancelMatchButton, cancellingMatch && styles.disabledButton]}
                onPress={handleCancelMatch}
                disabled={cancellingMatch}
              >
                {cancellingMatch
                  ? <ActivityIndicator color="#c00" />
                  : <Text style={styles.cancelMatchText}>Cancel Match</Text>}
              </TouchableOpacity>
            </View>
          )}
        </View>
      )}

      {/* === Broadcast flow: Payment pending (household) === */}
      {isOwner && task.status === 'PaymentPending' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>⏳ Payment Processing</Text>
          <Text style={styles.matchedInfo}>Waiting for M-Pesa confirmation. Check your phone for the STK prompt.</Text>
        </View>
      )}

      {/* === Broadcast flow: Student matched (waiting) === */}
      {isAssignedStudent && task.status === 'Matched' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>✅ You Got the Job!</Text>
          <Text style={styles.matchedInfo}>
            The household has 10 minutes to confirm and pay.{"\n"}
            Full address will be shared after payment.
          </Text>
          {graceTimeLeft && (
            <View style={[styles.graceBadge, graceTimeLeft === 'Expired' ? styles.graceExpired : null]}>
              <Text style={styles.graceText}>⏱ Waiting: {graceTimeLeft}</Text>
            </View>
          )}
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: '#fca5a5' }, studentCancelling && styles.disabledButton]}
            onPress={handleStudentCancel}
            disabled={studentCancelling}
          >
            {studentCancelling
              ? <ActivityIndicator color="#c00" />
              : <Text style={[styles.actionButtonText, { color: '#c00' }]}>Cancel (lowers reliability)</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Broadcast flow: Student payment pending === */}
      {isAssignedStudent && task.status === 'PaymentPending' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>⏳ Payment Processing</Text>
          <Text style={styles.matchedInfo}>The household is completing payment. You&apos;ll be notified once it&apos;s done.</Text>
        </View>
      )}

      {/* === Broadcast flow: Household broadcasting status === */}
      {isOwner && ['Broadcasting', 'Reopened'].includes(task.status) && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📡 Searching for Students</Text>
          <Text style={styles.matchedInfo}>
            Round {task.broadcast_round || 1} — looking for students within {task.search_radius_km} km.
            {"\n"}We&apos;ll notify you when a student accepts.
          </Text>
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: '#e0e7ff' }, rebroadcasting && styles.disabledButton]}
            onPress={handleRebroadcast}
            disabled={rebroadcasting}
          >
            {rebroadcasting
              ? <ActivityIndicator color="#3730a3" />
              : <Text style={[styles.actionButtonText, { color: '#3730a3' }]}>Re-broadcast Now</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Broadcast flow: No students found === */}
      {isOwner && task.status === 'Posted' && task.broadcast_round === 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📭 No Students Found</Text>
          <Text style={styles.matchedInfo}>
            No students were available for this task. Try raising the budget, changing the scheduled time, or re-broadcasting.
          </Text>
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: '#e0e7ff' }, rebroadcasting && styles.disabledButton]}
            onPress={handleRebroadcast}
            disabled={rebroadcasting}
          >
            {rebroadcasting
              ? <ActivityIndicator color="#3730a3" />
              : <Text style={[styles.actionButtonText, { color: '#3730a3' }]}>Re-broadcast</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Broadcast flow: Task requests (household view) === */}
      {isOwner && task.task_requests && task.task_requests.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{`📡 Broadcast Requests (${task.task_requests.length})`}</Text>
          {task.task_requests.map((req: any) => (
            <View key={req.id} style={styles.bidCard}>
              <View style={styles.bidHeader}>
                <View>
                  <Text style={styles.bidStudent}>{`👤 ${req.student_first_name || req.student_username}`}</Text>
                  <Text style={styles.bidMeta}>{`⭐ ${req.student_rating} • ${req.student_verification}`}</Text>
                </View>
                <View style={[styles.bidStatusBadge, { backgroundColor: req.status === 'SENT' ? '#e0f2fe' : req.status === 'VIEWED' ? '#fef3c7' : req.status === 'ACCEPTED' ? '#d1fae5' : req.status === 'TAKEN' ? '#e0e0e0' : '#fee2e2' }]}>
                  <Text style={styles.bidStatusText}>{req.status}</Text>
                </View>
              </View>
              <Text style={styles.bidDate}>{`Round ${req.broadcast_round} • Score: ${req.rank_score || '—'}`}</Text>
            </View>
          ))}
        </View>
      )}

      {/* === Household: start code display (Assigned) === */}
      {isOwner && task.status === 'Assigned' && startCode && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>🔐 Start Code</Text>
          <Text style={styles.startCodeInfo}>Share this 4-digit code with the student when they arrive. They must enter it to begin work.</Text>
          <View style={styles.startCodeBox}>
            <Text style={styles.startCodeText}>{startCode}</Text>
          </View>
        </View>
      )}

      {/* === Student: check-in with start code (Assigned) === */}
      {isAssignedStudent && task.status === 'Assigned' && task.escrow_status === 'Held' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📍 Check In to Start</Text>
          <Text style={styles.matchedInfo}>
            Enter the 4-digit code from the household. Your GPS location is
            checked once, right now, to confirm you&apos;re at the task location —
            it is never tracked in the background.
          </Text>
          <TextInput
            style={[styles.input, { letterSpacing: 8, fontSize: 24, textAlign: 'center' }]}
            placeholder="0000"
            keyboardType="number-pad"
            maxLength={4}
            value={checkinCode}
            onChangeText={setCheckinCode}
          />
          <TouchableOpacity
            style={[styles.actionButton, styles.confirmButton, checkingIn && styles.disabledButton]}
            onPress={() => handleCheckin(false)}
            disabled={checkingIn}
          >
            {checkingIn
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.actionButtonText}>Check In</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Check-in summary (household + assigned student, no coordinates) === */}
      {task.checkin_summary && (isOwner || isAssignedStudent) && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📍 Check-In</Text>
          <Text style={styles.infoText}>
            {`Arrived at ${formatClock(task.checkin_summary.arrived_at)}`}
          </Text>
          {task.checkin_summary.location_verified ? (
            <Text style={styles.checkinVerifiedText}>✓ Location verified</Text>
          ) : (
            <Text style={styles.checkinFlaggedText}>
              {`⚠️ Location not verified (${prettyResult(task.checkin_summary.result)})`}
            </Text>
          )}
          {isOwner && !task.checkin_summary.location_verified && (
            <Text style={styles.startCodeInfo}>
              The student&apos;s check-in could not be location-verified. You may want to
              confirm they arrived in person.
            </Text>
          )}
        </View>
      )}

      {/* === Student: retry check-in after a flagged result === */}
      {isAssignedStudent && task.status === 'InProgress' && task.checkin_summary && !task.checkin_summary.location_verified && (
        <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: '#f59e0b' }]}>
          <Text style={styles.cardTitle}>⚠️ Verify Your Location</Text>
          <Text style={styles.matchedInfo}>
            Your check-in was recorded but the location could not be verified
            ({prettyResult(task.checkin_summary.result)}). Move closer to the task pin or
            find a clearer GPS signal, then retry — no start code needed.
          </Text>
          <TouchableOpacity
            style={[styles.actionButton, styles.confirmButton, checkingIn && styles.disabledButton]}
            onPress={() => handleCheckin(true)}
            disabled={checkingIn}
          >
            {checkingIn
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.actionButtonText}>Retry Check-In</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Admin: location audit / dispute map view === */}
      {user?.role === 'ADMIN' && (
        <View style={{ marginHorizontal: 16, marginBottom: 8 }}>
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: '#0ea5e9' }]}
            onPress={() => router.push(`/tasks/${task.id}/location-audit` as any)}
          >
            <Text style={styles.actionButtonText}>🗺️ Location Audit</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* === Awaiting confirmation (household) === */}
      {isOwner && task.status === 'AwaitingConfirmation' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>✅ Student Finished — Your Action Required</Text>
          <Text style={styles.matchedInfo}>
            The student has marked the work as complete.{'\n'}
            Please confirm the work is satisfactory or raise a dispute.
          </Text>
          {confirmTimeLeft && (
            <View style={styles.graceBadge}>
              <Text style={styles.graceText}>⏱ {confirmTimeLeft}</Text>
            </View>
          )}
          <Text style={styles.startCodeInfo}>Payment will be automatically released if no action is taken within 48 hours.</Text>
          <TouchableOpacity
            style={[styles.actionButton, styles.confirmButton]}
            onPress={handleHouseholdConfirm}
          >
            <Text style={styles.actionButtonText}>✅ Confirm Work Complete</Text>
          </TouchableOpacity>
          {!task.has_dispute && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#E91E63', marginTop: 8 }]}
              onPress={() => setShowDisputeForm(true)}
            >
              <Text style={styles.actionButtonText}>⚠️ Report a Problem</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* === Awaiting confirmation (student view) === */}
      {isAssignedStudent && task.status === 'AwaitingConfirmation' && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>⏳ Waiting for Confirmation</Text>
          <Text style={styles.matchedInfo}>
            You&apos;ve marked the work as done. The household has 48 hours to confirm.{'\n'}
            Payment will be released automatically if they don&apos;t respond.
          </Text>
          {confirmTimeLeft && (
            <View style={styles.graceBadge}>
              <Text style={styles.graceText}>⏱ {confirmTimeLeft}</Text>
            </View>
          )}
          {task.has_dispute && !showDisputeResponse && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#f97316' }]}
              onPress={() => setShowDisputeResponse(true)}
            >
              <Text style={styles.actionButtonText}>📝 Respond to Dispute</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* === Dispute form (household) === */}
      {showDisputeForm && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>⚠️ Report a Problem</Text>
          <Text style={styles.startCodeInfo}>Select the reason and describe the problem. Payment will be frozen while admin reviews.</Text>
          <Text style={styles.label}>Reason *</Text>
          {DISPUTE_REASONS.map(r => (
            <TouchableOpacity
              key={r.value}
              style={[styles.reasonOption, disputeReason === r.value && styles.reasonSelected]}
              onPress={() => setDisputeReason(r.value)}
            >
              <Text style={[styles.reasonText, disputeReason === r.value && { color: '#fff' }]}>{r.label}</Text>
            </TouchableOpacity>
          ))}
          <Text style={[styles.label, { marginTop: 12 }]}>Description *</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="Describe the problem in detail..."
            multiline
            value={disputeDescription}
            onChangeText={setDisputeDescription}
          />
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 12 }}>
            <TouchableOpacity
              style={[styles.actionButton, { flex: 1, backgroundColor: '#E91E63' }, submittingDispute && styles.disabledButton]}
              onPress={handleRaiseDispute}
              disabled={submittingDispute}
            >
              {submittingDispute
                ? <ActivityIndicator color="#fff" />
                : <Text style={styles.actionButtonText}>Submit Dispute</Text>}
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.actionButton, { flex: 1, backgroundColor: '#6b7280' }]}
              onPress={() => { setShowDisputeForm(false); setDisputeReason(''); setDisputeDescription(''); }}
            >
              <Text style={styles.actionButtonText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* === Dispute response form (student) === */}
      {showDisputeResponse && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📝 Respond to Dispute</Text>
          <Text style={styles.startCodeInfo}>Explain your side of the situation. Admin will review both statements.</Text>
          <TextInput
            style={[styles.input, styles.textArea]}
            placeholder="Describe what happened and the work you completed..."
            multiline
            value={disputeResponseText}
            onChangeText={setDisputeResponseText}
          />
          <TouchableOpacity
            style={[styles.actionButton, styles.confirmButton, submittingResponse && styles.disabledButton]}
            onPress={handleDisputeResponse}
            disabled={submittingResponse}
          >
            {submittingResponse
              ? <ActivityIndicator color="#fff" />
              : <Text style={styles.actionButtonText}>Submit Response</Text>}
          </TouchableOpacity>
        </View>
      )}

      {/* === Disputed status info === */}
      {task.status === 'Disputed' && (isOwner || isAssignedStudent) && !showDisputeForm && !showDisputeResponse && (
        <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: '#E91E63' }]}>
          <Text style={styles.cardTitle}>⚖️ Dispute in Progress</Text>
          <Text style={styles.matchedInfo}>An admin is reviewing this dispute. Payment is frozen until a decision is made.</Text>
          {isAssignedStudent && !task.has_dispute && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#f97316' }]}
              onPress={() => setShowDisputeResponse(true)}
            >
              <Text style={styles.actionButtonText}>📝 Add Your Response</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* === NoShow info === */}
      {task.status === 'NoShow' && (isOwner || isAssignedStudent) && (
        <View style={[styles.card, { borderLeftWidth: 4, borderLeftColor: '#dc2626' }]}>
          <Text style={styles.cardTitle}>🚫 No-Show Recorded</Text>
          {isOwner && (
            <Text style={styles.matchedInfo}>The student did not check in within 30 minutes of the scheduled start. You can claim a full refund or re-broadcast the task.</Text>
          )}
          {isAssignedStudent && (
            <Text style={styles.matchedInfo}>A no-show has been recorded for this task. This has affected your reliability score.</Text>
          )}
        </View>
      )}

      {/* === Completion timestamps (both parties) === */}
      {task.has_completion && task.completion_timestamps && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>📋 Work Timeline</Text>
          {task.completion_timestamps.arrived_at && (
            <Text style={styles.infoText}>🕐 Arrived: {new Date(task.completion_timestamps.arrived_at).toLocaleString()}</Text>
          )}
          {task.completion_timestamps.started_at && (
            <Text style={styles.infoText}>▶️ Started: {new Date(task.completion_timestamps.started_at).toLocaleString()}</Text>
          )}
          {task.completion_timestamps.finished_at && (
            <Text style={styles.infoText}>✅ Finished: {new Date(task.completion_timestamps.finished_at).toLocaleString()}</Text>
          )}
          {task.completion_timestamps.has_before_photo && <Text style={styles.infoText}>📷 Before photo uploaded</Text>}
          {task.completion_timestamps.has_after_photo && <Text style={styles.infoText}>📷 After photo uploaded</Text>}
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

          {isAssignedStudent && task.status === 'InProgress' && (
            <TouchableOpacity
              style={[styles.actionButton, styles.completeButton]}
              onPress={handleStudentMarkDone}
            >
              <Text style={styles.actionButtonText}>Mark Work as Finished</Text>
            </TouchableOpacity>
          )}

          {isOwner && task.status === 'AwaitingConfirmation' && (
            <TouchableOpacity
              style={[styles.actionButton, styles.completeButton]}
              onPress={handleHouseholdConfirm}
            >
              <Text style={styles.actionButtonText}>Confirm Work Complete</Text>
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

          {/* Dispute — household only, during InProgress or AwaitingConfirmation */}
          {['InProgress', 'AwaitingConfirmation'].includes(task.status) && isOwner && !task.has_dispute && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#E91E63' }]}
              onPress={() => setShowDisputeForm(true)}
            >
              <Text style={styles.actionButtonText}>⚠️ Raise Dispute</Text>
            </TouchableOpacity>
          )}

          {/* Student dispute response */}
          {task.status === 'Disputed' && isAssignedStudent && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#f97316' }]}
              onPress={() => setShowDisputeResponse(true)}
            >
              <Text style={styles.actionButtonText}>📝 Respond to Dispute</Text>
            </TouchableOpacity>
          )}

          {/* Cancel task — household owner, before work starts */}
          {isOwner && ['Posted', 'Bidding', 'Broadcasting', 'Reopened', 'Assigned'].includes(task.status) && (
            <TouchableOpacity
              style={[styles.actionButton, { backgroundColor: '#fff', borderWidth: 1.5, borderColor: '#f44336' }]}
              onPress={async () => {
                const confirmed = await showConfirm(
                  'Cancel Task',
                  task.status === 'Assigned'
                    ? 'Cancel this task? A refund will be issued based on how close to the start time you are cancelling.'
                    : 'Cancel this task? All pending requests will be withdrawn.'
                );
                if (!confirmed) return;
                try {
                  const res: any = await api.tasks.cancelTask(task.id);
                  showAlert('Cancelled', res.message || 'Task cancelled.');
                  fetchTaskDetail();
                } catch (error: any) {
                  showAlert('Error', error.message || 'Failed to cancel task');
                }
              }}
            >
              <Text style={[styles.actionButtonText, { color: '#f44336' }]}>Cancel Task</Text>
            </TouchableOpacity>
          )}

        </View>
      )}

      {/* === Delete task (household, pre-work statuses only) === */}
      {isOwner && ['Posted', 'Broadcasting', 'Bidding', 'Reopened'].includes(task.status) && (
        <View style={{ marginHorizontal: 16, marginBottom: 8 }}>
          <TouchableOpacity
            style={[styles.actionButton, { backgroundColor: '#fff', borderWidth: 1.5, borderColor: '#9e9e9e' }]}
            onPress={handleDeleteTask}
          >
            <Text style={[styles.actionButtonText, { color: '#757575' }]}>🗑 Delete Task</Text>
          </TouchableOpacity>
        </View>
      )}

      <View style={{ height: 40 }} />

      {/* === Location-consent modal (first check-in) === */}
      <Modal
        visible={showConsentModal}
        transparent
        animationType="slide"
        onRequestClose={() => { if (!consenting) setShowConsentModal(false); }}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>📍 Location Notice</Text>
            <ScrollView style={styles.consentScroll}>
              <Text style={styles.consentText}>
                {consentInfo?.text ||
                  'To verify check-ins, your location is captured once when you check in or finish a task. It is never tracked in the background.'}
              </Text>
            </ScrollView>
            <Text style={styles.consentNote}>
              By agreeing you accept the location-collection notice. You can review
              it anytime in Settings → Privacy Policy.
            </Text>
            <View style={{ flexDirection: 'row', gap: 10 }}>
              <TouchableOpacity
                style={[styles.actionButton, { flex: 1, backgroundColor: '#6b7280', marginBottom: 0 }]}
                onPress={() => setShowConsentModal(false)}
                disabled={consenting}
              >
                <Text style={styles.actionButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, styles.confirmButton, { flex: 1, marginBottom: 0 }, consenting && styles.disabledButton]}
                onPress={handleAcceptConsent}
                disabled={consenting}
              >
                {consenting
                  ? <ActivityIndicator color="#fff" />
                  : <Text style={styles.actionButtonText}>I Agree</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
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
  // Broadcast-flow styles
  matchedInfo: { fontSize: 14, color: '#555', lineHeight: 20, marginBottom: 12 },
  graceBadge: { backgroundColor: '#fef3c7', paddingVertical: 8, paddingHorizontal: 14, borderRadius: 10, alignSelf: 'flex-start', marginBottom: 12 },
  graceText: { fontSize: 14, fontWeight: '700', color: '#92400e' },
  graceExpired: { backgroundColor: '#fee2e2' },
  confirmButton: { backgroundColor: '#16a34a' },
  cancelMatchButton: { backgroundColor: '#fff', borderWidth: 1.5, borderColor: '#fca5a5' },
  cancelMatchText: { color: '#c00', fontSize: 16, fontWeight: '600' },
  phoneInputBox: { marginTop: 8 },
  // Completion verification styles
  startCodeBox: { backgroundColor: '#1e293b', borderRadius: 12, paddingVertical: 20, alignItems: 'center', marginVertical: 12 },
  startCodeText: { fontSize: 42, fontWeight: '800', color: '#f8fafc', letterSpacing: 12 },
  startCodeInfo: { fontSize: 13, color: '#6b7280', lineHeight: 18, marginBottom: 8 },
  // Dispute form styles
  reasonOption: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8, padding: 12, marginBottom: 8, backgroundColor: '#f9fafb' },
  reasonSelected: { backgroundColor: '#E91E63', borderColor: '#E91E63' },
  reasonText: { fontSize: 14, color: '#374151' },
  // Map & check-in styles
  mapFrame: { borderRadius: 10, overflow: 'hidden', borderWidth: 1, borderColor: '#e0e0e0', marginTop: 8 },
  locationNote: { fontSize: 12, color: '#6b7280', fontStyle: 'italic', marginTop: 4 },
  checkinVerifiedText: { fontSize: 15, fontWeight: '700', color: '#16a34a', marginTop: 4 },
  checkinFlaggedText: { fontSize: 15, fontWeight: '700', color: '#d97706', marginTop: 4 },
  // Consent modal styles
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.55)', justifyContent: 'center', alignItems: 'center', padding: 24 },
  modalCard: { backgroundColor: '#fff', borderRadius: 14, padding: 20, width: '100%', maxWidth: 480, maxHeight: '80%' },
  modalTitle: { fontSize: 18, fontWeight: 'bold', color: '#1a1a1a', marginBottom: 12 },
  consentScroll: { maxHeight: 220, marginBottom: 12 },
  consentText: { fontSize: 14, color: '#374151', lineHeight: 21 },
  consentNote: { fontSize: 12, color: '#6b7280', marginBottom: 16, fontStyle: 'italic' },
});
