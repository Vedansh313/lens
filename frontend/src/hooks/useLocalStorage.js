import { useState } from "react";

export function useLocalStorage(key, initialValue) {
  const [storedValue, setStoredValue] = useState(() => {
    try {
      const item = window.localStorage.getItem(key);
      return item ? JSON.parse(item) : initialValue;
    } catch {
      return initialValue;
    }
  });

  const setValue = (value) => {
    const nextValue = value instanceof Function ? value(storedValue) : value;
    setStoredValue(nextValue);
    window.localStorage.setItem(key, JSON.stringify(nextValue));
  };

  return [storedValue, setValue];
}

