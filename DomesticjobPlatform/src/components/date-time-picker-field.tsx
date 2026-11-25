/**
 * Cross-platform date/time picker field (iOS & Android).
 * Uses the Expo UI DateTimePicker (Material 3 / SwiftUI):
 *   - Android: opens a native dialog on press.
 *   - iOS: opens a bottom sheet with an inline picker (iOS pickers are inline-only).
 *
 * The web implementation lives in date-time-picker-field.web.tsx.
 */
import React, { useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Platform,
  Modal,
} from 'react-native';
import { DateTimePicker } from '@expo/ui/community/datetime-picker';

import {
  DateTimePickerFieldProps,
  formatDisplayValue,
} from './date-time-picker-field.shared';

export default function DateTimePickerField({
  label,
  mode,
  value,
  onChange,
  placeholder,
  minimumDate,
  hint,
}: DateTimePickerFieldProps) {
  const [show, setShow] = useState(false);
  const [temp, setTemp] = useState<Date>(new Date());

  const open = () => {
    setTemp(value ?? new Date());
    setShow(true);
  };

  const display = formatDisplayValue(mode, value, placeholder);

  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <TouchableOpacity style={styles.field} onPress={open} activeOpacity={0.7}>
        <Text style={value ? styles.valueText : styles.placeholderText} numberOfLines={1}>
          {mode === 'date' ? '📅 ' : '🕐 '}
          {display}
        </Text>
        {value ? (
          <TouchableOpacity
            style={styles.clearButton}
            hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
            onPress={() => onChange(null)}
          >
            <Text style={styles.clearText}>✕</Text>
          </TouchableOpacity>
        ) : null}
      </TouchableOpacity>
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}

      {/* Android: native dialog, opens when the component mounts. */}
      {show && Platform.OS === 'android' && (
        <DateTimePicker
          value={temp}
          mode={mode}
          minimumDate={minimumDate}
          presentation="dialog"
          onValueChange={(_event, date) => {
            setShow(false);
            if (date) onChange(date);
          }}
          onDismiss={() => setShow(false)}
        />
      )}

      {/* iOS: bottom sheet with an inline picker. */}
      {show && Platform.OS === 'ios' && (
        <Modal
          transparent
          animationType="slide"
          visible={show}
          onRequestClose={() => setShow(false)}
        >
          <View style={styles.modalBackdrop}>
            <View style={styles.sheet}>
              <View style={styles.sheetHeader}>
                <TouchableOpacity onPress={() => setShow(false)} hitSlop={{ top: 10, bottom: 10 }}>
                  <Text style={styles.sheetCancel}>Cancel</Text>
                </TouchableOpacity>
                <Text style={styles.sheetTitle}>
                  {mode === 'date' ? 'Pick a date' : 'Pick a time'}
                </Text>
                <TouchableOpacity
                  onPress={() => {
                    setShow(false);
                    onChange(temp);
                  }}
                  hitSlop={{ top: 10, bottom: 10 }}
                >
                  <Text style={styles.sheetDone}>Done</Text>
                </TouchableOpacity>
              </View>
              <View style={styles.pickerWrap}>
                <DateTimePicker
                  value={temp}
                  mode={mode}
                  minimumDate={minimumDate}
                  onValueChange={(_event, date) => {
                    if (date) setTemp(date);
                  }}
                />
              </View>
              {value ? (
                <TouchableOpacity
                  style={styles.clearRow}
                  onPress={() => {
                    setShow(false);
                    onChange(null);
                  }}
                >
                  <Text style={styles.clearRowText}>
                    Clear {mode === 'date' ? 'date' : 'time'}
                  </Text>
                </TouchableOpacity>
              ) : null}
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  group: { marginBottom: 20 },
  label: {
    fontSize: 14,
    fontWeight: '600',
    color: '#333',
    marginBottom: 8,
  },
  field: {
    borderWidth: 1,
    borderColor: '#d0d0d0',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 14,
    fontSize: 15,
    backgroundColor: '#f9f9f9',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  valueText: { fontSize: 15, color: '#333', flex: 1 },
  placeholderText: { fontSize: 15, color: '#999', flex: 1 },
  clearButton: {
    paddingHorizontal: 6,
    paddingVertical: 2,
  },
  clearText: { fontSize: 15, color: '#999' },
  hint: {
    fontSize: 12,
    color: '#999',
    marginTop: 6,
    fontStyle: 'italic',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.4)',
    justifyContent: 'flex-end',
  },
  sheet: {
    backgroundColor: '#fff',
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    paddingBottom: 30,
  },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 20,
    paddingTop: 16,
    paddingBottom: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#eee',
  },
  sheetTitle: { fontSize: 16, fontWeight: '600', color: '#1a1a1a' },
  sheetCancel: { fontSize: 16, color: '#007bff' },
  sheetDone: { fontSize: 16, color: '#007bff', fontWeight: '700' },
  pickerWrap: { alignItems: 'center', paddingTop: 12 },
  clearRow: { alignItems: 'center', paddingVertical: 12 },
  clearRowText: { fontSize: 14, color: '#c00' },
});
