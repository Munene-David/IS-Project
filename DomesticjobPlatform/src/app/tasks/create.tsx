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
} from 'react-native';
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';

const TASK_CATEGORIES = [
  'Cleaning',
  'Cooking',
  'Laundry',
  'Childcare',
  'Gardening',
  'Errands',
  'Other',
];

export default function CreateTaskScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const goBack = useGoBack();
  
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [postedPrice, setPostedPrice] = useState('');
  const [locationAddress, setLocationAddress] = useState('');
  const [loading, setLoading] = useState(false);
  const [recommendedPrice, setRecommendedPrice] = useState<string | null>(null);

  // Redirect if not household owner
  useEffect(() => {
    if (user?.role !== 'HOUSEHOLD') {
      Alert.alert('Access Denied', 'Only household owners can post tasks.');
      goBack();
    }
  }, [user]);

  // Fetch recommended price when category changes
  useEffect(() => {
    if (category) {
      fetchRecommendedPrice();
    }
  }, [category]);

  const fetchRecommendedPrice = async () => {
    try {
      const data = await api.priceGuide.getByCategory(category);
      setRecommendedPrice(data.recommended_price);
      if (!postedPrice) {
        setPostedPrice(data.recommended_price);
      }
    } catch (error) {
      console.log('No price guide found for category');
      setRecommendedPrice(null);
    }
  };

  const handleCreateTask = async () => {
    // Validation
    if (!title.trim()) {
      Alert.alert('Error', 'Please enter a task title');
      return;
    }
    if (!description.trim()) {
      Alert.alert('Error', 'Please enter a task description');
      return;
    }
    if (!category) {
      Alert.alert('Error', 'Please select a category');
      return;
    }
    if (!postedPrice || parseFloat(postedPrice) <= 0) {
      Alert.alert('Error', 'Please enter a valid price');
      return;
    }
    if (!locationAddress.trim()) {
      Alert.alert('Error', 'Please enter a location');
      return;
    }

    setLoading(true);
    try {
      const taskData = {
        title: title.trim(),
        description: description.trim(),
        category,
        posted_price: parseFloat(postedPrice),
        location_address: locationAddress.trim(),
      };

      await api.tasks.create(taskData);
      
      Alert.alert(
        'Success',
        'Your task has been posted successfully!',
        [
          {
            text: 'OK',
            onPress: () => goBack(),
          },
        ]
      );
    } catch (error: any) {
      Alert.alert('Error', error.message || 'Failed to create task');
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => goBack()} style={styles.backButton}>
          <Text style={styles.backText}>← Cancel</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Post New Task</Text>
        <View style={{ width: 60 }} />
      </View>

      <ScrollView style={styles.scrollView} contentContainerStyle={styles.scrollContent}>
        <View style={styles.card}>
          <View style={styles.formGroup}>
            <Text style={styles.label}>Task Title *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g., House Cleaning - 3 Bedroom Apartment"
              value={title}
              onChangeText={setTitle}
            />
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Description *</Text>
            <TextInput
              style={[styles.input, styles.textArea]}
              placeholder="Describe the task in detail..."
              multiline
              numberOfLines={5}
              value={description}
              onChangeText={setDescription}
            />
            <Text style={styles.hint}>
              Include details about what needs to be done, any special requirements, and expected duration.
            </Text>
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Category *</Text>
            <View style={styles.categoryContainer}>
              {TASK_CATEGORIES.map((cat) => (
                <TouchableOpacity
                  key={cat}
                  style={[
                    styles.categoryChip,
                    category === cat && styles.categoryChipActive,
                  ]}
                  onPress={() => setCategory(cat)}
                >
                  <Text
                    style={[
                      styles.categoryChipText,
                      category === cat && styles.categoryChipTextActive,
                    ]}
                  >
                    {cat}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Offered Price (KES) *</Text>
            {recommendedPrice && (
              <Text style={styles.recommendedText}>
                💡 Recommended: KES {recommendedPrice}
              </Text>
            )}
            <TextInput
              style={styles.input}
              placeholder="Enter amount in KES"
              keyboardType="numeric"
              value={postedPrice}
              onChangeText={setPostedPrice}
            />
            <Text style={styles.hint}>
              This is what you're willing to pay for this task.
            </Text>
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Location *</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g., Kilimani, Nairobi"
              value={locationAddress}
              onChangeText={setLocationAddress}
            />
            <Text style={styles.hint}>
              Enter the address where the task will be performed.
            </Text>
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.infoTitle}>What happens next?</Text>
          <Text style={styles.infoText}>
            1. Your task will be visible to all students on the platform
          </Text>
          <Text style={styles.infoText}>
            2. Students can submit bids with their proposed rates
          </Text>
          <Text style={styles.infoText}>
            3. You can review bids and select the best student
          </Text>
          <Text style={styles.infoText}>
            4. Once accepted, you'll deposit payment into escrow
          </Text>
          <Text style={styles.infoText}>
            5. Student completes task and you release payment
          </Text>
        </View>

        <TouchableOpacity
          style={[styles.createButton, loading && styles.createButtonDisabled]}
          onPress={handleCreateTask}
          disabled={loading}
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <Text style={styles.createButtonText}>Post Task</Text>
          )}
        </TouchableOpacity>

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
  formGroup: {
    marginBottom: 20,
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
  textArea: {
    height: 120,
    textAlignVertical: 'top',
  },
  hint: {
    fontSize: 12,
    color: '#999',
    marginTop: 6,
    fontStyle: 'italic',
  },
  recommendedText: {
    fontSize: 13,
    color: '#007bff',
    marginBottom: 8,
    fontWeight: '600',
  },
  categoryContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  categoryChip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 20,
    backgroundColor: '#f0f0f0',
    borderWidth: 2,
    borderColor: 'transparent',
  },
  categoryChipActive: {
    backgroundColor: '#e3f2fd',
    borderColor: '#007bff',
  },
  categoryChipText: {
    fontSize: 14,
    color: '#666',
    fontWeight: '500',
  },
  categoryChipTextActive: {
    color: '#007bff',
    fontWeight: '600',
  },
  infoTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#1a1a1a',
    marginBottom: 12,
  },
  infoText: {
    fontSize: 14,
    color: '#555',
    marginBottom: 8,
    lineHeight: 20,
  },
  createButton: {
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
  createButtonDisabled: {
    backgroundColor: '#ccc',
  },
  createButtonText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: 'bold',
  },
});
