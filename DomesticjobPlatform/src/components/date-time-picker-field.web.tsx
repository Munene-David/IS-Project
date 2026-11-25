/**
 * Web implementation of the date/time picker field.
 * Uses native HTML <input type="date|time"> controls, which give the
 * browser's built-in calendar/clock UI. The iOS/Android implementation
 * lives in date-time-picker-field.tsx.
 */
import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

import {
  DateTimePickerFieldProps,
  formatDateForApi,
  formatTimeForApi,
  parseInputValue,
} from './date-time-picker-field.shared';

const INPUT_STYLE: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  borderWidth: 1,
  borderColor: '#d0d0d0',
  borderRadius: 8,
  padding: '13px 12px',
  fontSize: 15,
  backgroundColor: '#f9f9f9',
  color: '#333',
  fontFamily: 'inherit',
  outline: 'none',
};

export default function DateTimePickerField({
  label,
  mode,
  value,
  onChange,
  placeholder,
  minimumDate,
  hint,
}: DateTimePickerFieldProps) {
  const inputValue = value
    ? mode === 'date'
      ? formatDateForApi(value)
      : formatTimeForApi(value).slice(0, 5)
    : '';

  const minAttr = minimumDate
    ? mode === 'date'
      ? formatDateForApi(minimumDate)
      : formatTimeForApi(minimumDate).slice(0, 5)
    : undefined;

  return (
    <View style={styles.group}>
      <Text style={styles.label}>{label}</Text>
      <input
        type={mode === 'date' ? 'date' : 'time'}
        value={inputValue}
        min={minAttr}
        placeholder={placeholder}
        style={INPUT_STYLE}
        onChange={(e) => {
          onChange(parseInputValue(mode, e.target.value, value));
        }}
      />
      {hint ? <Text style={styles.hint}>{hint}</Text> : null}
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
  hint: {
    fontSize: 12,
    color: '#999',
    marginTop: 6,
    fontStyle: 'italic',
  },
});
