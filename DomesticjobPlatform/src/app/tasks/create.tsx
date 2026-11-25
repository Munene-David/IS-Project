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
import { useRouter } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { api, PlaceResult } from '@/services/api';
import { useGoBack } from '@/hooks/useGoBack';
import DateTimePickerField from '@/components/date-time-picker-field';
import { formatDateForApi, formatTimeForApi } from '@/components/date-time-picker-field.shared';
import MapPicker from '@/components/map-picker';
import { MapPin } from '@/components/map-picker.shared';
import {
  requestLocationPermission,
  getCurrentLocationSnapshot,
} from '@/services/location';

const TASK_CATEGORIES = [
  'Cleaning',
  'Cooking',
  'Laundry',
  'Childcare',
  'Gardening',
  'Errands',
  'Other',
];

/** Default geofence radius (metres) — must stay within 30–1000. */
const DEFAULT_GEOFENCE_M = 150;

export default function CreateTaskScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const goBack = useGoBack();
  
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [postedPrice, setPostedPrice] = useState('');
  const [locationAddress, setLocationAddress] = useState('');
  const [scheduledDate, setScheduledDate] = useState<Date | null>(null);
  const [scheduledTime, setScheduledTime] = useState<Date | null>(null);
  const [loading, setLoading] = useState(false);
  const [recommendedPrice, setRecommendedPrice] = useState<string | null>(null);

  // --- Map pin location state ---
  const [pin, setPin] = useState<MapPin | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<PlaceResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [locating, setLocating] = useState(false);
  const [geofenceRadius, setGeofenceRadius] = useState(String(DEFAULT_GEOFENCE_M));
  const [landmark, setLandmark] = useState('');

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

  // --- Map location handlers ---

  const handleSearchAddress = async () => {
    const q = searchQuery.trim();
    if (!q) {
      Alert.alert('Search', 'Type an address or area name first (e.g. "Kilimani, Nairobi").');
      return;
    }
    setSearching(true);
    setSearchResults([]);
    try {
      const data = await api.geo.searchPlaces(q);
      if (!data.results?.length) {
        Alert.alert('No matches', 'Try a nearby landmark or area name, e.g. "Yaya Centre, Nairobi".');
      }
      setSearchResults(data.results ?? []);
    } catch (error: any) {
      Alert.alert('Search failed', error.message || 'Address search is unavailable.');
    } finally {
      setSearching(false);
    }
  };

  const handleSelectPlace = (place: PlaceResult) => {
    setPin({ lat: place.lat, lng: place.lng });
    setLocationAddress(place.label);
    setSearchResults([]);
    setSearchQuery('');
  };

  const handleUseCurrentLocation = async () => {
    setLocating(true);
    try {
      const granted = await requestLocationPermission();
      if (!granted) {
        Alert.alert('Permission needed', 'Allow location access so we can drop the pin where you are.');
        return;
      }
      const snapshot = await getCurrentLocationSnapshot();
      setPin({ lat: snapshot.lat, lng: snapshot.lng });
      // Fill the address from the coordinates (best effort).
      try {
        const rev = await api.geo.reverseGeocode(snapshot.lat, snapshot.lng);
        const label = rev.results?.[0]?.label;
        if (label) setLocationAddress(label);
      } catch {
        // Reverse geocode unavailable — the household can type it instead.
      }
    } catch {
      Alert.alert('Location unavailable', 'Could not read your GPS position. Try searching for the address instead.');
    } finally {
      setLocating(false);
    }
  };

  const parsedGeofence = (): number | null => {
    const value = parseInt(geofenceRadius, 10);
    if (Number.isNaN(value)) return null;
    return value;
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
    if (!pin && !locationAddress.trim()) {
      Alert.alert(
        'Location required',
        'Please enter a location address so students know where the task is.'
      );
      return;
    }

    // Confirm before posting
    const confirmed = await new Promise<boolean>(resolve => {
      if (Platform.OS === 'web') {
        resolve(window.confirm(
          `Post "${title.trim()}" for KES ${postedPrice}?\n\nEligible students nearby will be notified immediately.`
        ));
      } else {
        Alert.alert(
          'Post Task?',
          `Post "${title.trim()}" for KES ${postedPrice}?\n\nEligible students nearby will be notified immediately.`,
          [
            { text: 'Cancel', style: 'cancel', onPress: () => resolve(false) },
            { text: 'Post Task', style: 'default', onPress: () => resolve(true) },
          ]
        );
      }
    });
    if (!confirmed) return;

    setLoading(true);
    try {
      const taskData = {
        title: title.trim(),
        description: description.trim(),
        category,
        posted_price: parseFloat(postedPrice),
        location_address: locationAddress.trim(),
        ...(pin ? {
          location_lat: parseFloat(pin.lat.toFixed(6)),
          location_lng: parseFloat(pin.lng.toFixed(6)),
          location_pin_confirmed: true,
          geofence_radius_m: parsedGeofence() ?? DEFAULT_GEOFENCE_M,
        } : {
          location_pin_confirmed: false,
        }),
        ...(landmark.trim() ? { location_landmark: landmark.trim() } : {}),
        ...(scheduledDate ? { scheduled_date: formatDateForApi(scheduledDate) } : {}),
        ...(scheduledTime ? { scheduled_time: formatTimeForApi(scheduledTime) } : {}),
      };

      await api.tasks.create(taskData);

      if (Platform.OS === 'web') {
        window.alert('Your task has been posted! Students will be notified shortly.');
        goBack();
      } else {
        Alert.alert(
          'Task Posted!',
          'Your task has been posted successfully! Eligible students nearby will be notified.',
          [{ text: 'OK', onPress: () => goBack() }]
        );
      }
    } catch (error: any) {
      if (Platform.OS === 'web') {
        window.alert('Error: ' + (error.message || 'Failed to create task'));
      } else {
        Alert.alert('Error', error.message || 'Failed to create task');
      }
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
              This is what you&apos;re willing to pay for this task.
            </Text>
          </View>

          <View style={styles.formGroup}>
            <Text style={styles.label}>Task Location *</Text>
            <Text style={styles.hint}>
              Search for the address, drop the pin where the work happens, then
              fine-tune it by dragging. Students only see the approximate area
              until they accept and pay.
            </Text>

            {/* Address search */}
            <View style={styles.searchRow}>
              <TextInput
                style={[styles.input, styles.searchInput]}
                placeholder="e.g. Yaya Centre, Kilimani, Nairobi"
                value={searchQuery}
                onChangeText={setSearchQuery}
                onSubmitEditing={handleSearchAddress}
                returnKeyType="search"
              />
              <TouchableOpacity
                style={[styles.searchButton, searching && styles.disabledButton]}
                onPress={handleSearchAddress}
                disabled={searching}
              >
                {searching
                  ? <ActivityIndicator color="#fff" size="small" />
                  : <Text style={styles.searchButtonText}>Search</Text>}
              </TouchableOpacity>
            </View>

            {/* Map with draggable pin */}
            <View style={styles.mapFrame}>
              <MapPicker
                pin={pin}
                onPinChange={(p) => setPin(p)}
                geofenceRadiusM={parsedGeofence()}
                height={240}
              />
            </View>

            <TouchableOpacity
              style={[styles.currentLocationButton, locating && styles.disabledButton]}
              onPress={handleUseCurrentLocation}
              disabled={locating}
            >
              {locating
                ? <ActivityIndicator color="#007bff" size="small" />
                : <Text style={styles.currentLocationText}>📍 Use my current location</Text>}
            </TouchableOpacity>

            {/* Address text (auto-filled by search / current location) */}
            <TextInput
              style={styles.input}
              placeholder="Address / area description"
              value={locationAddress}
              onChangeText={setLocationAddress}
              multiline
            />

            {/* Search results */}
            {searchResults.length > 0 && (
              <View style={styles.resultsBox}>
                {searchResults.map((place, i) => (
                  <TouchableOpacity
                    key={`${place.lat}-${place.lng}-${i}`}
                    style={styles.resultRow}
                    onPress={() => handleSelectPlace(place)}
                  >
                    <Text style={styles.resultText} numberOfLines={2}>
                      📍 {place.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}

            {/* Check-in geofence */}
            <View style={styles.radiusRow}>
              <Text style={styles.radiusLabel}>Check-in radius (m)</Text>
              <TextInput
                style={[styles.input, styles.radiusInput]}
                placeholder="150"
                keyboardType="numeric"
                value={geofenceRadius}
                onChangeText={setGeofenceRadius}
              />
            </View>
            <Text style={styles.hint}>
              Students must check in within this distance of the pin (30–1000 m,
              default 150). The circle on the map shows the allowed area.
            </Text>

            {/* Landmark */}
            <TextInput
              style={styles.input}
              placeholder="Landmark hint (optional), e.g. Blue gate next to Yaya"
              value={landmark}
              onChangeText={setLandmark}
            />
            <Text style={styles.hint}>
              A landmark helps the student find the exact spot. Only shown after
              they are assigned and have paid.
            </Text>
          </View>

          <DateTimePickerField
            label="Scheduled Date (Optional)"
            mode="date"
            value={scheduledDate}
            onChange={setScheduledDate}
            placeholder="Tap to pick a date"
            minimumDate={new Date(new Date().setHours(0, 0, 0, 0))}
          />

          <DateTimePickerField
            label="Scheduled Time (Optional)"
            mode="time"
            value={scheduledTime}
            onChange={setScheduledTime}
            placeholder="Tap to pick a time"
            hint="Providing a date and time helps match you with available students."
          />
        </View>

        <View style={styles.card}>
          <Text style={styles.infoTitle}>How it works</Text>
          <Text style={styles.infoText}>
            1. Your task is broadcast to nearby, verified students automatically
          </Text>
          <Text style={styles.infoText}>
            2. The first student to accept gets the job — no manual selection
          </Text>
          <Text style={styles.infoText}>
            3. You have 10 minutes to confirm and pay via M-Pesa
          </Text>
          <Text style={styles.infoText}>
            4. Students only see the approximate area — the exact pin is shared after they accept and pay
          </Text>
          <Text style={styles.infoText}>
            5. Mark the task complete when done to release payment
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
  // Map location picker styles
  searchRow: {
    flexDirection: 'row',
    gap: 8,
    marginBottom: 8,
  },
  searchInput: {
    flex: 1,
    marginBottom: 0,
  },
  searchButton: {
    backgroundColor: '#007bff',
    borderRadius: 8,
    paddingHorizontal: 16,
    justifyContent: 'center',
    alignItems: 'center',
    minWidth: 84,
  },
  searchButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
  mapFrame: {
    borderRadius: 10,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#d0d0d0',
    marginBottom: 8,
  },
  currentLocationButton: {
    borderWidth: 1.5,
    borderColor: '#007bff',
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
    marginBottom: 8,
    backgroundColor: '#f0f7ff',
  },
  currentLocationText: {
    color: '#007bff',
    fontSize: 15,
    fontWeight: '600',
  },
  resultsBox: {
    borderWidth: 1,
    borderColor: '#e0e0e0',
    borderRadius: 8,
    marginBottom: 8,
    overflow: 'hidden',
  },
  resultRow: {
    padding: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
    backgroundColor: '#fafafa',
  },
  resultText: {
    fontSize: 13,
    color: '#333',
  },
  radiusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    marginBottom: 4,
  },
  radiusLabel: {
    fontSize: 14,
    color: '#333',
    fontWeight: '500',
  },
  radiusInput: {
    width: 90,
    marginBottom: 0,
  },
  disabledButton: {
    backgroundColor: '#ccc',
    borderColor: '#ccc',
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
