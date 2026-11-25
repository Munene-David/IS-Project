import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';

export default function CreateRatingScreen() {
  const router = useRouter();
  const { taskId, ratedUserId } = useLocalSearchParams();
  const { user } = useAuth();
  
  const [task, setTask] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState('');

  // Helper function for cross-platform alerts
  const showAlert = (title: string, message: string, onOk?: () => void) => {
    if (Platform.OS === 'web') {
      window.alert(`${title}\n\n${message}`);
      if (onOk) onOk();
    } else {
      Alert.alert(title, message, [
        { text: 'OK', onPress: onOk },
      ]);
    }
  };

  useEffect(() => {
    fetchTaskDetails();
  }, [taskId]);

  const fetchTaskDetails = async () => {
    try {
      const data = await api.tasks.get(Number(taskId));
      setTask(data);
    } catch (error: any) {
      showAlert('Error', 'Failed to load task details');
      console.error(error);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitRating = async () => {
    if (rating === 0) {
      showAlert('Error', 'Please select a rating');
      return;
    }

    if (!comment.trim()) {
      showAlert('Error', 'Please write a review comment');
      return;
    }

    setSubmitting(true);
    try {
      await api.ratings.create(
        Number(taskId),
        Number(ratedUserId),
        rating,
        comment.trim()
      );

      showAlert(
        'Success',
        'Your rating has been submitted!',
        () => router.back()
      );
    } catch (error: any) {
      showAlert('Error', error.message || 'Failed to submit rating');
    } finally {
      setSubmitting(false);
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

  // Determine who we're rating
  const isRatingStudent = user?.id === task.household_owner;
  const ratedUserName = isRatingStudent
    ? task.assigned_student_name
    : task.household_owner_name;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backButton}>
          <Text style={styles.backText}>← Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Rate & Review</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.scrollContent}>
        <View style={styles.card}>
          <Text style={styles.taskTitle}>{task.title}</Text>
          <Text style={styles.taskCategory}>📂 {task.category}</Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>
            Rate {ratedUserName}
          </Text>
          <Text style={styles.sectionSubtitle}>
            How was your experience with this {isRatingStudent ? 'student' : 'household owner'}?
          </Text>

          <View style={styles.starsContainer}>
            {[1, 2, 3, 4, 5].map((star) => (
              <TouchableOpacity
                key={star}
                onPress={() => setRating(star)}
                style={styles.starButton}
              >
                <Text style={styles.starText}>
                  {star <= rating ? '⭐' : '☆'}
                </Text>
              </TouchableOpacity>
            ))}
          </View>

          {rating > 0 && (
            <Text style={styles.ratingLabel}>
              {getRatingLabel(rating)}
            </Text>
          )}
        </View>

        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Write Your Review</Text>
          <TextInput
            style={styles.textArea}
            placeholder={`Tell others about your experience with ${ratedUserName}...`}
            multiline
            numberOfLines={6}
            value={comment}
            onChangeText={setComment}
            maxLength={500}
          />
          <Text style={styles.charCount}>
            {comment.length} / 500 characters
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.guideTitle}>📝 Review Guidelines</Text>
          <Text style={styles.guideText}>
            • Be honest and constructive
          </Text>
          <Text style={styles.guideText}>
            • Describe specific aspects of the experience
          </Text>
          <Text style={styles.guideText}>
            • Avoid personal attacks or offensive language
          </Text>
          <Text style={styles.guideText}>
            • Focus on professionalism and quality of work
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.submitButton, submitting && styles.submitButtonDisabled]}
          onPress={handleSubmitRating}
          disabled={submitting}
        >
          {submitting ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.submitButtonText}>Submit Rating</Text>
          )}
        </TouchableOpacity>

        <View style={{ height: 40 }} />
      </ScrollView>
    </View>
  );
}

function getRatingLabel(rating: number): string {
  const labels: Record<number, string> = {
    1: '⭐ Poor',
    2: '⭐⭐ Fair',
    3: '⭐⭐⭐ Good',
    4: '⭐⭐⭐⭐ Very Good',
    5: '⭐⭐⭐⭐⭐ Excellent',
  };
  return labels[rating] || '';
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
    marginBottom: 20,
  },
  starsContainer: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    marginBottom: 16,
  },
  starButton: {
    padding: 8,
  },
  starText: {
    fontSize: 40,
  },
  ratingLabel: {
    fontSize: 18,
    fontWeight: '600',
    color: '#007bff',
    textAlign: 'center',
  },
  textArea: {
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 12,
    fontSize: 15,
    backgroundColor: '#f9f9f9',
    minHeight: 150,
    textAlignVertical: 'top',
  },
  charCount: {
    fontSize: 12,
    color: '#999',
    textAlign: 'right',
    marginTop: 6,
  },
  guideTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#1a1a1a',
    marginBottom: 12,
  },
  guideText: {
    fontSize: 14,
    color: '#555',
    marginBottom: 8,
    lineHeight: 20,
  },
  submitButton: {
    backgroundColor: '#28a745',
    padding: 18,
    borderRadius: 12,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOpacity: 0.2,
    shadowOffset: { width: 0, height: 2 },
    shadowRadius: 4,
    elevation: 3,
  },
  submitButtonDisabled: {
    backgroundColor: '#ccc',
  },
  submitButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});
